import networkx as nx
from skyfield.api import load, utc, Topos
from datetime import datetime
import simplekml

import GroundStation
from Satellite import Satellite
from graph_actions import graph_actions  # The class you asked for

# Load TLE data for Starlink satellites
tle_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle'
skyfield_satellites = load.tle_file(tle_url)

# Load ground stations
manager = GroundStation.GroundStationManager()
manager.load_from_file('ground_stations.txt')

# Prepare time
ts = load.timescale()
now = datetime.utcnow().replace(tzinfo=utc)
t = ts.from_datetime(now)

# Initialize satellites list and update positions
my_sats = []
for idx, sky_sat in enumerate(skyfield_satellites[:50]):  # limit to first 50 for performance
    sat = Satellite(satellite_id=idx)
    sat.update_position(sky_sat, ts, now)
    my_sats.append(sat)

# Initialize graph manager and build graph
graph_mgr = graph_actions()

# Add ground stations and satellites as nodes
graph_mgr.add_ground_stations(manager)
graph_mgr.add_satellites(my_sats)

# Add visible edges (sat-sat and sat-groundstation)
graph_mgr.add_visible_edges(skyfield_satellites, t)

G = graph_mgr.get_graph()
print(f"Graph created with {len(G.nodes)} nodes and {len(G.edges)} edges")

# --- KML Generation ---
kml = simplekml.Kml()

# Folder for ground stations
gs_folder = kml.newfolder(name="Ground Stations")
for node_name, data in G.nodes(data=True):
    if data['type'] == 'ground_station':
        gs = data['obj']
        pnt = gs_folder.newpoint(name=gs.name,
                                 coords=[(gs.longitude, gs.latitude)])
        pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png'
        pnt.description = f"Latitude: {gs.latitude:.4f}\nLongitude: {gs.longitude:.4f}"

# Folder for satellites
sat_folder = kml.newfolder(name="Satellites")
for node_name, data in G.nodes(data=True):
    if data['type'] == 'satellite':
        sat = data['obj']
        pnt = sat_folder.newpoint(name=f"Sat {sat.satellite_id}",
                                 coords=[(sat.longitude, sat.latitude, sat.altitude * 1000)])  # meters
        pnt.altitudemode = simplekml.AltitudeMode.absolute
        pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/paddle/wht-blank.png'
        pnt.style.iconstyle.scale = 0.7
        pnt.description = (f"Satellite ID: {sat.satellite_id}\n"
                           f"Latitude: {sat.latitude:.4f}\n"
                           f"Longitude: {sat.longitude:.4f}\n"
                           f"Altitude: {sat.altitude:.2f} km")

# Folder for visible links
links_folder = kml.newfolder(name="Visible Links")
for u, v in G.edges():
    data_u = G.nodes[u]
    data_v = G.nodes[v]

    coords = []
    # Get coordinates in (lon, lat, alt) format
    for node_data in (data_u, data_v):
        if node_data['type'] == 'ground_station':
            coords.append((node_data['longitude'], node_data['latitude'], 0))
        elif node_data['type'] == 'satellite':
            coords.append((node_data['longitude'], node_data['latitude'], node_data['altitude'] * 1000))

    if len(coords) == 2:
        line = links_folder.newlinestring(name=f"{u} to {v}", coords=coords)
        line.altitudemode = simplekml.AltitudeMode.absolute
        line.extrude = 0
        line.tessellate = 1
        line.style.linestyle.width = 1
        line.style.linestyle.color = simplekml.Color.green

# Add camera looking from space
camera = simplekml.Camera(
    longitude=0,
    latitude=0,
    altitude=50000 * 1000,  # 50,000 km
    heading=0,
    tilt=90,
    roll=0,
    altitudemode=simplekml.AltitudeMode.absolute
)
kml.document.camera = camera

kml_filename = f"satellite_ground_station_links_{now.strftime('%Y%m%d_%H%M')}.kml"
kml.save(kml_filename)
print(f"KML file '{kml_filename}' created successfully. Open it with Google Earth.")
