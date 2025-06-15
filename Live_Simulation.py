import os

from skyfield.api import load, utc
from datetime import datetime, timedelta
import simplekml
import GroundStation
import Satellite
import Graph_Manager
from pathlib import Path
from flask import Flask, Response

RESOURCES_DIR = Path(__file__).parent / "resources"
output_dir = "output"


class LiveKMLGenerator:
    def __init__(self):
        self.graph_mgr = Graph_Manager.GraphManager()
        self.ts = load.timescale()
        self.manager = GroundStation.GroundStationManager()
        file_path = RESOURCES_DIR / "ground_stations_global.txt"
        self.manager.load_from_file(file_path)
        self.graph_mgr.add_ground_stations(self.manager)
        self.graph_mgr.create_users()

    def generate_current_kml(self):
        """Generate KML for current time"""
        current_time = datetime.utcnow().replace(tzinfo=utc)
        skyfield_time = self.ts.from_datetime(current_time)

        # Create fresh KML
        kml = simplekml.Kml()

        # Clear and rebuild graph
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

        # Add ground stations
        for gs in self.graph_mgr.get_ground_stations():
            pnt = gs_folder.newpoint(
                name=f"GS-{gs.name}",
                coords=[(gs.longitude, gs.latitude, 0)]
            )
            pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/communications.png'
            pnt.style.iconstyle.color = simplekml.Color.green

        # Add satellites
        for sat in all_satellites:
            if hasattr(sat, 'latitude') and hasattr(sat, 'longitude'):
                pnt = sat_folder.newpoint(
                    name=f"Sat-{sat.name}",
                    coords=[(sat.longitude, sat.latitude, sat.altitude() * 1000)]
                )
                pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/target.png'
                pnt.style.iconstyle.color = simplekml.Color.red

        # Add users
        for user in self.graph_mgr.users:
            user_pnt = users_folder.newpoint(
                name=f"User {user.user_id}",
                coords=[(user.longitude, user.latitude, 0)]
            )
            user_pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/paddle/purple-stars.png'

        # Add regular links
        for u, v, data in G.edges(data=True):
            node_u = G.nodes[u]
            node_v = G.nodes[v]

            coord_u = self.graph_mgr.get_coords(node_u)
            coord_v = self.graph_mgr.get_coords(node_v)

            if coord_u and coord_v:
                line = links_folder.newlinestring(
                    name=f"Link {u}-{v}",
                    coords=[coord_u, coord_v]
                )
                connection_type = data.get('connection_type', 'unknown')
                if connection_type == 'satellite':
                    line.style.linestyle.color = simplekml.Color.red
                elif connection_type == 'ground_station':
                    line.style.linestyle.color = simplekml.Color.green
                else:
                    line.style.linestyle.color = simplekml.Color.blue

                line.altitudemode = simplekml.AltitudeMode.absolute

        # Calculate and add shortest path from first user to closest ground station
        self.add_shortest_path(G, paths_folder)

        return kml.kml()

    def add_shortest_path(self, G, paths_folder):
        """Calculate and visualize shortest path from first user to closest ground station"""
        if self.graph_mgr.users:
            try:
                user1 = self.graph_mgr.users[0]
                closest_gs = self.graph_mgr.find_closest_ground_station(user1)

                if closest_gs is not None:
                    path, length = self.graph_mgr.find_shortest_path(source=user1, target=closest_gs)

                    if path and len(path) > 1:
                        print(f"  Found shortest path with {len(path)} nodes, length: {length:.1f} km")

                        # Create path segments (avoid duplicates)
                        for i in range(len(path) - 1):
                            u, v = path[i], path[i + 1]

                            if u not in G.nodes or v not in G.nodes:
                                continue

                            node_u = G.nodes[u]
                            node_v = G.nodes[v]

                            coord_u = self.graph_mgr.get_coords(node_u)
                            coord_v = self.graph_mgr.get_coords(node_v)

                            if not coord_u or not coord_v:
                                continue

                            coords = [coord_u, coord_v]

                            # Create path segment line
                            line = paths_folder.newlinestring(
                                name=f"Path Segment {i + 1}: {u} -> {v}",
                                coords=coords
                            )
                            line.style.linestyle.color = simplekml.Color.blueviolet
                            line.style.linestyle.width = 4
                            line.altitudemode = simplekml.AltitudeMode.absolute

            except Exception as e:
                print(f"Warning: Could not compute shortest path: {e}")


# Flask Web Server for NetworkLink
app = Flask(__name__)
kml_generator = LiveKMLGenerator()


@app.route('/live_satellites.kml')
def serve_live_kml():
    """Serve live KML data"""
    kml_data = kml_generator.generate_current_kml()
    return Response(kml_data, mimetype='application/vnd.google-earth.kml+xml')


def create_master_kml():
    """Create master KML file with NetworkLink that refreshes every 30 seconds"""
    kml = simplekml.Kml()

    # Add NetworkLink for live updates
    network_link = kml.newnetworklink(name="Live Satellite Data")
    network_link.link.href = "http://localhost:5000/live_satellites.kml"
    network_link.link.refreshmode = simplekml.RefreshMode.oninterval
    network_link.link.refreshinterval = 30  # Refresh every 30 seconds

    # Save master KML
    os.makedirs(output_dir, exist_ok=True)
    kml_filename = os.path.join(output_dir, f"master_live_satellites.kml")
    kml.save(kml_filename)
    print("Master KML saved as: master_live_satellites.kml")
    print("Start the Flask server and open this file in Google Earth")


if __name__ == "__main__":
    # Create master KML file
    create_master_kml()

    # Start Flask server
    print("Starting Flask server...")
    print("Open master_live_satellites.kml in Google Earth")
    app.run(host='0.0.0.0', port=5000, debug=False)
