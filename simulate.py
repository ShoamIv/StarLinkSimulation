from skyfield.api import load, utc, Topos
from datetime import datetime, timedelta
import simplekml
import GroundStation
import Satellite
import Graph_Manager
from typing import List
import os

# Build the graph
graph_mgr = Graph_Manager.GraphManager()
# Prepare time (single snapshot)
ts = load.timescale()
current_time = datetime.utcnow().replace(tzinfo=utc)
skyfield_time = ts.from_datetime(current_time)

# Load ground stations
manager = GroundStation.GroundStationManager()
manager.load_from_file('ground_stations_global.txt')
graph_mgr.add_ground_stations(manager)
Satellite.extractor(graph_mgr, ts, skyfield_time)
all_satellites = graph_mgr.get_satellites()
G = graph_mgr.get_graph()

print(f"Total satellites loaded: {len(all_satellites)}")
# Create KML
kml = simplekml.Kml()
all_satellites = all_satellites[:50]
# Simulation loop
for step in range(10):
    current_time = current_time + timedelta(minutes=step * 6)

    # Update positions and build graph
    for sat in all_satellites:
        sat.update_position(ts, current_time)

    graph_mgr = Graph_Manager.GraphManager()
    graph_mgr.add_ground_stations(manager)
    graph_mgr.add_satellites(all_satellites)

    #for sat in all_satellites:
        #sat.reset_connections()

    # Get the graph instance
    G = graph_mgr.get_graph()

    # Add neighbor connections as edges
    for sat in all_satellites:
        sat_node = f"Satellite_{sat.satellite_id}"

        # Only proceed if this satellite exists in the graph
        if not G.has_node(sat_node):
            continue

        for neighbor_id in sat.neighbors_id:
            neighbor_node = f"Satellite_{neighbor_id}"

            # Check if neighbor exists in our satellite list and in the graph
            neighbor_exists = any(s.satellite_id == neighbor_id for s in all_satellites)
            if not neighbor_exists or not G.has_node(neighbor_node):
                continue

            # Get both satellite objects
            neighbor = next(s for s in all_satellites if s.satellite_id == neighbor_id)
            # Add edge with attributes
            G.add_edge(sat_node, neighbor_node,
                       weight=1000,  # weight in km
                       distance=100,
                       signal_strength=1.0,
                       connection_type='neighbor',
                       time_step=step)

    # KML visualization
    folder = kml.newfolder(name=f"Step {step} - {current_time.strftime('%H:%M')}")
    gs_folder = folder.newfolder(name="Ground Stations")
    sat_folder = folder.newfolder(name="Satellites")
    links_folder = folder.newfolder(name="Visible Links")
    neighbor_links_folder = folder.newfolder(name="Neighbor Links")

    # Add ground stations to KML
    #for gs in manager.ground_stations:
     #   pnt = gs_folder.newpoint(name=gs.name,
      #                           coords=[(gs.longitude, gs.latitude)])
       # pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png'
       # pnt.timestamp.when = current_time.isoformat()

    # Add satellites to KML
    for sat in all_satellites:
        pnt = sat_folder.newpoint(name=f"Sat {sat.satellite_id}",
                                  coords=[(sat.longitude, sat.latitude, sat.altitude * 1000)])
        pnt.altitudemode = simplekml.AltitudeMode.absolute
        pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/paddle/wht-blank.png'
        pnt.style.iconstyle.scale = 0.7
        pnt.timestamp.when = current_time.isoformat()

    # Draw all edges from the graph
    for u, v, data in G.edges(data=True):
        node_u = G.nodes[u]
        node_v = G.nodes[v]
        coords = []

        # Get coordinates for both nodes
        for node_data in (node_u, node_v):
            if node_data['type'] == 'ground_station':
                gs = node_data['obj']
                coords.append((gs.longitude, gs.latitude, 0))
            elif node_data['type'] == 'satellite':
                sat_obj = node_data['obj']
                coords.append((sat_obj.longitude, sat_obj.latitude, sat_obj.altitude * 1000))

        if len(coords) != 2:
            continue

        # Create the appropriate link based on connection type
        if data.get('connection_type') == 'neighbor':
            line = neighbor_links_folder.newlinestring(name=f"{u} to {v}", coords=coords)
            line.style.linestyle.color = simplekml.Color.blue
            line.style.linestyle.width = 2
        else:  # ground connections
            a=1
            #line = links_folder.newlinestring(name=f"{u} to {v}", coords=coords)
            #line.style.linestyle.color = simplekml.Color.green
            #line.style.linestyle.width = 1

        # Common line properties
        line.altitudemode = simplekml.AltitudeMode.absolute
        line.extrude = 0
        line.tessellate = 1
        line.timespan.begin = current_time.isoformat()
        line.timespan.end = (current_time + timedelta(minutes=6)).isoformat()

# Save KML file
output_dir = "output"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
kml_filename = os.path.join(output_dir, f"starlink_simulation_{timestamp}.kml")
kml.save(kml_filename)
print(f"KML file saved as: {kml_filename}")