#!/usr/bin/env python3
"""
PortalPanel - Live Instrument Server
Reads MSFS data via SimConnect, serves it to web-based instrument displays
"""
import sys
import os
import time
import json
import threading
from flask import Flask, jsonify, Response

# Try to import SimConnect
try:
    from SimConnect import SimConnect, AircraftRequests
    SIMCONNECT_AVAILABLE = True
except ImportError:
    SIMCONNECT_AVAILABLE = False
    print("[WARN] SimConnect not available - running in mock mode")

# =====================================================================
# CONFIG
# =====================================================================
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
WEB_DIR = os.path.normpath(WEB_DIR)
DATA_REFRESH_MS = 10  # How often to poll SimConnect (ms)

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="/static")

# =====================================================================
# INSTRUMENT DATA STORE
# =====================================================================
g_instrument_data = {}
g_data_lock = threading.Lock()
g_simconnect_active = False
g_status_message = "Initializing..."

# Final corrected variable list (from our testing)
INSTRUMENT_VARS = {
    # PFD
    "altitude":              "PLANE_ALTITUDE",
    "airspeed":              "AIRSPEED_INDICATED",
    "vertical_speed":        "VERTICAL_SPEED",
    "heading_true":          "PLANE_HEADING_DEGREES_TRUE",
    "heading_mag":           "PLANE_HEADING_DEGREES_MAGNETIC",
    "pitch":                 "PLANE_PITCH_DEGREES",
    "roll":                  "PLANE_BANK_DEGREES",
    "latitude":              "PLANE_LATITUDE",
    "longitude":             "PLANE_LONGITUDE",
    "on_ground":             "SIM_ON_GROUND",
    "baro_pressure":         "KOHLSMAN_SETTING_MB",
    "turn_rate":             "TURN_INDICATOR_RATE",
    "slip_ball":             "TURN_COORDINATOR_BALL",
    "nav1_freq":             "NAV_ACTIVE_FREQUENCY:1",
    "nav1_stby_freq":        "NAV_STANDBY_FREQUENCY:1",
    "nav1_signal":           "NAV_HAS_NAV:1",
    "nav1_dme":             "NAV_DME:1",
    "nav2_freq":             "NAV_ACTIVE_FREQUENCY:2",
    "nav2_stby_freq":        "NAV_STANDBY_FREQUENCY:2",
    "nav2_signal":           "NAV_HAS_NAV:2",
    "nav2_dme":             "NAV_DME:2",
    "gps_ground_speed":      "GPS_GROUND_SPEED",
    "gps_magvar":            "GPS_MAGVAR",

    # MFD - Engine
    "eng_rpm":               "GENERAL_ENG_RPM:1",
    "eng_manifold_press":    "RECIP_ENG_MANIFOLD_PRESSURE:1",
    "eng_oil_temp":         "ENG_OIL_TEMPERATURE:1",       # Rankine
    "eng_oil_pressure":      "ENG_OIL_PRESSURE:1",          # Pascals
    "eng_egt":              "ENG_EXHAUST_GAS_TEMPERATURE:1", # Rankine
    "eng_cht":              "ENG_CYLINDER_HEAD_TEMPERATURE:1", # Rankine
    "eng_fuel_flow":         "ENG_FUEL_FLOW_GPH:1",

    # MFD - Fuel
    "fuel_total":            "FUEL_TOTAL_QUANTITY",
    "fuel_left":             "FUEL_LEFT_QUANTITY",
    "fuel_right":            "FUEL_RIGHT_QUANTITY",

    # MFD - Electrical
    "bus_voltage":           "ELECTRICAL_MAIN_BUS_VOLTAGE",
    "bus_load":              "ELECTRICAL_MAIN_BUS_AMPS",
    "vacuum":                "SUCTION_PRESSURE",
}


def convert_units(raw_data):
    """Convert MSFS internal units to display-friendly values"""
    converted = dict(raw_data)
        # Pitch and roll: MSFS 2024 returns radians, convert to degrees
    if converted.get("pitch") is not None:
        converted["pitch"] = round(converted["pitch"] * 57.2958, 2)
    if converted.get("roll") is not None:
        converted["roll"] = round(converted["roll"] * 57.2958, 2)

    # Temperature: Rankine -> Fahrenheit
    for key in ["eng_oil_temp", "eng_egt", "eng_cht"]:
        if converted.get(key) is not None:
            converted[key] = round(converted[key] - 459.67, 1)

    # Oil pressure: Pascals -> PSI
    if converted.get("eng_oil_pressure") is not None:
        converted["eng_oil_pressure"] = round(converted["eng_oil_pressure"] / 6894.76, 1)

    # Round common values for cleaner display
    for key in ["altitude", "airspeed", "heading_true", "heading_mag",
                "vertical_speed", "pitch", "roll", "baro_pressure",
                "turn_rate", "slip_ball", "nav1_dme", "nav2_dme",
                "gps_ground_speed", "gps_magvar", "eng_rpm",
                "eng_manifold_press", "eng_fuel_flow", "fuel_total",
                "fuel_left", "fuel_right", "bus_voltage", "bus_load",
                "vacuum"]:
        if converted.get(key) is not None and isinstance(converted[key], float):
            converted[key] = round(converted[key], 2)

    # Format NAV frequencies nicely (e.g., 114.30)
    for key in ["nav1_freq", "nav1_stby_freq", "nav2_freq", "nav2_stby_freq"]:
        if converted.get(key) is not None:
            converted[key] = round(converted[key], 2)

    return converted


