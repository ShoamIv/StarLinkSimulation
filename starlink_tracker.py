# starlink_tracker.py
# This script continuously generates a KML file with Starlink satellite
# positions and ground station locations, designed to be refreshed by Google Earth Pro.

import simplekml
from skyfield.api import load, utc, EarthSatellite
from datetime import datetime, timedelta
import time
import os # For path manipulation and checking file existence

# Import the GroundStation module
try:
    import GroundStation
except ImportError:
    print("Error: GroundStation.py not found. Please ensure it's in the same directory.")
    print("Exiting.")
    exit()

# --- Configuration ---
TLE_URL = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle'
GROUND_STATIONS_FILE = 'ground_stations.txt'
KML_OUTPUT_FILE = 'dynamic_starlink.kml'
UPDATE_INTERVAL_SECONDS = 10  # How often the KML file is updated (e.g., 10 seconds)
PATH_DURATION_MINUTES = 10    # How many minutes of past path to show for each satellite
PATH_STEP_SECONDS = 30        # Step size for generating satellite paths (e.g., every 30 seconds)

# --- Initialize Skyfield timescale ---
ts = load.timescale()

# --- Load Starlink satellites ---
def load_satellites():
    """Loads Starlink satellite TLE data from Celestrak."""
    print(f"Attempting to load Starlink TLE data from {TLE_URL}...")
    try:
        satellites = load.tle_file(TLE_URL, reload=True) # reload=True ensures fresh data
        print(f"Loaded {len(satellites)} Starlink satellites.")
        return satellites
    except Exception as e:
        print(f"Error loading TLE data: {e}")
        print("Retrying in 5 seconds...")
        time.sleep(5)
        return [] # Return empty list to indicate failure, loop will retry

# --- Load ground stations ---
manager = GroundStation.GroundStationManager()
if not os.path.exists(GROUND_STATIONS_FILE):
    print(f"Warning: '{GROUND_STATIONS_FILE}' not found. Creating a default one.")
    # Create a default ground_stations.txt in the format your GroundStation.py expects
    with open(GROUND_STATIONS_FILE, 'w') as f:
        f.write("My Home: (32.7940, 34.9896)\n")
        f.write("New York: (40.7128, -74.0060)\n")
        f.write("London: (51.5074, -0.1278)\n")
        f.write("Tokyo: (35.6895, 139.6917)\n")
print(f"Loading ground stations from {GROUND_STATIONS_FILE}...")
manager.load_from_file(GROUND_STATIONS_FILE)
if not manager.all_stations():
    print("No ground stations loaded. Please check 'ground_stations.txt' format.")

# --- Main KML Generation Loop ---
def generate_kml_update(satellites_data: list[EarthSatellite], ground_stations: list[GroundStation.GroundStation]):
    """
    Generates a KML document with current satellite positions and paths,
    and static ground station locations.
    """
    kml = simplekml.Kml()

    # Add ground stations to KML (static points)
    # Using the structure from your GroundStation.py
    for station in ground_stations:
        p = kml.newpoint(name=f"Ground Station: {station.name}",
                         coords=[(station.longitude, station.latitude)]) # No elevation in your GS class
        p.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/pushpin/grn-pushpin.png' # Green pushpin
        p.style.iconstyle.scale = 1.2
        p.style.labelstyle.scale = 1.2
        p.altitudemode = simplekml.AltitudeMode.clamptoground # Clamped to ground since no elevation specified

    # Get current time for satellite positions
    now = datetime.utcnow().replace(tzinfo=utc)
    t_now = ts.from_datetime(now)

    # Add satellite positions and paths to KML
    for sat in satellites_data:
        try:
            # Current position
            geo_current = sat.at(t_now).subpoint()
            lon_current = geo_current.longitude.degrees
            lat_current = geo_current.latitude.degrees
            alt_current = geo_current.elevation.km

            # Create a Placemark for the current satellite position
            p_current = kml.newpoint(name=f"Satellite: {sat.name}",
                                     coords=[(lon_current, lat_current, alt_current * 1000)]) # KML expects meters
            p_current.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png' # Circle icon
            p_current.style.iconstyle.scale = 0.8
            p_current.style.labelstyle.scale = 0.8
            p_current.altitudemode = simplekml.AltitudeMode.absolute # Interpret altitude as absolute

            # Generate path for the last PATH_DURATION_MINUTES
            path_coords = []
            start_time = now - timedelta(minutes=PATH_DURATION_MINUTES)
            current_path_time = start_time
            while current_path_time <= now:
                t_path = ts.from_datetime(current_path_time)
                geo_path = sat.at(t_path).subpoint()
                path_coords.append((geo_path.longitude.degrees, geo_path.latitude.degrees, geo_path.elevation.km * 1000))
                current_path_time += timedelta(seconds=PATH_STEP_SECONDS)

            # Create a Placemark for the satellite's path
            ls = kml.newlinestring(name=f"{sat.name} Path",
                                   coords=path_coords)
            ls.style.linestyle.width = 2
            ls.style.linestyle.color = simplekml.Color.blue # Blue path
            ls.altitudemode = simplekml.AltitudeMode.absolute # Interpret altitude as absolute

        except Exception as e:
            # This can happen if TLE data is bad or satellite is out of range
            # print(f"Error processing satellite {sat.name}: {e}") # Uncomment for detailed error logging
            continue # Skip to the next satellite

    # Save the KML file
    try:
        kml.save(KML_OUTPUT_FILE)
        print(f"KML file '{KML_OUTPUT_FILE}' updated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"Error saving KML file: {e}")

# --- Main execution loop ---
if __name__ == "__main__":
    current_satellites = []
    while True:
        # Reload satellites periodically in case TLEs change or to refresh data
        if not current_satellites: # Only try to load if empty (e.g., on startup or after an error)
            current_satellites = load_satellites()
            if not current_satellites:
                print("No satellites loaded. Retrying TLE download...")
                time.sleep(UPDATE_INTERVAL_SECONDS)
                continue

        if manager.all_stations():
            generate_kml_update(current_satellites, manager.all_stations())
        else:
            print("No ground stations available to display. Please check 'ground_stations.txt'.")

        time.sleep(UPDATE_INTERVAL_SECONDS)

