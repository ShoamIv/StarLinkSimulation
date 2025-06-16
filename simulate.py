from skyfield.api import load, utc
from datetime import datetime, timedelta
import simplekml
import GroundStation
import Satellite
import Graph_Manager
import os
from pathlib import Path
import math

RESOURCES_DIR = Path(__file__).parent / "resources"


def validate_coordinate(coord):
    """Validate that coordinate values are finite and reasonable"""
    if coord is None:
        return False
    if isinstance(coord, (list, tuple)) and len(coord) >= 2:
        lon, lat = coord[0], coord[1]
        alt = coord[2] if len(coord) > 2 else 0

        # Check for valid ranges and finite values
        if (not math.isfinite(lon) or not math.isfinite(lat) or not math.isfinite(alt) or
                abs(lon) > 180 or abs(lat) > 90 or alt < -1000 or alt > 1000000):
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
        # Validate all coordinates in the line
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


# Build the graph manager
graph_mgr = Graph_Manager.GraphManager()

# Prepare time & timescale for simulation steps
ts = load.timescale()
start_time = datetime.utcnow().replace(tzinfo=utc)

# Load ground stations
manager = GroundStation.GroundStationManager()
file_path = RESOURCES_DIR / "ground_stations_global.txt"
manager.load_from_file(file_path)
graph_mgr.add_ground_stations(manager)
graph_mgr.create_users()
G = graph_mgr.get_graph()

# Number of steps & step interval in minutes
num_steps = 3  # Start small for testing
step_minutes = 6

# Create KML container
kml = simplekml.Kml()

print(f"Starting simulation with {num_steps} steps...")

for step in range(num_steps):
    print(f"Processing step {step + 1}/{num_steps}...")

    current_time = start_time + timedelta(minutes=step * step_minutes)
    next_time = current_time + timedelta(minutes=step_minutes)
    skyfield_time = ts.from_datetime(current_time)

    # Define TimeSpan for this time step
    try:
        time_span = simplekml.TimeSpan(
            begin=current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end=next_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    except Exception as e:
        print(f"Error creating timespan for step {step}: {e}")
        continue

    # Clear graph and reload fresh for each time step
    try:
        graph_mgr.clear()
        Satellite.extractor(graph_mgr, ts, skyfield_time)
        all_satellites = graph_mgr.get_satellites()

        # Update satellite positions for current time
        for sat in all_satellites:
            sat.update_position(ts, current_time)

        graph_mgr.add_satellite_to_satellite_edges(ts, skyfield_time)
        graph_mgr.add_ground_to_satellite_edges(ts, skyfield_time)

    except Exception as e:
        print(f"Error building graph for step {step}: {e}")
        continue

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
        coords = [(gs.longitude, gs.latitude, 0)]
        create_point(
            gs_folder, f"GS-{gs.name}", coords,
            'http://maps.google.com/mapfiles/kml/shapes/communications.png',
            simplekml.Color.green, 1.1, time_span
        )

    # Add satellites
    for sat in all_satellites:
        try:
            alt_km = sat.altitude()
            if not math.isfinite(alt_km) or alt_km < 0:
                print(f"Warning: Invalid altitude for satellite {sat.name}: {alt_km}")
                continue

            coords = [(sat.longitude, sat.latitude, alt_km * 1000)]
            create_point(
                sat_folder, f"SAT-{sat.name}", coords,
                'http://maps.google.com/mapfiles/kml/paddle/wht-blank.png',
                simplekml.Color.red, 1.1, time_span
            )
        except Exception as e:
            print(f"Error processing satellite {sat.name}: {e}")
            continue

    # Add users
    for user in graph_mgr.users:
        coords = [(user.longitude, user.latitude, 0)]
        create_point(
            users_folder, f"User {user.user_id}", coords,
            'http://maps.google.com/mapfiles/kml/paddle/purple-stars.png',
            simplekml.Color.purple, 1.2, time_span
        )

    # Add edges / links
    edge_count = 0
    for u, v, data in G.edges(data=True):
        try:
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
                create_line(
                    sat_links_folder, f"Sat Link {u} to {v} ({distance:.1f} km)",
                    coords, simplekml.Color.red, 0.5, time_span
                )
            elif connection_type == 'ground_station':

                create_line(
                    gs_links_folder, f"Ground Link {u} to {v} ({distance:.1f} km)",
                    coords, simplekml.Color.aqua, 0, time_span
                )
            elif any((isinstance(node, dict) and node.get('type') == 'user') for node in [node_u, node_v]):
                create_line(
                    gs_links_folder, f"User Link {u} to {v} ({distance:.1f} km)",
                    coords, simplekml.Color.purple, 3, time_span
                )
            else:
                create_line(
                    gs_links_folder, f"Link {u} to {v} ({distance:.1f} km)",
                    coords, simplekml.Color.gray, 1, time_span
                )

            edge_count += 1
        except Exception as e:
            print(f"Error processing edge {u}-{v}: {e}")
            continue

    print(f"  Added {edge_count} edges for step {step}")

    # Handle shortest path
    if graph_mgr.users:
        try:
            user1 = graph_mgr.users[0]
            path, weight = graph_mgr.find_closest_ground_station(user1)

            if path is not None and len(path) > 1:
                print(f"  Found shortest path with {len(path)} nodes, Weighted: {weight:.1f} latency")

                # Create path segments (avoid duplicates)
                for i in range(len(path) - 1):
                    u, v = path[i], path[i + 1]

                    if u not in G.nodes or v not in G.nodes:
                        continue

                    node_u = G.nodes[u]
                    node_v = G.nodes[v]

                    coord_u = graph_mgr.get_coords(node_u)
                    coord_v = graph_mgr.get_coords(node_v)

                    if not coord_u or not coord_v:
                        continue

                    coords = [coord_u, coord_v]

                    create_line(
                        shortest_path_folder, f"Path Segment {i + 1}: {u} -> {v}",
                        coords, simplekml.Color.blueviolet, 4, time_span
                    )

        except Exception as e:
            print(f"Warning: Could not compute shortest path for step {step}: {e}")

print("Simulation complete, saving final KML...")
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
kml_filename = os.path.join(output_dir, f"satellite_simulation.kml")
kml.save(kml_filename)

print(f"KML file saved as: {kml_filename}")
