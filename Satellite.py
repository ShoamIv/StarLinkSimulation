import numpy as np
from skyfield.api import EarthSatellite, load
from datetime import datetime


class Satellite:
    MAX_SATELLITE_CONNECTIONS = 2
    MAX_GROUND_CONNECTIONS = 2

    def __init__(self, satellite_id: int, latitude: float = None, longitude: float = None, altitude: float = None,
                 sat_xyz=None, total_flow=None):
        self.satellite_id = satellite_id
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.sat_xyz = np.array(sat_xyz) if sat_xyz is not None else None
        self.total_flow = total_flow
        self.connected_users = 0
        self.connected_sats = []  # list of Satellite IDs
        self.connected_gs = []    # list of Ground Station IDs (or names/objects)

    def is_above_threshold(self, threshold_km: float = 350) -> bool:
        return (self.altitude is not None) and (self.altitude > threshold_km)

    def update_position(self, satellite: EarthSatellite, ts, time_utc: datetime):
        t = ts.utc(time_utc)
        geocentric = satellite.at(t)
        subpoint = geocentric.subpoint()

        self.latitude = subpoint.latitude.degrees
        self.longitude = subpoint.longitude.degrees
        self.altitude = subpoint.elevation.km
        self.sat_xyz = np.array(geocentric.position.km)

    def can_connect_satellite(self) -> bool:
        return len(self.connected_sats) < self.MAX_SATELLITE_CONNECTIONS

    def can_connect_ground_station(self) -> bool:
        return len(self.connected_gs) < self.MAX_GROUND_CONNECTIONS

    def connect_satellite(self, other_sat_id: int) -> bool:
        if self.can_connect_satellite() and other_sat_id not in self.connected_sats:
            self.connected_sats.append(other_sat_id)
            return True
        return False

    def disconnect_satellite(self, other_sat_id: int):
        if other_sat_id in self.connected_sats:
            self.connected_sats.remove(other_sat_id)

    def connect_ground_station(self, ground_station_id: int) -> bool:
        if self.can_connect_ground_station() and ground_station_id not in self.connected_gs:
            self.connected_gs.append(ground_station_id)
            return True
        return False

    def disconnect_ground_station(self, ground_station_id: int):
        if ground_station_id in self.connected_gs:
            self.connected_gs.remove(ground_station_id)

    def __str__(self):
        return (
            f"Satellite ID: {self.satellite_id}, "
            f"Latitude: {self.latitude:.4f}, "
            f"Longitude: {self.longitude:.4f}, "
            f"Altitude: {self.altitude:.2f} km, "
            f"XYZ Coordinates: {self.sat_xyz}, "
            f"Connected Sats: {self.connected_sats}, "
            f"Connected GS: {self.connected_gs}"
        )

    def reset_connections(self):
        """
        Call this before each new simulation step to clear old connections.
        """
        self.connected_sats.clear()
        self.connected_gs.clear()
