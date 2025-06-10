import networkx as nx
from skyfield.api import Topos
import numpy as np
import math
import random
from typing import Dict, List, Tuple, Optional
from Satellite import Satellite


class GraphManager:
    def __init__(self):
        self.G = nx.Graph()
        self.sat_nodes = {}  # Map satellite_id -> node name in graph
        self.gs_nodes = {}  # Map ground station name -> node name in graph
        self.earth_radius = 6371.0  # Earth radius in km

    def get_satellites(self):
        """Returns all Satellite objects stored in graph nodes.

        Returns:
            List[Satellite]: A list of Satellite objects from the graph.
        """
        satellites = []

        for sat_id, node_id in self.sat_nodes.items():
            if node_id in self.G.nodes:
                node_data = self.G.nodes[node_id]
                if 'obj' in node_data:  # Changed from 'satellite' to 'obj'
                    satellites.append(node_data['obj'])

        return satellites

    def add_ground_stations(self, ground_station_manager):
        """
        Add ground stations from a GroundStationManager instance to the graph.
        """
        for gs in ground_station_manager.all_stations():
            node_name = gs.name
            self.G.add_node(node_name,
                            type='ground_station',
                            latitude=gs.latitude,
                            longitude=gs.longitude,
                            altitude=0.0,  # Ground stations at sea level
                            obj=gs)
            self.gs_nodes[gs.name] = node_name

    def add_satellites(self, satellites):
        """
        Add satellites (your Satellite class instances) to the graph.
        """
        for sat in satellites:
            node_name = f"Satellite_{sat.satellite_id}"
            sat.capacity_level = random.choice([1, 2, 3])
            self.G.add_node(node_name,
                            type='satellite',
                            latitude=sat.latitude,
                            longitude=sat.longitude,
                            altitude=sat.altitude,
                            capacity=sat.capacity_level,
                            obj=sat
                            )
            self.sat_nodes[sat.satellite_id] = node_name

    def lat_lon_alt_to_cartesian(self, lat_deg, lon_deg, alt_km):
        """
        Convert latitude, longitude, altitude to cartesian coordinates (km).
        """
        lat_rad = math.radians(lat_deg)
        lon_rad = math.radians(lon_deg)
        r = self.earth_radius + alt_km

        x = r * math.cos(lat_rad) * math.cos(lon_rad)
        y = r * math.cos(lat_rad) * math.sin(lon_rad)
        z = r * math.sin(lat_rad)

        return np.array([x, y, z])

    def calculate_distance_3d(self, pos1, pos2):
        """
        Calculate 3D Euclidean distance between two positions.
        """
        return np.linalg.norm(pos2 - pos1)

    def satellite_to_groundstation_los(self, sat, gs_obj, time):
        """
        Check LOS between satellite and ground station using Skyfield.
        Returns True if satellite is above horizon (>0 degrees altitude).
        """
        skyfield_sat = sat
        try:
            gs_topos = Topos(latitude_degrees=gs_obj.latitude, longitude_degrees=gs_obj.longitude)
            difference = skyfield_sat - gs_topos
            topocentric = difference.at(time)
            alt, az, distance = topocentric.altaz()
            return alt.degrees > 0
        except Exception as e:
            print(f"Error in satellite_to_groundstation_los: {e}")
            return False


    @staticmethod
    def satellite_to_satellite_los(self, sat1, sat2, time):
        """
        Check LOS between two satellites by verifying Earth does not block the line between them.
        Uses improved geometric calculation.
        """

        try:
            pos1 = sat1.at(time).position.km
            pos2 = sat2.at(time).position.km

            # Vector from sat1 to sat2
            direction = pos2 - pos1
            direction_norm = np.linalg.norm(direction)

            if direction_norm == 0:
                return False  # Same position

            # Normalize direction vector
            direction_unit = direction / direction_norm

            # Find closest point on line to Earth center
            # Using parametric line equation: P(t) = pos1 + t * direction_unit
            # Minimize |P(t)|^2
            t_closest = -np.dot(pos1, direction_unit)

            # Clamp t to line segment bounds
            t_closest = max(0, min(t_closest, direction_norm))

            # Find closest point and distance to Earth center
            closest_point = pos1 + t_closest * direction_unit
            min_distance_to_earth = np.linalg.norm(closest_point)

            # Add small buffer to Earth radius to account for atmosphere
            return min_distance_to_earth > (self.earth_radius + 100)  # 100km buffer

        except Exception as e:
            print(f"Error in satellite_to_satellite_los: {e}")
            return False

    def calculate_signal_strength(self, distance_km, connection_type='satellite'):
        """
        Calculate signal strength based on distance (simple model).
        Returns a value between 0 and 1 (1 = strongest signal).
        """
        if connection_type == 'satellite':
            # Satellite-to-satellite: good up to ~2000km
            max_distance = 2000.0
        else:
            # Satellite-to-ground: good up to ~2500km
            max_distance = 2500.0

        # Simple inverse relationship
        if distance_km > max_distance:
            return 0.1  # Very weak signal

        strength = 1.0 - (distance_km / max_distance) * 0.9
        return max(0.1, strength)

    def add_orbit_edge(self, sat1, sat2, time):
        """Adds an edge between two satellites in the same orbit."""
        # Get the correct node names from the satellite IDs
        sat1_node = self.sat_nodes.get(sat1.satellite_id)
        sat2_node = self.sat_nodes.get(sat2.satellite_id)

        # Check if both satellites exist in the graph
        if sat1_node is None or sat2_node is None:
            print(f"Warning: One or both satellites not found in graph")
            return

        # Get ECI positions (in kilometers)
        pos1 = sat1.earth_satellite.at(time).position.km
        pos2 = sat2.earth_satellite.at(time).position.km

        # Calculate 3D distance
        distance = self.calculate_distance_3d(pos1, pos2)

        # Add edge to the graph using the correct node names
        self.G.add_edge(
            sat1_node,  # Use node name, not satellite object
            sat2_node,  # Use node name, not satellite object
            weight=sat2.capacity_level,
            distance=distance,
            connection_type='satellite'
        )
    def add_edges(self, satellites, time):
        """
        Add edges based on LOS and shortest distance, respecting connection limits.
        Enhanced with proper distance calculations and edge weights.
        """
        skyfield_satellites = []
        for sat in satellites:
            skyfield_satellites.append(sat.earth_satellite)
        # Clear existing edges
        self.G.clear_edges()
        # Satellite-to-ground station connections
        for sat_id, sat_node in self.sat_nodes.items():
            sat_obj = self.G.nodes[sat_node]['obj']
            if sat_id >= len(skyfield_satellites):
                continue

            sky_sat = skyfield_satellites[sat_id]
            possible_gs = []

            # Get satellite position in cartesian coordinates
            sat_pos_skyfield = sky_sat.at(time).position.km

            for gs_name, gs_node in self.gs_nodes.items():
                gs_obj = self.G.nodes[gs_node]['obj']

                if self.satellite_to_groundstation_los(sky_sat, gs_obj, time):
                    # Convert ground station to cartesian coordinates
                    gs_pos = self.lat_lon_alt_to_cartesian(gs_obj.latitude, gs_obj.longitude, 0)
                    distance = self.calculate_distance_3d(sat_pos_skyfield, gs_pos)
                    signal_strength = self.calculate_signal_strength(distance, 'ground')

                    possible_gs.append((distance, gs_node, gs_obj, signal_strength))

            # Sort ground stations by distance (closest first)
            possible_gs.sort(key=lambda x: x[0])

            # Connect to closest available ground stations
            for distance, gs_node, gs_obj, signal_strength in possible_gs:
                if sat_obj.can_connect_ground_station():
                    if not self.G.has_edge(sat_node, gs_node):
                        # Add edge with weight (lower weight = better connection)
                        weight = distance / 1000.0  # Convert to thousands of km for reasonable weights
                        self.G.add_edge(sat_node, gs_node,
                                        weight=weight,
                                        distance=distance,
                                        signal_strength=signal_strength,
                                        connection_type='ground')
                        sat_obj.connect_ground_station(gs_obj.name)

        # Satellite-to-satellite connections
        sat_ids = list(self.sat_nodes.keys())
        for i in range(len(sat_ids)):
            sat1_id = sat_ids[i]
            if sat1_id >= len(skyfield_satellites):
                continue

            sat1_node = self.sat_nodes[sat1_id]
            sat1_obj = self.G.nodes[sat1_node]['obj']
            sky_sat1 = skyfield_satellites[sat1_id]

            # Build list of other satellites with LOS and distance
            candidate_sats = []
            for j in range(len(sat_ids)):
                if i == j:
                    continue

                sat2_id = sat_ids[j]
                if sat2_id >= len(skyfield_satellites):
                    continue

                sat2_node = self.sat_nodes[sat2_id]
                sat2_obj = self.G.nodes[sat2_node]['obj']
                sky_sat2 = skyfield_satellites[sat2_id]

                if self.satellite_to_satellite_los(self, sky_sat1, sky_sat2, time):
                    pos1 = sky_sat1.at(time).position.km
                    pos2 = sky_sat2.at(time).position.km
                    distance = self.calculate_distance_3d(pos1, pos2)
                    signal_strength = self.calculate_signal_strength(distance, 'satellite')
                    candidate_sats.append((distance, sat2_node, sat2_obj, signal_strength))

            # Sort by distance and connect up to limit
            candidate_sats.sort(key=lambda x: x[0])
            for distance, sat2_node, sat2_obj, signal_strength in candidate_sats:
                if (sat1_obj.can_connect_satellite() and
                        sat2_obj.can_connect_satellite() and
                        not self.G.has_edge(sat1_node, sat2_node)):
                    # Add edge with weight
                    weight = distance / 500.0  # Satellite connections have different scale
                    self.G.add_edge(sat1_node, sat2_node,
                                    weight=weight,
                                    distance=distance,
                                    signal_strength=signal_strength,
                                    connection_type='satellite')
                    sat1_obj.connect_satellite(sat2_obj.satellite_id)
                    sat2_obj.connect_satellite(sat1_obj.satellite_id)

    def find_shortest_path(self, source, target, weight='weight'):
        """
        Find shortest path between two nodes using Dijkstra's algorithm.
        Args:
            source: Source node name
            target: Target node name
            weight: Edge attribute to use as weight ('weight', 'distance', etc.)

        Returns:
            Tuple of (path, total_weight) or (None, None) if no path exists
        """
        try:
            if source not in self.G.nodes or target not in self.G.nodes:
                return None, None

            path = nx.shortest_path(self.G, source, target, weight=weight)
            path_length = nx.shortest_path_length(self.G, source, target, weight=weight)

            return path, path_length
        except nx.NetworkXNoPath:
            return None, None
        except Exception as e:
            print(f"Error finding shortest path: {e}")
            return None, None

    def find_all_shortest_paths(self, source, weight='weight'):
        """
        Find shortest paths from source to all other reachable nodes.

        Returns:
            Dictionary of {target: (path, distance)}
        """
        try:
            if source not in self.G.nodes:
                return {}

            paths = nx.single_source_dijkstra(self.G, source, weight=weight)
            distances, routes = paths

            result = {}
            for target in distances:
                if target != source:
                    result[target] = (routes[target], distances[target])

            return result
        except Exception as e:
            print(f"Error finding all shortest paths: {e}")
            return {}

    def find_best_ground_station_path(self, source_gs, target_gs):
        """
        Find the best path between two ground stations through the satellite network.
        """
        if source_gs not in self.gs_nodes or target_gs not in self.gs_nodes:
            return None, None

        source_node = self.gs_nodes[source_gs]
        target_node = self.gs_nodes[target_gs]

        return self.find_shortest_path(source_node, target_node)

    def send_data(self, source: str, target: str, weight: str = 'weight') -> Optional[Dict]:
        """
        Simulate sending data from source to target node over the shortest path.

        Args:
            source (str): The starting node name (ground station or satellite).
            target (str): The destination node name.
            weight (str): Edge attribute used for shortest path calculation (default: 'weight').

        Returns:
            dict with details if path exists, or None if not reachable.
        """
        path, total_cost = self.find_shortest_path(source, target, weight=weight)

        if path is None:
            print(f"No path found between {source} and {target}.")
            return None

        total_distance = 0.0
        min_signal_strength = float('inf')
        hop_info = []

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge = self.G[u][v]

            hop_info.append({
                'from': u,
                'to': v,
                'distance_km': edge.get('distance', 0.0),
                'signal_strength': edge.get('signal_strength', 0.0),
                'connection_type': edge.get('connection_type', 'unknown')
            })

            total_distance += edge.get('distance', 0.0)
            min_signal_strength = min(min_signal_strength, edge.get('signal_strength', 1.0))

        result = {
            'path': path,
            'hops': hop_info,
            'total_hops': len(path) - 1,
            'total_distance_km': round(total_distance, 2),
            'path_cost': round(total_cost, 4),
            'min_signal_strength': round(min_signal_strength, 4)
        }

        print(f"Data sent from {source} to {target}:")
        for hop in hop_info:
            print(
                f"  {hop['from']} -> {hop['to']} | Distance: {hop['distance_km']:.1f} km | Signal: {hop['signal_strength']:.2f}")

        print(f"Total path cost: {result['path_cost']}, Total distance: {result['total_distance_km']} km")
        print(f"Minimum signal strength on path: {result['min_signal_strength']}")
        print(f"Total hops: {result['total_hops']}")

        return result


    def get_graph(self):
        """
        Return the NetworkX graph object.
        """
        return self.G
