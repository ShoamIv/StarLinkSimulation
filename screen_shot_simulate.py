from skyfield.api import load, utc, Topos
from datetime import datetime
import simplekml
import GroundStation
import Satellite
import Graph_Manager
import os
from pathlib import Path
# Get the path to the resources folder
RESOURCES_DIR = Path(__file__).parent / "resources"

# Build the graph
graph_mgr = Graph_Manager.GraphManager()
# Prepare time (single snapshot)
ts = load.timescale()
current_time = datetime.utcnow().replace(tzinfo=utc)
skyfield_time = ts.from_datetime(current_time)

# Load ground stations
manager = GroundStation.GroundStationManager()
file_path = RESOURCES_DIR / "ground_stations_global.txt"
manager.load_from_file(file_path)
graph_mgr.add_ground_stations(manager)
Satellite.extractor(graph_mgr, ts, skyfield_time)
all_satellites = graph_mgr.get_satellites()
G = graph_mgr.get_graph()

print(f"Total satellites loaded: {len(all_satellites)}")

# Update satellite positions once
for sat in all_satellites:
    sat.update_position(ts, current_time)

# Add visible edges based on line-of-sight calculations
print("Calculating visible edges...")
#graph_mgr.add_edges(all_satellites, skyfield_time)

# Create KML structure
kml = simplekml.Kml()
sat_folder = kml.newfolder(name="Satellites")
links_folder = kml.newfolder(name="Visible Links")
sat_to_sat_links = kml.newfolder(name="Satellite-to-Satellite Links")

# Add satellites to KML (no timestamp)
for sat in all_satellites:
    pnt = sat_folder.newpoint(
        name=f"Sat {sat.satellite_id}",
        coords=[(sat.longitude, sat.latitude, sat.altitude * 1000)]
    )
    pnt.altitudemode = simplekml.AltitudeMode.absolute
    pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/paddle/wht-blank.png'
    pnt.style.iconstyle.scale = 0.7
edge_count = {'satellite': 0, 'ground': 0}

# Draw all edges
for u, v, data in G.edges(data=True):
    node_u = G.nodes[u]
    node_v = G.nodes[v]
    coords = []

    # Get coordinates for both nodes
    for node_data in (node_u, node_v):
        if 'type' in node_data:  # Check node type instead of connection type
            if node_data['type'] == 'ground_station':
                gs = node_data['obj']
                coords.append((gs.longitude, gs.latitude, 0))
            elif node_data['type'] == 'satellite':
                sat_obj = node_data['obj']
                coords.append((sat_obj.longitude, sat_obj.latitude, sat_obj.altitude * 1000))
        else:
            print(f"Warning: Node missing type attribute: {node_data}")

    if len(coords) != 2:
        continue

        # Assign link style based on connection type
    connection_type = data.get('connection_type', 'unknown')
    distance = data.get('distance', 0)
    signal_strength = data.get('signal_strength', 0)

    if connection_type == 'satellite':
        line = sat_to_sat_links.newlinestring(
            name=f"{u} to {v} ({distance:.1f}km)",
            coords=coords
        )
        line.style.linestyle.color = simplekml.Color.red
        line.style.linestyle.width = 2
        edge_count['satellite'] += 1

    elif connection_type == 'ground':
        a = 1
        line.style.linestyle.color = simplekml.Color.green
        line.style.linestyle.width = 1
        edge_count['ground'] += 1

        line.style.linestyle.color = simplekml.Color.blue
        line.style.linestyle.width = 2
        edge_count['neighbor'] += 1

    line.altitudemode = simplekml.AltitudeMode.absolute
    line.extrude = 0
    line.tessellate = 1

# Save KML file
output_dir = "output"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
kml_filename = os.path.join(output_dir, f"satellite_snapshot_{timestamp}.kml")
kml.save(kml_filename)
print(f"KML file saved as: {kml_filename}")
