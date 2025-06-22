import networkx as nx
from geopy.distance import geodesic
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

    def get_coords(self, node):
        if 'type' in node:
            if node['type'] in ['ground_station', 'user']:
                lon = node.get('longitude')
                lat = node.get('latitude')
                if lon is not None and lat is not None:
                    return lon, lat, 0
            elif node['type'] == 'satellite':
                sat_obj = node.get('obj')
                if sat_obj:
                    return sat_obj.longitude, sat_obj.latitude, sat_obj.altitude() * 1000
        return None

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
            sat1_node,
            sat2_node,
            distance=distance,
            connection_type='satellite'
        )
        sat1.connected_satellites.add(sat2.satellite_id)
        sat2.connected_satellites.add(sat1.satellite_id)

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
                    if distance_km < 1000:
                        print(gs_node_key, sat_node_name, distance_km)
                        self.G.add_edge(
                            gs_node_key,
                            sat_node_name,
                            distance=distance_km,
                            connection_type='ground_station'
                        )

    def add_satellite_to_satellite_edges(self, ts, time):
        print("Adding cross-plane satellite links (laser communication)...")

        satellites = self.get_satellites()
        sat_by_id = {sat.satellite_id: sat for sat in satellites}
        MAX_INTER_SAT_RANGE = 2000.0  # km

        for sat in satellites:
            if len(sat.connected_satellites) >= sat.MAX_SATELLITE_CONNECTIONS:
                continue

            sat_node = self.sat_nodes.get(sat.satellite_id)
            if sat_node is None or sat_node not in self.G.nodes:
                continue

            # Candidates: satellites from different orbital planes
            candidates = [
                other for other in satellites
                if other.orbit_id != sat.orbit_id
                   and other.satellite_id != sat.satellite_id
                   and len(other.connected_satellites) < other.MAX_SATELLITE_CONNECTIONS
                   and self.sat_nodes.get(other.satellite_id) in self.G.nodes
                   and not self.G.has_edge(sat_node, self.sat_nodes[other.satellite_id])
            ]

            # Sort candidates by distance
            candidates_sorted = sorted(
                candidates,
                key=lambda other: self.calculate_distance_3d(
                    sat.earth_satellite.at(time).position.km,
                    other.earth_satellite.at(time).position.km
                )
            )

            for other in candidates_sorted:
                if len(sat.connected_satellites) >= sat.MAX_SATELLITE_CONNECTIONS:
                    break
                if len(other.connected_satellites) >= other.MAX_SATELLITE_CONNECTIONS:
                    continue

                other_node = self.sat_nodes[other.satellite_id]
                distance_km = self.calculate_distance_3d(
                    sat.earth_satellite.at(time).position.km,
                    other.earth_satellite.at(time).position.km
                )

                if distance_km > MAX_INTER_SAT_RANGE:
                    continue

                if not self.satellite_to_satellite_los(sat.earth_satellite, other.earth_satellite, time):
                    continue

                # Add bidirectional edge
                self.G.add_edge(
                    sat_node, other_node,
                    distance=distance_km,
                    connection_type='satellite'
                )
                sat.connected_satellites.add(other.satellite_id)
                other.connected_satellites.add(sat.satellite_id)

                print(f"  Connected {sat_node} <--> {other_node} (Cross-plane, dist: {distance_km:.0f} km)")

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
        distance_km = edge_attr.get('distance', 1)
        distance_latency_ms = (distance_km / 300_000) * 1000  # km / (km/s) → s → ms

        node_u_attr = self.G.nodes[u]
        node_penalty = 0 if node_u_attr.get('type') == 'user' else self.get_node_latency_penalty(u)

        return distance_latency_ms + node_penalty  # total latency in ms

    def find_shortest_path(self, source, target):
        try:
            path = nx.shortest_path(self.G, source=source, target=target, weight=self.weight_with_node_penalty)
            length = nx.shortest_path_length(self.G, source=source, target=target, weight=self.weight_with_node_penalty)
            return path, length
        except nx.NetworkXNoPath:
            print(f"No path between {source} and {target}")
            return None, None

    def comm_between_users(self, source_user, target_user):
        source_id = f"user_{source_user.user_id}"
        target_id = f"user_{target_user.user_id}"
        if source_id in self.G and target_id in self.G:
            try:
                path = nx.shortest_path(self.G, source=source_id, target=target_id,
                                        weight=self.weight_with_node_penalty)
                length = nx.shortest_path_length(self.G, source=source_id, target=target_id,
                                                 weight=self.weight_with_node_penalty)
                return path, length
            except nx.NetworkXNoPath:
                return None, float('inf')
        return None, float('inf')

    def find_shortest_path_to_gs(self, source):
        source_attr = self.G.nodes[source]
        user_lat = source_attr.get('latitude')
        user_lon = source_attr.get('longitude')

        if user_lat is None or user_lon is None:
            raise ValueError(f"User node {source} has no latitude/longitude info")

        ground_stations = [
            node for node, attr in self.G.nodes(data=True)
            if attr.get('type') == 'ground_station'
        ]

        closest_gs = None
        min_penalty_distance = float('inf')
        best_path = None  # Store the best path found

        for gs in ground_stations:
            gs_attr = self.G.nodes[gs]
            gs_lat = gs_attr.get('latitude')
            gs_lon = gs_attr.get('longitude')

            if gs_lat is None or gs_lon is None:
                continue

            # Step 1: Check physical distance
            distance_km = geodesic((user_lat, user_lon), (gs_lat, gs_lon)).kilometers

            if distance_km <= 1000:
                # Step 2: Use find_shortest_path to get both path and distance
                path, dist_with_penalty = self.find_shortest_path(source, gs)

                if dist_with_penalty is not None and dist_with_penalty < min_penalty_distance:
                    closest_gs = gs
                    min_penalty_distance = dist_with_penalty
                    best_path = path  # Store the corresponding path

        if closest_gs:
            return best_path, min_penalty_distance  # Return both path and length
        else:
            return None, None  # No GS within 1000 km reachable by path

    def get_graph(self):
        """
        Return the NetworkX graph object.
        """
        return self.G

    def add_users(self, user):
        """Creates user nodes and adds them to the graph."""
        self.G.add_node(
            user,
            type="user",
            latitude=user.latitude,
            longitude=user.longitude,
            altitude=0.0,
        )
        self.users.append(user)
        self.gs_nodes[str(user.user_id)] = user  # <-- Add to gs_nodes

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
