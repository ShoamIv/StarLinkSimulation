from skyfield.api import load, utc, Topos
from datetime import datetime
import simplekml
import GroundStation
import Satellite
import Graph_Manager
import os
from pathlib import Path

from User import User

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

print(f"Total satellites loaded: {len(all_satellites)}")
graph_mgr.create_users()
G = graph_mgr.get_graph()

# Update satellite positions once
for sat in all_satellites:
    sat.update_position(ts, current_time)

graph_mgr.add_satellite_to_satellite_edges(ts, skyfield_time)
graph_mgr.add_ground_to_satellite_edges(ts, skyfield_time)

user1 = graph_mgr.users[0]
user2 = graph_mgr.users[1]

# Create KML structure
kml = simplekml.Kml()
sat_folder = kml.newfolder(name="Satellites")
users_folder = kml.newfolder(name="Users")  # New folder for users
ground_stations_folder = kml.newfolder(name="Ground Stations")  # New ground stations folder
links_folder = kml.newfolder(name="Ground-Satellite Links")
sat_to_sat_links = kml.newfolder(name="Satellite-to-Satellite Links")

# Add satellites to KML
for sat in all_satellites:
    pnt = sat_folder.newpoint(
        name=f"Sat {sat.satellite_id}",
        coords=[(sat.longitude, sat.latitude, sat.altitude() * 1000)]
    )
    pnt.altitudemode = simplekml.AltitudeMode.absolute
    pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/paddle/wht-blank.png'
    pnt.style.iconstyle.scale = 0.7

# Add users to KML with person icon
for user in graph_mgr.users:  # Assuming you have access to self.users
    user_pnt = users_folder.newpoint(
        name=f"User {user.user_id}",
        coords=[(user.longitude, user.latitude, 0)]
    )
    user_pnt.altitudemode = simplekml.AltitudeMode.absolute
    user_pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/paddle/purple-stars.png'  # Person-like icon
    user_pnt.style.iconstyle.scale = 1.2  # Slightly larger icon

# Add ground stations with tower icon
for gs in graph_mgr.get_ground_stations():  # Assuming you have ground_stations list
    gs_pnt = ground_stations_folder.newpoint(
        name=f"GS-{gs.name}",
        coords=[(gs.longitude, gs.latitude, 0)],
    )
    gs_pnt.altitudemode = simplekml.AltitudeMode.absolute
    gs_pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/communications.png'
    gs_pnt.style.iconstyle.color = simplekml.Color.green
    gs_pnt.style.iconstyle.scale = 1.1

edge_count = {'satellite': 0, 'ground': 0, 'user': 0}

# Step 1: Find closest ground station from the user/source
closest_gs = graph_mgr.find_closest_ground_station(user1)

if closest_gs is not None:
    # Step 2: Find shortest path from source to that ground station
    path, length = graph_mgr.find_shortest_path(source=user1, target=closest_gs)
else:
    path = None

# Convert path to edge set for quick lookup
path_edges = set()
if path:
    for i in range(len(path)-1):
        path_edges.add((path[i], path[i+1]))
        path_edges.add((path[i+1], path[i]))

# In the edge drawing loop, highlight edges in this path as before:

for u, v, data in G.edges(data=True):
    node_u = G.nodes[u]
    node_v = G.nodes[v]
    coords = []

    coord_u = graph_mgr.get_coords(node_u if isinstance(node_u, dict) else u)
    coord_v = graph_mgr.get_coords(node_v if isinstance(node_v, dict) else v)

    if coord_u and coord_v:
        coords = [coord_u, coord_v]
    else:
        continue

    if (u, v) in path_edges or (v, u) in path_edges:
        # Highlight edges in path to closest ground station
        line = links_folder.newlinestring(
            name=f"Path to Closest GS Link {u} to {v}",
            coords=coords
        )
        line.style.linestyle.color = simplekml.Color.blue
        line.style.linestyle.width = 5
        line.altitudemode = simplekml.AltitudeMode.absolute
        line.extrude = 0
        line.tessellate = 1
        continue


# Draw all edges
for u, v, data in G.edges(data=True):
    node_u = G.nodes[u]
    node_v = G.nodes[v]
    coords = []

    coord_u = graph_mgr.get_coords(node_u if isinstance(node_u, dict) else u)
    coord_v = graph_mgr.get_coords(node_v if isinstance(node_v, dict) else v)

    if coord_u and coord_v:
        coords = [coord_u, coord_v]
    else:
        continue

    connection_type = data.get('connection_type', 'unknown')
    distance = data.get('distance', 0)

    if connection_type == 'satellite':
        line = sat_to_sat_links.newlinestring(
            name=f"Sat Link {u} to {v} ({distance:.1f}km)",
            coords=coords
        )
        line.style.linestyle.color = simplekml.Color.red
        edge_count['satellite'] += 1
    elif connection_type == 'ground_station':
        line = links_folder.newlinestring(
            name=f"Ground Link {u} to {v} ({distance:.1f}km)",
            coords=coords
        )
        line.style.linestyle.color = simplekml.Color.green
        edge_count['ground'] += 1
    elif any((isinstance(node, dict) and node.get('type') == 'user') for node in [node_u, node_v]):
        # Assuming you have node_u and node_v from your earlier code
        line = links_folder.newlinestring(
            name=f"User Link {u} to {v} ({distance:.1f}km)",
            coords=coords
        )
        line.style.linestyle.color = simplekml.Color.purple  # Distinct color for user links
        line.style.linestyle.width = 3  # Thicker line for visibility
        edge_count['user'] += 1

        # Common line properties
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
