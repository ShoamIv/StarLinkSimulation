class GroundStation:
    def __init__(self, name, latitude, longitude):
        self.name = name
        self.latitude = latitude
        self.longitude = longitude

    def __repr__(self):
        return f"GroundStation(name='{self.name}', latitude={self.latitude}, longitude={self.longitude})"


class GroundStationManager:
    def __init__(self):
        self.stations = {}

    def load_from_file(self, filepath):
        with open(filepath, 'r') as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue  # skip empty lines

                # Example line: StationA: (31.7683, 35.2137)
                try:
                    name_part, coord_part = line.split(':')
                    name = name_part.strip()
                    # Remove parentheses and split by comma
                    coords = coord_part.strip().strip('()').split(',')
                    latitude = float(coords[0].strip())
                    longitude = float(coords[1].strip())

                    # Create GroundStation and store
                    self.stations[name] = GroundStation(name, latitude, longitude)
                except Exception as e:
                    print(f"Skipping invalid line: {line} ({e})")

    def get_station(self, name):
        return self.stations.get(name)

    def all_stations(self):
        return list(self.stations.values())
