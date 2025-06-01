import networkx as nx
from skyfield.api import Topos
import numpy as np


class graph_actions:
    def __init__(self):
        self.G = nx.Graph()
        self.sat_nodes = {}  # Map satellite_id -> node name in graph
        self.gs_nodes = {}  # Map ground station name -> node name in graph

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
                            obj=gs)
            self.gs_nodes[gs.name] = node_name

    def add_satellites(self, satellites):
        """
        Add satellites (your Satellite class instances) to the graph.
        """
        for sat in satellites:
            node_name = f"Satellite_{sat.satellite_id}"
            self.G.add_node(node_name,
                            type='satellite',
                            latitude=sat.latitude,
                            longitude=sat.longitude,
                            altitude=sat.altitude,
                            obj=sat)
            self.sat_nodes[sat.satellite_id] = node_name

    def satellite_to_groundstation_los(self, skyfield_sat, gs_obj, time):
        """
        Check LOS between satellite and ground station using Skyfield.
        Returns True if satellite is above horizon (>0 degrees altitude).
        """
        gs_topos = Topos(latitude_degrees=gs_obj.latitude, longitude_degrees=gs_obj.longitude)
        difference = skyfield_sat - gs_topos
        topocentric = difference.at(time)
        alt, az, distance = topocentric.altaz()
        return alt.degrees > 0

    def satellite_to_satellite_los(self, sat1, sat2, time):
        """
        Check LOS between two satellites by verifying Earth does not block the line between them.
        """
        pos1 = sat1.at(time).position.km
        pos2 = sat2.at(time).position.km

        vector = pos2 - pos1
        vector_norm = np.linalg.norm(vector)
        earth_radius = 6371.0

        cross = np.cross(pos1, vector)
        dist_to_earth_center = np.linalg.norm(cross) / vector_norm

        return dist_to_earth_center > earth_radius

    def add_visible_edges(self, skyfield_satellites, time):
        """
        Add edges based on LOS and shortest distance, respecting connection limits.
        """
        # Satellite-to-ground station connections
        for sat_id, sat_node in self.sat_nodes.items():
            sat_obj = self.G.nodes[sat_node]['obj']
            sky_sat = skyfield_satellites[sat_id]
            possible_gs = []

            for gs_name, gs_node in self.gs_nodes.items():
                gs_obj = self.G.nodes[gs_node]['obj']
                if self.satellite_to_groundstation_los(sky_sat, gs_obj, time):
                    sat_pos = sky_sat.at(time).position.km
                    gs_pos = np.array([gs_obj.latitude, gs_obj.longitude, 0])  # ground assumed at 0 km
                    distance = np.linalg.norm(sat_pos - gs_pos)
                    possible_gs.append((distance, gs_node, gs_obj))

            # Sort ground stations by distance
            possible_gs.sort(key=lambda x: x[0])

            for _, gs_node, gs_obj in possible_gs:
                if sat_obj.can_connect_ground_station():
                    if sat_node not in self.G[gs_node]:
                        self.G.add_edge(sat_node, gs_node)
                        sat_obj.connect_ground_station(gs_obj.name)

        # Satellite-to-satellite connections
        sat_ids = list(self.sat_nodes.keys())
        for i in range(len(sat_ids)):
            sat1_id = sat_ids[i]
            sat1_node = self.sat_nodes[sat1_id]
            sat1_obj = self.G.nodes[sat1_node]['obj']
            sky_sat1 = skyfield_satellites[sat1_id]

            # Build list of other satellites with LOS and distance
            candidate_sats = []
            for j in range(len(sat_ids)):
                if i == j:
                    continue
                sat2_id = sat_ids[j]
                sat2_node = self.sat_nodes[sat2_id]
                sat2_obj = self.G.nodes[sat2_node]['obj']
                sky_sat2 = skyfield_satellites[sat2_id]

                if self.satellite_to_satellite_los(sky_sat1, sky_sat2, time):
                    pos1 = sky_sat1.at(time).position.km
                    pos2 = sky_sat2.at(time).position.km
                    distance = np.linalg.norm(pos1 - pos2)
                    candidate_sats.append((distance, sat2_node, sat2_obj))

            # Sort by distance and connect up to limit
            candidate_sats.sort(key=lambda x: x[0])

            for _, sat2_node, sat2_obj in candidate_sats:
                if sat1_obj.can_connect_satellite() and sat2_obj.can_connect_satellite():
                    if not self.G.has_edge(sat1_node, sat2_node):
                        self.G.add_edge(sat1_node, sat2_node)
                        sat1_obj.connect_satellite(sat2_obj.satellite_id)
                        sat2_obj.connect_satellite(sat1_obj.satellite_id)

    def get_graph(self):
        return self.G
