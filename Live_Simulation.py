from skyfield.api import load, utc
from datetime import datetime, timedelta
import simplekml
import GroundStation
import Satellite
import Graph_Manager
import os
from pathlib import Path
from flask import Flask, Response
import threading
import time

RESOURCES_DIR = Path(__file__).parent / "resources"


class LiveKMLGenerator:
    def __init__(self):
        self.graph_mgr = Graph_Manager.GraphManager()
        self.ts = load.timescale()
        self.manager = GroundStation.GroundStationManager()
        file_path = RESOURCES_DIR / "ground_stations_global.txt"
        self.manager.load_from_file(file_path)

    def generate_current_kml(self):
        """Generate KML for current time"""
        current_time = datetime.utcnow().replace(tzinfo=utc)
        skyfield_time = self.ts.from_datetime(current_time)

        # Create fresh KML
        kml = simplekml.Kml()

        # Clear and rebuild graph
        self.graph_mgr.clear()
        self.graph_mgr.add_ground_stations(self.manager)
        Satellite.extractor(self.graph_mgr, self.ts, skyfield_time)

        all_satellites = self.graph_mgr.get_satellites()
        for sat in all_satellites:
            sat.update_position(self.ts, current_time)

        self.graph_mgr.add_satellite_to_satellite_edges(self.ts, skyfield_time)
        self.graph_mgr.add_ground_to_satellite_edges(self.ts, skyfield_time)
        self.graph_mgr.create_users()

        G = self.graph_mgr.get_graph()

        # Create folders
        gs_folder = kml.newfolder(name="Ground Stations")
        sat_folder = kml.newfolder(name="Satellites")
        users_folder = kml.newfolder(name="Users")
        links_folder = kml.newfolder(name="Links")

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

        # Add links
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

        return kml.kml()


# Method 1: Flask Web Server for NetworkLink
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
    kml.save("master_live_satellites.kml")
    print("Master KML saved as: master_live_satellites.kml")
    print("Start the Flask server and open this file in Google Earth")


# Method 2: File-based live updates
def generate_live_kml_files():
    """Generate KML files continuously"""
    kml_gen = LiveKMLGenerator()

    while True:
        try:
            kml_data = kml_gen.generate_current_kml()

            # Save with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"live_satellites_{timestamp}.kml"

            with open(filename, 'w') as f:
                f.write(kml_data)

            # Also save as a fixed name that viewers can refresh
            with open("current_satellites.kml", 'w') as f:
                f.write(kml_data)

            print(f"Updated KML: {filename}")
            time.sleep(30)  # Update every 30 seconds

        except Exception as e:
            print(f"Error generating KML: {e}")
            time.sleep(5)


if __name__ == "__main__":
    print("Choose update method:")
    print("1. Flask web server (recommended)")
    print("2. File-based updates")

    choice = input("Enter choice (1 or 2): ")

    if choice == "1":
        # Create master KML file
        create_master_kml()

        # Start Flask server
        print("Starting Flask server...")
        print("Open master_live_satellites.kml in Google Earth")
        app.run(host='0.0.0.0', port=5000, debug=False)

    elif choice == "2":
        print("Starting file-based live updates...")
        print("Monitor 000000000000000000000000000000current_satellites.kml file")
        generate_live_kml_files()
    else:
        print("Invalid choice")