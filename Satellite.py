from collections import defaultdict
from pathlib import Path
from typing import List, Optional, Tuple, Set
import numpy as np
import requests
from skyfield.api import EarthSatellite
import random


class Satellite:
    FIXED_SAT_CONNECTIONS = 2
    MAX_SATELLITE_CONNECTIONS = 3
    MAX_GROUND_CONNECTIONS = 1

    CAPACITY_LATENCY_PENALTY_MS = {
        1: 10,
        2: 100,
        3: 500
    }

    TLE_URL = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle'

    def __init__(self, satellite_id: int, earth_satellite: EarthSatellite, name: str, line1: str, line2: str,
                 mean_anomaly, position, orbit_id: Tuple[float, float], neighbors_id: List[int] = None):
        self.satellite_id = satellite_id
        self.earth_satellite = earth_satellite
        self.name = name
        self.line1 = line1
        self.line2 = line2
        self.orbit_id = orbit_id
        self.mean_anomaly = mean_anomaly
        self.neighbors_id = neighbors_id if neighbors_id is not None else []
        self.inclination = np.degrees(earth_satellite.model.inclo)
        self.raan = np.degrees(earth_satellite.model.nodeo)
        self.position = position  # (lat, lon, alt)
        self.velocity = None  # km/s
        self.connected_satellites: Set[int] = set()  # Currently connected satellites
        self.connected_ground_stations: Set[str] = set()  # Currently connected ground stations
        self.number_of_users = random.uniform(1, 2000)

    def altitude(self) -> Optional[float]:
        return self.position.elevation.km if self.position else None

    @property
    def latitude(self) -> Optional[float]:
        """Return latitude in degrees if position is available."""
        return self.position.latitude.degrees if self.position else None

    @property
    def longitude(self) -> Optional[float]:
        """Return longitude in degrees if position is available."""
        return self.position.longitude.degrees if self.position else None

    def update_position(self, ts, time_utc):
        """Update satellite's ECEF position and velocity."""
        t = ts.utc(time_utc)
        geocentric = self.earth_satellite.at(t)
        self.position = geocentric.subpoint()
        self.velocity = geocentric.velocity.km_per_s

    def get_capacity(self):
        if self.number_of_users <= 500:
            return 1
        elif 500 < self.number_of_users < 1500:
            return 2
        else:  # 1500 or more
            return 3

    def can_connect_satellite(self) -> bool:
        """Check if satellite can accept another satellite connection."""
        return len(self.connected_satellites) < self.MAX_SATELLITE_CONNECTIONS

    def can_connect_ground_station(self) -> bool:
        """Check if satellite can accept another ground station connection."""
        return len(self.connected_ground_stations) < self.MAX_GROUND_CONNECTIONS

    def connect_satellite(self, satellite_id: int):
        """Add a satellite connection."""
        if self.can_connect_satellite():
            self.connected_satellites.add(satellite_id)

    def disconnect_satellite(self, satellite_id: int):
        """Remove a satellite connection."""
        self.connected_satellites.discard(satellite_id)

    def connect_ground_station(self, ground_station_id: str):
        """Add a ground station connection."""
        if self.can_connect_ground_station():
            self.connected_ground_stations.add(ground_station_id)

    def disconnect_ground_station(self, ground_station_id: str):
        """Remove a ground station connection."""
        self.connected_ground_stations.discard(ground_station_id)

    def get_latency_penalty(self) -> int:
        """Get latency penalty based on capacity level."""
        return self.CAPACITY_LATENCY_PENALTY_MS.get(self.capacity_level, 0)

    def reset_connections(self):
        """Call this before each new simulation step to clear old connections."""
        self.connected_satellites.clear()
        self.connected_ground_stations.clear()

    @staticmethod
    def download_tle_data(url: str) -> List[str]:
        """
        Fetches TLE data from Celestrak unless 'gp.php' already exists in the resources folder.

        Args:
            url (str): The URL to fetch TLE data from.

        Returns:
            List[str]: A list of strings, where each string is a line from the TLE file.

        Raises:
            requests.exceptions.RequestException: If the HTTP request fails.
        """
        # Define the path to the resources folder
        resources_dir = Path(__file__).parent / "resources"
        resources_dir.mkdir(exist_ok=True)  # Ensure the directory exists
        tle_file = resources_dir / "gp.php"

        # Check if the file already exists
        if tle_file.exists():
            print(f"{tle_file} already exists. Skipping download.")
            with open(tle_file, "r") as file:
                return file.read().strip().splitlines()

        # Download the file if it doesn't exist
        response = requests.get(url)
        response.raise_for_status()

        # Save the file to the resources folder
        with open(tle_file, "w") as file:
            file.write(response.text)

        return response.text.strip().splitlines()

    @staticmethod
    def parse_tle_lines(lines: List[str], ts, skyfield_time) -> List['Satellite']:
        """
        Parses TLEs into Satellite objects with orbital parameters.
        Only includes satellites currently above the USA.

        Args:
            lines (List[str]): A list of TLE data lines.
            ts: A Skyfield timescale object.
            skyfield_time: Time at which to compute the subpoint.

        Returns:
            List[Satellite]: Satellites currently over the USA.
        """
        satellites = []
        satellite_id = 0

        # Rough bounding box for continental USA
        min_lat, max_lat = 24.396308, 49.384358  # from Florida Keys to northern border
        min_lon, max_lon = -125.0, -66.93457  # from West Coast to East Coast
        count = 0
        for i in range(0, len(lines), 3):
            if count >= 50:
                break
            if i + 2 >= len(lines):
                continue
            name = lines[i].strip()
            line1 = lines[i + 1].strip()
            line2 = lines[i + 2].strip()

            try:
                sat_obj = EarthSatellite(line1, line2, name, ts)
                subpoint = sat_obj.at(skyfield_time).subpoint()
                lat, lon = subpoint.latitude.degrees, subpoint.longitude.degrees

                # Check if satellite is over the USA
                if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                    inclination = np.degrees(sat_obj.model.inclo)
                    raan = np.degrees(sat_obj.model.nodeo)
                    orbit_id = (round(inclination, 1), round(raan / 10) * 10)
                    mean_anomaly = np.degrees(sat_obj.model.mo)

                    satellite = Satellite(
                        satellite_id=satellite_id,
                        earth_satellite=sat_obj,
                        name=name,
                        line1=line1,
                        line2=line2,
                        orbit_id=orbit_id,
                        mean_anomaly=mean_anomaly,
                        neighbors_id=[],
                        position=subpoint
                    )
                    satellites.append(satellite)
                    satellite_id += 1
                    count +=1
            except Exception as e:
                print(f"Skipping malformed TLE {name}: {e}")

        return satellites

    @staticmethod
    def group_by_orbit(sats: List['Satellite'], graph_manager, skyfield_time) -> List['Satellite']:
        """
        Groups satellites by orbit, adds orbit_id to each satellite, and assigns neighbor_ids.
        Each satellite can have up to 2 neighbors: forward and backward in its plane.
        """
        planes = defaultdict(list)
        # Group by orbit_id
        for sat in sats:
            planes[sat.orbit_id].append(sat)

        for orbit_sats in planes.values():
            if len(orbit_sats) < 2:
                for sat in orbit_sats:
                    sat.neighbors_id = []
                continue

            # Sort by mean anomaly
            sorted_sats = sorted(orbit_sats, key=lambda s: s.mean_anomaly)

            for i, sat in enumerate(sorted_sats):
                sat.neighbors_id = []

                # Get previous and next satellite in the plane
                neighbors = [
                    sorted_sats[(i - 1) % len(sorted_sats)],
                    sorted_sats[(i + 1) % len(sorted_sats)]
                ]

                for neighbor_sat in neighbors:

                    if graph_manager.satellite_to_satellite_los(sat.earth_satellite,
                                                                neighbor_sat.earth_satellite, skyfield_time):
                        sat.neighbors_id.append(neighbor_sat.satellite_id)
                        graph_manager.add_orbit_edge(sat, neighbor_sat, skyfield_time)
                    # Limit to max 2 neighbors
                    if len(sat.neighbors_id) == 2:
                        break

        return sats

    @classmethod
    def extractor(cls, graph_manager, ts, skyfield_time):
        """
        Main function to download and process TLE data
        Returns:
            List[Satellite]: Ready-to-use list of Satellite objects
        """
        print("Downloading TLE data...")
        tle_lines = cls.download_tle_data(cls.TLE_URL)

        print("Parsing TLEs...")
        satellites_data = cls.parse_tle_lines(tle_lines, ts, skyfield_time)
        graph_manager.add_satellites(satellites_data)
        print("Grouping satellites by orbit and assigning neighbors...")
        satellites_with_neighbors = cls.group_by_orbit(satellites_data, graph_manager, skyfield_time)
        print(f"Successfully created {len(satellites_with_neighbors)} Satellite objects")
    # Module-level convenience function


def extractor(graph_manager, ts, skyfield_time):
    """Convenience function to call Satellite.extractor() at module level."""
    Satellite.extractor(graph_manager, ts, skyfield_time)
