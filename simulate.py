from skyfield.api import load, utc
from datetime import datetime, timedelta
import simplekml
import GroundStation
import Satellite
import Graph_Manager
import os
from pathlib import Path

RESOURCES_DIR = Path(__file__).parent / "resources"

# Build the graph manager
graph_mgr = Graph_Manager.GraphManager()

# Prepare time & timescale for simulation steps
ts = load.timescale()
start_time = datetime.utcnow().replace(tzinfo=utc)

# Load ground stations
manager = GroundStation.GroundStationManager()
file_path = RESOURCES_DIR / "ground_stations_global.txt"
manager.load_from_file(file_path)

# Number of steps & step interval in minutes
num_steps = 10
step_minutes = 6

# Create KML container
kml = simplekml.Kml()

for step in range(num_steps):
    current_time = start_time + timedelta(minutes=step * step_minutes)
    next_time = current_time + timedelta(minutes=step_minutes)
    skyfield_time = ts.from_datetime(current_time)

    # Define TimeSpan for this time step
    time_span = simplekml.TimeSpan(
        begin=current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end=next_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    # Clear graph and reload fresh for each time step (if needed)
    graph_mgr.clear()  # Add this method if you want to reset the graph each step
    graph_mgr.add_ground_stations(manager)
    Satellite.extractor(graph_mgr, ts, skyfield_time)
    all_satellites = graph_mgr.get_satellites()

    # Update satellite positions for current time
    for sat in all_satellites:
        sat.update_position(ts, current_time)

    graph_mgr.add_satellite_to_satellite_edges(ts, skyfield_time)
    graph_mgr.add_ground_to_satellite_edges(ts, skyfield_time)

    graph_mgr.create_users()
    G = graph_mgr.get_graph()

    # Create a KML folder per step/time
    step_folder = kml.newfolder(name=f"Step {step} - {current_time.strftime('%Y-%m-%d %H:%M UTC')}")

    # Subfolders for better organization
    gs_folder = step_folder.newfolder(name="Ground Stations")
    sat_folder = step_folder.newfolder(name="Satellites")
    users_folder = step_folder.newfolder(name="Users")
    gs_links_folder = step_folder.newfolder(name="Ground-Satellite Links")
    sat_links_folder = step_folder.newfolder(name="Satellite-to-Satellite Links")
    shortest_path_folder = step_folder.newfolder(name="Shortest Path")

    # Add ground stations
    for gs in graph_mgr.get_ground_stations():
        pnt = gs_folder.newpoint(
            name=f"GS-{gs.name}",
            coords=[(gs.longitude, gs.latitude, 0)]
        )
        pnt.altitudemode = simplekml.AltitudeMode.absolute
        pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/communications.png'
        pnt.style.iconstyle.color = simplekml.Color.green
        pnt.style.iconstyle.scale = 1.1
        pnt.timespan = time_span  # ✅ Apply time span

    # Add satellites
    for gs in graph_mgr.get_ground_stations():
        pnt = gs_folder.newpoint(
            name=f"GS-{gs.name}",
            coords=[(gs.longitude, gs.latitude, 0)]
        )
        pnt.altitudemode = simplekml.AltitudeMode.absolute
        pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/communications.png'
        pnt.style.iconstyle.color = simplekml.Color.green
        pnt.style.iconstyle.scale = 1.1
        pnt.timespan = time_span  # ✅ Apply time span

    # Add users
    for user in graph_mgr.users:
        user_pnt = users_folder.newpoint(
            name=f"User {user.user_id}",
            coords=[(user.longitude, user.latitude, 0)]
        )
        user_pnt.altitudemode = simplekml.AltitudeMode.absolute
        user_pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/paddle/purple-stars.png'
        user_pnt.style.iconstyle.scale = 1.2
        user_pnt.timespan = time_span  # ✅ Apply time span

    # Add edges / links
    for u, v, data in G.edges(data=True):
        node_u = G.nodes[u]
        node_v = G.nodes[v]

        coord_u = graph_mgr.get_coords(node_u)
        coord_v = graph_mgr.get_coords(node_v)

        if not coord_u or not coord_v:
            continue

        coords = [coord_u, coord_v]

        connection_type = data.get('connection_type', 'unknown')
        distance = data.get('distance', 0)

        if connection_type == 'satellite':
            line = sat_links_folder.newlinestring(
                name=f"Sat Link {u} to {v} ({distance:.1f} km)",
                coords=coords
            )
            line.style.linestyle.color = simplekml.Color.red
            line.style.linestyle.width = 1
        elif connection_type == 'ground_station':
            line = gs_links_folder.newlinestring(
                name=f"Ground Link {u} to {v} ({distance:.1f} km)",
                coords=coords
            )
            line.style.linestyle.color = simplekml.Color.green
            line.style.linestyle.width = 1
        elif any((isinstance(node, dict) and node.get('type') == 'user') for node in [node_u, node_v]):
            line = gs_links_folder.newlinestring(
                name=f"User Link {u} to {v} ({distance:.1f} km)",
                coords=coords
            )
            line.style.linestyle.color = simplekml.Color.purple
            line.style.linestyle.width = 3
        else:
            # Other types of links (optional)
            line = gs_links_folder.newlinestring(
                name=f"Link {u} to {v} ({distance:.1f} km)",
                coords=coords
            )
            line.style.linestyle.color = simplekml.Color.gray
            line.style.linestyle.width = 1

        line.altitudemode = simplekml.AltitudeMode.absolute
        line.extrude = 0
        line.tessellate = 1
        line.timespan = time_span

    if graph_mgr.users:
        user1 = graph_mgr.users[0]
        closest_gs = graph_mgr.find_closest_ground_station(user1)

        if closest_gs is not None:
            path, length = graph_mgr.find_shortest_path(source=user1, target=closest_gs)
        else:
            path = None

        if path:
            path_edges = set()
            for i in range(len(path)-1):
                path_edges.add((path[i], path[i+1]))
                path_edges.add((path[i+1], path[i]))

            for (u, v) in path_edges:
                #node_u = implement here get node same to node_v
                node_v = graph_mgr.get_coords(v)
                coords = [(node_u.longitude, node_u.latitude, node_u.altitude() * 1000),
                          (node_v.longitude, node_v.latitude, node_v.altitude() * 1000)]

                line = shortest_path_folder.newlinestring(
                    name=f"Path {u} -> {v}",
                    coords=coords
                )
                line.style.linestyle.color = simplekml.Color.yellow  # ✅ Different color
                line.style.linestyle.width = 3  # ✅ Thicker
                line.altitudemode = simplekml.AltitudeMode.absolute
                line.extrude = 0
                line.tessellate = 1
                line.timespan = time_span


# Optional: Set a camera for the whole KML
kml.document.camera = simplekml.Camera(
    longitude=0, latitude=0, altitude=50000 * 1000,
    heading=0, tilt=90, roll=0,
    altitudemode=simplekml.AltitudeMode.absolute
)

# Save KML file
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)
timestamp = start_time.strftime("%Y%m%d_%H%M%S")
kml_filename = os.path.join(output_dir, f"satellite_sim_{timestamp}.kml")
kml.save(kml_filename)

print(f"KML file saved as: {kml_filename}")
