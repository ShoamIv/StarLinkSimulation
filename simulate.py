import networkx as nx
from skyfield.api import load, utc, Topos
from datetime import datetime, timedelta
import simplekml

import GroundStation
from Satellite import Satellite
from graph_actions import graph_actions  # Your graph manager

# Load satellite TLE data
tle_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle'
skyfield_satellites = load.tle_file(tle_url)

# Load ground stations
manager = GroundStation.GroundStationManager()
manager.load_from_file('ground_stations_global.txt')

# Prepare times
ts = load.timescale()
start_time = datetime.utcnow().replace(tzinfo=utc)

# Initialize satellites
my_sats = []
for idx, sky_sat in enumerate(skyfield_satellites[:50]):
    sat = Satellite(satellite_id=idx)
    sat.update_position(sky_sat, ts, start_time)
    my_sats.append(sat)

# Create KML
kml = simplekml.Kml()

# Simulate for 1 hour in 10 steps (every 6 minutes)
for step in range(10):
    current_time = start_time + timedelta(minutes=step * 6)
    t = ts.from_datetime(current_time)

    # Update satellite positions
    for idx, sat in enumerate(my_sats):
        sat.update_position(skyfield_satellites[idx], ts, current_time)

    # Build graph
    graph_mgr = graph_actions()
    graph_mgr.add_ground_stations(manager)
    graph_mgr.add_satellites(my_sats)

    for sat in my_sats:
        sat.reset_connections()

    graph_mgr.add_visible_edges(skyfield_satellites, t)
    G = graph_mgr.get_graph()

    # KML folders
    folder = kml.newfolder(name=f"Step {step} - {current_time.strftime('%H:%M')}")
    gs_folder = folder.newfolder(name="Ground Stations")
    sat_folder = folder.newfolder(name="Satellites")
    links_folder = folder.newfolder(name="Visible Links")

    for node_name, data in G.nodes(data=True):
        if data['type'] == 'ground_station':
            gs = data['obj']
            pnt = gs_folder.newpoint(name=gs.name,
                                     coords=[(gs.longitude, gs.latitude)])
            pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png'

        elif data['type'] == 'satellite':
            sat = data['obj']
            pnt = sat_folder.newpoint(name=f"Sat {sat.satellite_id}",
                                      coords=[(sat.longitude, sat.latitude, sat.altitude * 1000)])
            pnt.altitudemode = simplekml.AltitudeMode.absolute
            pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/paddle/wht-blank.png'
            pnt.style.iconstyle.scale = 0.7

    for u, v in G.edges():
        data_u = G.nodes[u]
        data_v = G.nodes[v]
        coords = []
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

# Camera
kml.document.camera = simplekml.Camera(
    longitude=0, latitude=0, altitude=50000 * 1000,
    heading=0, tilt=90, roll=0,
    altitudemode=simplekml.AltitudeMode.absolute
)

filename = f"starlink_sim_1hr_{start_time.strftime('%Y%m%d_%H%M')}.kml"
kml.save(filename)
print(f"KML saved: {filename}")
