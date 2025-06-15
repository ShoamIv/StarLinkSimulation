import networkx as nx
from skyfield.api import wgs84
import numpy as np
import random
from typing import List
from GroundStation import GroundStation
from Satellite import Satellite
from User import User


class GraphManager:
    def __init__(self):
        self.G = nx.Graph()
        self.sat_nodes = {}  # Map satellite_id -> node name in graph
        self.gs_nodes = {}  # Map ground station name -> node name in graph
        self.earth_radius = 6371.0  # Earth radius in km
        self.users = []

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

    def get_ground_stations(self):
        """Returns all GroundStation objects stored in graph nodes (from self.gs_nodes)."""
        ground_stations = []
        for gs_name, node_name in self.gs_nodes.items():
            if node_name in self.G.nodes:
                node_data = self.G.nodes[node_name]
                if 'obj' in node_data:  # Assuming 'obj' stores the GroundStation object
                    ground_stations.append(node_data['obj'])
        return ground_stations

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

    def calculate_distance_3d(self, pos1, pos2):
        """
        Calculate 3D Euclidean distance between two positions.
        """
        return np.linalg.norm(pos2 - pos1)

    def satellite_to_groundstation_los(self, sat, gs_obj, time):
        """
        Check Line of Sight (LOS) between satellite and ground station.
        Returns True if satellite is above the local horizon (>0° elevation).
        """
        try:
            # Create ground station position using WGS84
            gs_location = wgs84.latlon(gs_obj.latitude, gs_obj.longitude)

            # Compute vector from GS to satellite at current time
            topocentric = (sat - gs_location).at(time)
            alt, az, distance = topocentric.altaz()

            # Return True if satellite is above the horizon
            return alt.degrees > 0, distance.km
        except Exception as e:
            print(f"Error in satellite_to_groundstation_los: {e}")
            return False, None

    @staticmethod
    def satellite_to_satellite_los(sat1, sat2, time):
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
            return min_distance_to_earth > (6371.0 + 100)  # 100km buffer

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

    def add_ground_to_satellite_edges(self, ts, time):
        print("Checking Ground Station/User to Satellite LOS...")

        satellites = self.get_satellites()
        ground_stations_or_users = self.get_ground_stations()
        ground_stations_or_users.extend(self.users)

        for gs_obj in ground_stations_or_users:
            gs_node_key = None
            if hasattr(gs_obj, 'name'):
                gs_node_key = self.gs_nodes.get(gs_obj.name)
            elif hasattr(gs_obj, 'user_id'):
                gs_node_key = self.gs_nodes.get(str(gs_obj.user_id))

            if gs_node_key is None or gs_node_key not in self.G.nodes:
                print(
                    f"Warning: Ground Station/User object {gs_obj} (mapped to {gs_node_key}) not found in graph nodes.")
                continue

            for sat_obj in satellites:
                sat_node_name = self.sat_nodes.get(sat_obj.satellite_id)
                if sat_node_name is None or sat_node_name not in self.G.nodes:
                    continue

                is_los, distance_km = self.satellite_to_groundstation_los(sat_obj.earth_satellite, gs_obj, time)
                if is_los and not self.G.has_edge(gs_node_key, sat_node_name):
                    print(gs_node_key, sat_node_name, distance_km)
                    self.G.add_edge(
                        gs_node_key,
                        sat_node_name,
                        weight=distance_km,
                        distance=distance_km,
                        connection_type='ground_station'
                    )

    def add_satellite_to_satellite_edges(self, ts, time):
        print("Checking Inter-Satellite LOS...")
        self.G.remove_edges_from([
            (u, v) for u, v, d in self.G.edges(data=True) if d.get("connection_type") == "satellite"
        ])
        satellites = self.get_satellites()
        num_satellites = len(satellites)

        for i in range(num_satellites):
            sat1_obj = satellites[i]
            sat1_node_name = self.sat_nodes.get(sat1_obj.satellite_id)
            if sat1_node_name is None or sat1_node_name not in self.G.nodes:
                continue

            for j in range(i + 1, num_satellites):
                sat2_obj = satellites[j]
                sat2_node_name = self.sat_nodes.get(sat2_obj.satellite_id)
                if sat2_node_name is None or sat2_node_name not in self.G.nodes:
                    continue

                sat_earth1 = sat1_obj.earth_satellite
                sat_earth2 = sat2_obj.earth_satellite

                if self.satellite_to_satellite_los(sat_earth1, sat_earth2, time):
                    pos1_eci = sat_earth1.at(time).position.km
                    pos2_eci = sat_earth2.at(time).position.km
                    distance_km = self.calculate_distance_3d(pos1_eci, pos2_eci)

                    max_inter_sat_range = 2000.0
                    if distance_km < max_inter_sat_range and not self.G.has_edge(sat1_node_name, sat2_node_name):
                        signal_strength = self.calculate_signal_strength(distance_km, 'satellite')
                        self.G.add_edge(
                            sat1_node_name,
                            sat2_node_name,
                            weight=distance_km,
                            distance=distance_km,
                            signal_strength=signal_strength,
                            connection_type='satellite'
                        )
                        print(
                            f"  Connected {sat1_node_name} to {sat2_node_name} (Inter-Sat LOS, dist: {distance_km:.0f} km)")

    def geographic_distance(self, coords1, coords2):
        """
        Calculate the haversine distance between two points.

        Args:
            coords1, coords2: tuples (lon, lat, alt) - alt is ignored here.

        Returns:
            Distance in kilometers.
        """
        from math import radians, sin, cos, sqrt, atan2

        lon1, lat1, _ = coords1
        lon2, lat2, _ = coords2

        R = 6371.0  # Earth radius in km

        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)

        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c

    def get_node_latency_penalty(self, node):
        attr = self.G.nodes[node]  # Get node attributes
        node_type = attr.get('type')

        if node_type == 'ground_station':
            gs_obj = attr.get('obj')
            if gs_obj:
                capacity = gs_obj.get_capacity()  # call method on the object
                return GroundStation.CAPACITY_LATENCY_PENALTY_MS.get(capacity, 0)
        elif node_type == 'satellite':
            sat_obj = attr.get('obj')
            if sat_obj:
                capacity = sat_obj.get_capacity()
                return Satellite.CAPACITY_LATENCY_PENALTY_MS.get(capacity, 0)

        return 0

    def weight_with_node_penalty(self, u, v, edge_attr):
        edge_weight = edge_attr.get('weight', 1)

        # Skip penalty for user nodes
        node_u_attr = self.G.nodes[u]
        if node_u_attr.get('type') == 'user':
            node_penalty = 0
        else:
            node_penalty = self.get_node_latency_penalty(u)

        return edge_weight + node_penalty

    def find_shortest_path(self, source, target):
        try:
            path = nx.shortest_path(self.G, source=source, target=target, weight=self.weight_with_node_penalty)
            length = nx.shortest_path_length(self.G, source=source, target=target, weight=self.weight_with_node_penalty)
            return path, length
        except nx.NetworkXNoPath:
            print(f"No path between {source} and {target}")
            return None, None

    def find_closest_ground_station(self, source):
        ground_stations = [node for node, attr in self.G.nodes(data=True) if attr.get('type') == 'ground_station']
        min_distance = float('inf')
        closest_gs = None

        for gs in ground_stations:
            try:
                dist = nx.shortest_path_length(self.G, source=source, target=gs, weight=self.weight_with_node_penalty)
                if dist < min_distance:
                    min_distance = dist
                    closest_gs = gs
            except nx.NetworkXNoPath:
                continue

        return closest_gs

    def send_data_to_closest_gs(self, source, weight='weight'):
        """
        Send data from source to the closest ground station.

        Args:
            source: source node key in graph.
            weight: edge attribute for shortest path calculation.

        Returns:
            Result dict from send_data, or None.
        """
        closest_gs = self.find_closest_ground_station(source)
        if closest_gs is None:
            print(f"No ground station reachable from source '{source}'")
            return None

        # Call your main send_data method with source and target
        return self.send_data(source, closest_gs, weight=weight)

    def get_graph(self):
        """
        Return the NetworkX graph object.
        """
        return self.G

    def create_users(self):
        """Creates user nodes and adds them to the graph."""

        user1 = User(1,  47.751076,  -120.740135)
        self.G.add_node(
            user1,
            type="user",
            latitude=user1.latitude,
            longitude=user1.longitude,
            altitude=0.0,
        )
        self.users.append(user1)
        self.gs_nodes[str(user1.user_id)] = user1  # <-- Add to gs_nodes

        # Los Angeles
        user2 = User(2, 36.778259, -119.417931)
        self.G.add_node(
            user2,
            type="user",
            latitude=user2.latitude,
            longitude=user2.longitude,
            altitude=0.0,
        )
        self.users.append(user2)
        self.gs_nodes[str(user2.user_id)] = user2

    def get_coords(self,node):
        if 'type' in node:
            if node['type'] == 'ground_station':
                return node['longitude'], node['latitude'], 0
            elif node['type'] == 'user':
                return node['longitude'], node['latitude'], 0
            elif node['type'] == 'satellite':
                sat_obj = node.get('obj', None)
                if sat_obj:
                    return sat_obj.longitude, sat_obj.latitude, sat_obj.altitude() * 1000
        return None
    """
    def clear(self):
        self.G.clear()  # Clears all nodes and edges
        self.users = []
        self.sat_nodes = {}
        self.gs_nodes = {}
    """

    def clear(self):
        """Clear only satellites and their edges, preserving ground stations."""

        # Get all satellite node names to remove
        sat_node_names = list(self.sat_nodes.values())

        # Remove satellite nodes (this also removes all edges connected to them)
        for node_name in sat_node_names:
            if node_name in self.G.nodes:
                self.G.remove_node(node_name)

        # Clear satellite-related data structures
        self.sat_nodes = {}


