import os
import math
from datetime import datetime
from pathlib import Path
from flask import Flask, Response

from skyfield.api import load, utc
import simplekml

import GroundStation
import Satellite
import Graph_Manager
from User import User

RESOURCES_DIR = Path(__file__).parent / "resources"
output_dir = "output"


# === Utility Functions ===
def validate_coordinate(coord):
    """Validate that coordinate values are finite and reasonable"""
    if coord is None:
        return False
    if isinstance(coord, (list, tuple)) and len(coord) >= 2:
        lon, lat = coord[0], coord[1]
        alt = coord[2] if len(coord) > 2 else 0
        if (not math.isfinite(lon) or not math.isfinite(lat) or not math.isfinite(alt)
                or abs(lon) > 180 or abs(lat) > 90 or alt < -1000 or alt > 1000000):
            return False
        return True
    return False


def create_point(folder, name, coords, icon_href, color, scale=1.0, time_span=None):
    """Safely create a KML point with validation"""
    try:
        if not validate_coordinate(coords[0]):
            print(f"Warning: Invalid coordinates for {name}: {coords}")
            return None
        pnt = folder.newpoint(coords=coords)
        pnt.name = name
        pnt.altitudemode = simplekml.AltitudeMode.absolute
        pnt.style.iconstyle.icon.href = icon_href
        pnt.style.iconstyle.color = color
        pnt.style.iconstyle.scale = scale
        if time_span:
            pnt.timespan = time_span
        return pnt
    except Exception as e:
        print(f"Error creating point {name}: {e}")
        return None


def create_line(folder, name, coords, color, width, time_span=None):
    """Safely create a KML line with validation"""
    try:
        for coord in coords:
            if not validate_coordinate(coord):
                print(f"Warning: Invalid coordinates in line {name}: {coord}")
                return None
        line = folder.newlinestring(name=name, coords=coords)
        line.style.linestyle.color = color
        line.style.linestyle.width = width
        line.altitudemode = simplekml.AltitudeMode.absolute
        line.extrude = 0
        line.tessellate = 1
        if time_span:
            line.timespan = time_span
        return line
    except Exception as e:
        print(f"Error creating line {name}: {e}")
        return None


# === Main Class ===
class LiveKMLGenerator:
    def __init__(self):
        self.graph_mgr = Graph_Manager.GraphManager()
        self.ts = load.timescale()
        self.manager = GroundStation.GroundStationManager()
        file_path = RESOURCES_DIR / "ground_stations_global.txt"
        self.manager.load_from_file(file_path)
        self.graph_mgr.add_ground_stations(self.manager)
        user1 = User(1, 47.751076, -120.740135)
        user2 = User(2, 36.778259, -119.417931)
        self.graph_mgr.add_users(user1)
        self.graph_mgr.add_users(user2)

    def generate_current_kml(self):
        current_time = datetime.utcnow().replace(tzinfo=utc)
        skyfield_time = self.ts.from_datetime(current_time)
        kml = simplekml.Kml()

        self.graph_mgr.clear()
        Satellite.extractor(self.graph_mgr, self.ts, skyfield_time)

        all_satellites = self.graph_mgr.get_satellites()
        for sat in all_satellites:
            sat.update_position(self.ts, current_time)

        self.graph_mgr.add_satellite_to_satellite_edges(self.ts, skyfield_time)
        self.graph_mgr.add_ground_to_satellite_edges(self.ts, skyfield_time)

        G = self.graph_mgr.get_graph()

        # Create folders
        gs_folder = kml.newfolder(name="Ground Stations")
        sat_folder = kml.newfolder(name="Satellites")
        users_folder = kml.newfolder(name="Users")
        links_folder = kml.newfolder(name="Links")
        paths_folder = kml.newfolder(name="Shortest Paths")

        # Ground Stations
        for gs in self.graph_mgr.get_ground_stations():
            create_point(gs_folder, f"GS-{gs.name}", [(gs.longitude, gs.latitude, 0)],
                         'http://maps.google.com/mapfiles/kml/shapes/communications.png',
                         simplekml.Color.green)

        # Satellites
        for sat in all_satellites:
            create_point(sat_folder, f"Sat-{sat.name}", [(sat.longitude, sat.latitude, sat.altitude() * 1000)],
                         'http://maps.google.com/mapfiles/kml/shapes/target.png',
                         simplekml.Color.red)

        # Users
        for user in self.graph_mgr.users:
            create_point(users_folder, f"User {user.user_id}", [(user.longitude, user.latitude, 0)],
                         'http://maps.google.com/mapfiles/kml/paddle/purple-stars.png',
                         simplekml.Color.purple)

        # Links
        for u, v, data in G.edges(data=True):
            node_u = G.nodes[u]
            node_v = G.nodes[v]
            coord_u = self.graph_mgr.get_coords(node_u)
            coord_v = self.graph_mgr.get_coords(node_v)
            connection_type = data.get('connection_type', 'unknown')
            if connection_type == 'satellite':
                color = simplekml.Color.red
                width = 2
            elif connection_type == 'ground_station':
                color = simplekml.Color.green
                width = 0  # Set ground station link width to 0
            else:
                color = simplekml.Color.blue
                width = 1

            create_line(links_folder, f"Link {u}-{v}", [coord_u, coord_v], color=color, width=width)

        self.add_shortest_path(G, paths_folder)
        return kml.kml()

    def add_shortest_path(self, G, paths_folder):
        if self.graph_mgr.users:
            try:
                user1 = self.graph_mgr.users[0]
                path, length = self.graph_mgr.find_shortest_path_to_gs(user1)

                if path and len(path) > 1:
                    print(f"  Found shortest path with {len(path)} nodes, weighted: {length:.1f}")
                    for i in range(len(path) - 1):
                        u, v = path[i], path[i + 1]
                        if u not in G.nodes or v not in G.nodes:
                            continue
                        coord_u = self.graph_mgr.get_coords(G.nodes[u])
                        coord_v = self.graph_mgr.get_coords(G.nodes[v])
                        create_line(paths_folder, f"Path Segment {i + 1}: {u} -> {v}",
                                    [coord_u, coord_v], simplekml.Color.blueviolet, 4)
            except Exception as e:
                print(f"Warning: Could not compute shortest path: {e}")


# === Flask Server ===
app = Flask(__name__)
kml_generator = LiveKMLGenerator()


@app.route('/live_satellites.kml')
def serve_live_kml():
    kml_data = kml_generator.generate_current_kml()
    return Response(kml_data, mimetype='application/vnd.google-earth.kml+xml')


def create_master_kml():
    kml = simplekml.Kml()
    network_link = kml.newnetworklink(name="Live Satellite Data")
    network_link.link.href = "http://localhost:5000/live_satellites.kml"
    network_link.link.refreshmode = simplekml.RefreshMode.oninterval
    network_link.link.refreshinterval = 30

    os.makedirs(output_dir, exist_ok=True)
    kml_filename = os.path.join(output_dir, f"master_live_satellites.kml")
    kml.save(kml_filename)
    print("Master KML saved as: master_live_satellites.kml")
    print("Start the Flask server and open this file in Google Earth")


if __name__ == "__main__":
    create_master_kml()
    print("Starting Flask server...")
    print("Open master_live_satellites.kml in Google Earth")
    app.run(host='0.0.0.0', port=5000, debug=False)