def read_instrument_data(sm, ar):
    """Read all instrument variables from SimConnect"""
    global g_instrument_data, g_simconnect_active, g_status_message
    data = {}
    for key, simvar in INSTRUMENT_VARS.items():
        try:
            value = ar.get(simvar)
            data[key] = value
        except Exception:
            data[key] = None
    return data


def simconnect_loop():
    """Background thread: continuously read SimConnect data"""
    global g_instrument_data, g_simconnect_active, g_status_message

    if not SIMCONNECT_AVAILABLE:
        g_status_message = "SimConnect not installed (mock mode)"
        mock_altitude = 5000
        mock_heading = 180
        mock_airspeed = 120
        while True:
            if sys.is_finalizing():
                break
            mock_data = {
                "altitude": mock_altitude,
                "airspeed": mock_airspeed,
                "vertical_speed": 0,
                "heading_true": mock_heading,
                "heading_mag": mock_heading,
                "pitch": 0,
                "roll": 0,
                "latitude": 44.98,
                "longitude": -79.31,
                "on_ground": 0,
                "baro_pressure": 1013.25,
                "turn_rate": 0,
                "slip_ball": 0,
                "nav1_freq": 110.50,
                "nav1_stby_freq": 113.90,
                "nav1_signal": 0,
                "nav1_dme": 0,
                "nav2_freq": 110.50,
                "nav2_stby_freq": 113.90,
                "nav2_signal": 0,
                "nav2_dme": 0,
                "gps_ground_speed": 0,
                "gps_magvar": 0,
                "eng_rpm": 2300,
                "eng_manifold_press": 23.0,
                "eng_oil_temp": 168.0,
                "eng_oil_pressure": 50.0,
                "eng_egt": 1250.0,
                "eng_cht": 300.0,
                "eng_fuel_flow": 12.0,
                "fuel_total": 25.8,
                "fuel_left": 12.9,
                "fuel_right": 12.9,
                "bus_voltage": 28.0,
                "bus_load": 15.0,
                "vacuum": 5.0,
            }
            with g_data_lock:
                g_instrument_data = mock_data
            mock_altitude += 1
            if mock_altitude > 15000:
                mock_altitude = 5000
            time.sleep(DATA_REFRESH_MS / 1000.0)
        return

    while True:
        if sys.is_finalizing():
            break
        try:
            if not g_simconnect_active:
                sm = SimConnect()
                ar = AircraftRequests(sm, _time=DATA_REFRESH_MS)
                g_simconnect_active = True
                g_status_message = "Connected to MSFS"
                print("[SIMCONNECT] Connected!")

            raw_data = read_instrument_data(sm, ar)
            converted = convert_units(raw_data)

            with g_data_lock:
                g_instrument_data = converted

            g_status_message = "Connected to MSFS"
            time.sleep(DATA_REFRESH_MS / 1000.0)

        except Exception as e:
            g_simconnect_active = False
            g_status_message = "MSFS not connected. Waiting..."
            print("[SIMCONNECT] Error: {}. Retrying in 3s...".format(e))
            time.sleep(3.0)


# =====================================================================
# FLASK ROUTES
# =====================================================================

@app.route("/")
def index():
    """Combined PFD + MFD page"""
    try:
        filepath = os.path.join(WEB_DIR, "index.html")
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "ERROR: index.html not found in {}".format(WEB_DIR), 404


@app.route("/pfd")
def pfd():
    """Standalone PFD page"""
    try:
        filepath = os.path.join(WEB_DIR, "pfd.html")
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "ERROR: pfd.html not found in {}".format(WEB_DIR), 404


@app.route("/mfd")
def mfd():
    """Standalone MFD page"""
    try:
        filepath = os.path.join(WEB_DIR, "mfd.html")
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "ERROR: mfd.html not found in {}".format(WEB_DIR), 404


@app.route("/api/data")
def api_data():
    """JSON endpoint with all live instrument data"""
    with g_data_lock:
        data = dict(g_instrument_data)
    return jsonify({
        "status": g_status_message,
        "connected": g_simconnect_active,
        "data": data
    })


@app.route("/api/status")
def api_status():
    """Simple status endpoint"""
    return jsonify({
        "connected": g_simconnect_active,
        "message": g_status_message
    })


# =====================================================================
# MAIN
# =====================================================================

def start_flask():
    print("[FLASK] PortalPanel server starting on http://127.0.0.1:8090")
    app.run(host="127.0.0.1", port=8090, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    print("=" * 60)
    print("PortalPanel - Live Instrument Server")
    print("=" * 60)
    print("")

    # Ensure web directory exists
    if not os.path.exists(WEB_DIR):
        os.makedirs(WEB_DIR)
        print("[SYSTEM] Created web directory: {}".format(WEB_DIR))

    # Start SimConnect data reader thread
    sim_thread = threading.Thread(target=simconnect_loop, daemon=True)
    sim_thread.start()

    # Start Flask web server
    start_flask()