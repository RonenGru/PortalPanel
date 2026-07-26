# PortalPanel

Live instrument panel display for Microsoft Flight Simulator 2024 (and 2020), designed for use with VR passthrough setups.

## Overview

PortalPanel reads live flight data from MSFS via SimConnect and renders custom PFD (Primary Flight Display) and MFD (Multi-Function Display) instruments in a web browser. This allows pilots to view and interact with instrument panels on external monitors, even while in VR mode with passthrough enabled.

## Why PortalPanel?

MSFS's built-in Pop Out feature stops working when VR is enabled. PortalPanel solves this by using SimConnect (MSFS's official API) to read instrument data directly and render it in a web browser — which works perfectly alongside VR passthrough.

## Features

- **Live PFD** — Attitude indicator, airspeed tape, altitude tape, heading tape, VSI, NAV frequencies, baro setting
- **Live MFD** — Engine RPM, temperatures, fuel quantities, electrical, position data
- **Multiple views** — Combined PFD+MFD, standalone PFD, standalone MFD
- **VR compatible** — Works with VR passthrough (OpenKneeboard, etc.)
- **Aircraft agnostic** — Works with any aircraft that exposes standard SimConnect variables

## Requirements

- Microsoft Flight Simulator 2024 (or 2020) running with Developer Mode enabled
- Python 3.8+ 
- MSFS SimConnect SDK (installed with the game)

## Installation

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

Usage
Launch MSFS 2024 and load into the cockpit of your aircraft
Start the PortalPanel server:

1. cd manager
2. python portalpanel_server.py
Open a web browser to one of these addresses:
http://127.0.0.1:8090/ — Combined PFD + MFD
http://127.0.0.1:8090/pfd — Standalone PFD
http://127.0.0.1:8090/mfd — Standalone MFD


Project Structure

PortalPanel/
├── manager/
│   ├── portalpanel_server.py    # Flask + SimConnect backend server
│   ├── test_simconnect.py       # SimConnect connection test
│   └── instrument_reader.py     # Full instrument variable reader
├── web/
│   ├── index.html               # Combined PFD + MFD view
│   ├── pfd.html                 # Standalone PFD
│   └── mfd.html                 # Standalone MFD
├── requirements.txt
└── README.md

Tech Stack
Backend: Python, Flask, SimConnect
Frontend: HTML5 Canvas, JavaScript
Data Source: MSFS SimConnect API

License
MIT License — Free to use, modify, and share with the flight sim community.

Author
Ronen — Retired teacher, flight sim enthusiast, 3D printing and technology lover.