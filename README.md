# 🌍 Starlink Satellite Network Simulator #

Simulate and visualize dynamic Starlink satellite connectivity with shortest path discovery between users and ground stations. Outputs to animated KML for playback in Google Earth.

## Overview ##

This project simulates the real-time motion of Starlink satellites and models a dynamic communication graph that connects:

#### Users (on Earth)

#### Ground stations

#### Satellites

### The simulation:

Calculates satellite positions using Skyfield

Dynamically rebuilds the network graph at each time step

Identifies the shortest communication path from a user to the nearest ground station via satellites

Exports all visualizations to a time-aware .kml file for playback in Google Earth

## 📁 Folder Structure ##

StarLinkSimulator/
│
├── Graph_Manager.py           # Manages dynamic graph construction and pathfinding
├── GroundStation.py           # Ground station data and loader
├── Satellite.py               # Satellite object and TLE-based positioning
├── User.py                    # User representation
├── simulate.py                # Main KML simulation generator
├── Live_Simulation.py         # (Optional) Real-time or UI simulation
├── resources/
│   └── ground_stations_global.txt   # Earth ground station locations
├── output/
│   └── satellite_simulation.kml     # Final KML visualization output
├── .venv/                     # Python virtual environment (optional)
├── .idea/                     # IDE metadata

 ## Features ##
✅ Dynamic satellite position updates (TLE-based)

✅ Calculates graph edges in real-time (satellite-to-satellite, satellite-to-ground, user-to-satellite)

✅ Finds shortest path between a user and ground station with custom edge weights

✅ Exports simulation to time-aware KML, with satellite motion, ground links, and path color cod

## Technologies Used

Python 3.10+

Skyfield – Satellite ephemeris and orbital mechanics

SimpleKML – KML generation

networkx – Dynamic graph structures and pathfinding

datetime, math, os – Built-in Python modules for time handling and file generation

 ## Output Preview

After running the simulation, you'll get a satellite_simulation.kml file with:

🟢 Green icons: Ground stations

🔴 Red icons: Satellites

🟣 Purple icons: Users

🔵 Violet lines: Shortest path per time step

🔴/🟦 Lines: Communication links (S2S, GS2SAT, etc.)

You can open this .kml file in Google Earth Pro to view an animated timeline.
