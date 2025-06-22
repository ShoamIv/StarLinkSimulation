# 🌍 Starlink Satellite Network Simulator #

Simulate and visualize dynamic Starlink satellite connectivity with shortest path discovery between users and ground stations. Outputs to animated KML for playback in Google Earth.

## Overview ##

This project simulates the real-time motion of Starlink satellites and models a dynamic communication graph that connects:

#### Users

#### Ground stations

#### Satellites

### The simulation:

Calculates satellite positions using Skyfield

Dynamically rebuilds the network graph at each time step

Identifies the shortest communication path from a user to user via satellites and ground stations.

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
    └──requirements.txt              #requirmenets txt for installation
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

# Scripts #

#### simulation.py ####

#### Purpose:

Runs a predefined simulation of the satellite network over a time range and outputs a sequence of KML files — one for each time step — into a folder. This is ideal for generating a video-like visualization of satellite movement and dynamic routing.

Output: satellite_simulation.kml

Open output/satellite_simulation.kml in Google Earth Pro.

Use Case:
When you want to simulate and review the satellite constellation behavior over time, offline.

#### live_simulation.py ####

#### Purpose:

Launches a live web server using Flask that continuously generates real-time KML data based on the current time. It creates a master_live_satellites.kml file with a NetworkLink that automatically refreshes in Google Earth every 30 seconds.

### How it Works:

Google Earth requests live_satellites.kml every 30 seconds.

The server dynamically updates satellite/user positions and links.

It also calculates the shortest path between a user and their closest ground station.

### Steps to Use:

Run the script:

python live_simulation.py

Open output/master_live_satellites.kml in Google Earth Pro.

## Usage ##

1. Clone the repository

2. Run the Simulation

    python simulate.py/master_live_satellites.py

3. Output saved to: output/file_name.kml

4. View in Google Earth

    Open file_name.kml in Google Earth Pro.

    Use the timeline slider to play through time steps or inititate the live simulation

## Requirements ##
 
To run this project, you'll need Python 3.8 or newer and the following Python packages:

flask

simplekml

skyfield

geopy

networkx

numpy

### Installation ###

Clone the repository (if you haven't already):

Create a virtual environment (optional but recommended):

python -m venv venv

source venv/bin/activate     # On Windows: venv\Scripts\activate

Create a requirements.txt file (or use the one provided at resources folder):

flask

skyfield

simplekml

geopy

networkx

numpy

Install dependencies:

pip install -r requirements.txt


