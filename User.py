import networkx as nx


class User:
    def __init__(self, user_id, latitude, longitude):
        self.user_id = user_id
        self.latitude = latitude
        self.longitude = longitude


    def __str__(self):
        return f'{self.user_id}, {self.latitude}, {self.longitude}'
