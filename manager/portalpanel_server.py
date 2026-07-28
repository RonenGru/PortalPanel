#!/usr/bin/env python3
"""
PortalPanel - Live Instrument Server with WebSocket Push
Reads MSFS data via SimConnect, pushes it to web-based instrument displays
"""
import sys
import os
import time
import json
import threading
from flask import Flask, jsonify, send_from_directory
from flask_socketio import SocketIO

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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "web"))
DATA_REFRESH_MS = 50  # How often to read SimConnect (ms)

# =====================================================================
# FLASK + WEBSOCKET SETUP
# =====================================================================
app = Flask(__name__, static_folder=WEB_DIR, static_url_path="/static")
app.config["SECRET_KEY"] = "portalpanel-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# =====================================================================
# INSTRUMENT DATA STORE
# =====================================================================
g_instrument_data = {}
g_data_lock = threading.Lock()
g_simconnect_active = False
g_status_message = "Initializing..."

# Final corrected variable list (from our testing)
# Final corrected variable list (from our testing)
INSTRUMENT_VARS = {
    # PFD
    "aircraft_title":        "TITLE",
    "aircraft_model":        "ATC_MODEL",
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
    "nav1_dme":              "NAV_DME:1",
    "nav2_freq":             "NAV_ACTIVE_FREQUENCY:2",
    "nav2_stby_freq":        "NAV_STANDBY_FREQUENCY:2",
    "nav2_signal":           "NAV_HAS_NAV:2",
    "nav2_dme":              "NAV_DME:2",
    "gps_ground_speed":      "GPS_GROUND_SPEED",
    "gps_magvar":            "GPS_MAGVAR",
    # MFD - Engine
    "eng_rpm":               "GENERAL_ENG_RPM:1",
    "eng_manifold_press":    "RECIP_ENG_MANIFOLD_PRESSURE:1",
    "eng_oil_temp":          "ENG_OIL_TEMPERATURE:1",
    "eng_oil_pressure":      "ENG_OIL_PRESSURE:1",
    "eng_egt":               "ENG_EXHAUST_GAS_TEMPERATURE:1",
    "eng_cht":               "ENG_CYLINDER_HEAD_TEMPERATURE:1",
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
        converted["eng_oil_pressure"] = round(
            converted["eng_oil_pressure"] / 6894.76, 1)

    # Round common values for cleaner display
    for key in ["altitude", "airspeed", "heading_true", "heading_mag",
                "vertical_speed", "baro_pressure", "turn_rate", "slip_ball",
                "nav1_dme", "nav2_dme", "gps_ground_speed", "gps_magvar",
                "eng_rpm", "eng_manifold_press", "eng_fuel_flow", "fuel_total",
                "fuel_left", "fuel_right", "bus_voltage", "bus_load",
                "vacuum"]:
        if converted.get(key) is not None and isinstance(converted[key], float):
            converted[key] = round(converted[key], 2)

    # Format NAV frequencies nicely
    for key in ["nav1_freq", "nav1_stby_freq", "nav2_freq", "nav2_stby_freq"]:
        if converted.get(key) is not None:
            converted[key] = round(converted[key], 2)

        # Aircraft title
    if converted.get("aircraft_title") is not None:
        try:
            converted["aircraft_title"] = converted["aircraft_title"].strip()
        except:
            pass
    if converted.get("aircraft_model") is not None:
        try:
            converted["aircraft_model"] = converted["aircraft_model"].strip()
        except:
            pass
    
    return converted


def read_instrument_data(ar):
    """Read all instrument variables from SimConnect"""
    data = {}
    for key, simvar in INSTRUMENT_VARS.items():
        try:
            value = ar.get(simvar)
            data[key] = value
        except Exception:
            data[key] = None
    return data


def simconnect_loop():
    """Background thread: continuously read SimConnect data and push via WebSocket"""
    global g_instrument_data, g_simconnect_active, g_status_message

    if not SIMCONNECT_AVAILABLE:
        g_status_message = "SimConnect not installed (mock mode)"
        mock_altitude = 5000
        while True:
            if sys.is_finalizing():
                break
            mock_data = {
                "aircraft_title": "Cessna Skyhawk 172 G1000",
                "aircraft_model": "C172",
                "altitude": mock_altitude, "airspeed": 120,
                "vertical_speed": 0, "heading_true": 180,
                "heading_mag": 180, "pitch": 5, "roll": 0,
                "latitude": 44.98, "longitude": -79.31,
                "on_ground": 0, "baro_pressure": 1013.25,
                "turn_rate": 0, "slip_ball": 0,
                "nav1_freq": 110.50, "nav1_stby_freq": 113.90,
                "nav1_signal": 0, "nav1_dme": 0,
                "nav2_freq": 110.50, "nav2_stby_freq": 113.90,
                "nav2_signal": 0, "nav2_dme": 0,
                "gps_ground_speed": 120, "gps_magvar": 0,
                "eng_rpm": 2300, "eng_manifold_press": 23.0,
                "eng_oil_temp": 168.0, "eng_oil_pressure": 50.0,
                "eng_egt": 1250.0, "eng_cht": 300.0,
                "eng_fuel_flow": 12.0, "fuel_total": 25.8,
                "fuel_left": 12.9, "fuel_right": 12.9,
                "bus_voltage": 28.0, "bus_load": 15.0, 
                "vacuum": 5.0,
                "aircraft_title": "Cessna Skyhawk 172 G1000",
                "aircraft_model": "C172",
            }
            with g_data_lock:
                g_instrument_data = mock_data
            socketio.emit("instrument_data", {
                "status": g_status_message,
                "connected": False,
                "data": mock_data
            })
            mock_altitude += 1
            if mock_altitude > 15000:
                mock_altitude = 5000
            time.sleep(DATA_REFRESH_MS / 1000.0)
        return

    sm = None
    ar = None

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

            raw_data = read_instrument_data(ar)
            converted = convert_units(raw_data)

            with g_data_lock:
                g_instrument_data = converted

            # PUSH data to all connected browsers immediately
            socketio.emit("instrument_data", {
                "status": g_status_message,
                "connected": g_simconnect_active,
                "data": converted
            })

            time.sleep(DATA_REFRESH_MS / 1000.0)

        except Exception as e:
            g_simconnect_active = False
            g_status_message = "MSFS not connected. Waiting..."
            print("[SIMCONNECT] Error: {}. Retrying in 3s...".format(e))
            socketio.emit("instrument_data", {
                "status": g_status_message,
                "connected": False,
                "data": {}
            })
            time.sleep(3.0)


# =====================================================================
# FLASK ROUTES
# =====================================================================

@app.route("/")
def index():
    """Combined PFD + MFD page"""
    try:
        return send_from_directory(WEB_DIR, "index.html")
    except FileNotFoundError:
        return "ERROR: index.html not found in {}".format(WEB_DIR), 404


@app.route("/pfd")
def pfd():
    """Standalone PFD page"""
    try:
        return send_from_directory(WEB_DIR, "pfd.html")
    except FileNotFoundError:
        return "ERROR: pfd.html not found in {}".format(WEB_DIR), 404


@app.route("/mfd")
def mfd():
    """Standalone MFD page"""
    try:
        return send_from_directory(WEB_DIR, "mfd.html")
    except FileNotFoundError:
        return "ERROR: mfd.html not found in {}".format(WEB_DIR), 404


@app.route("/api/data")
def api_data():
    """JSON endpoint with all live instrument data (fallback for HTTP polling)"""
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
    
@app.route("/api/aircraft")
def api_aircraft():
    """Return detected aircraft info"""
    with g_data_lock:
        data = dict(g_instrument_data)
    title = data.get("aircraft_title", "Unknown")
    model = data.get("aircraft_model", "")
    return jsonify({
        "title": title,
        "model": model
    })

@app.route("/api/monitors")
def api_monitors():
    """Return list of available monitors"""
    try:
        from screeninfo import get_monitors
        monitors = []
        for m in get_monitors():
            monitors.append({
                "x": m.x, "y": m.y,
                "width": m.width, "height": m.height
            })
        return jsonify({"monitors": monitors})
    except Exception as e:
        return jsonify({"monitors": [], "error": str(e)})   


@socketio.on("connect")
def on_connect():
    """Called when a browser connects via WebSocket"""
    print("[WEBSOCKET] Client connected")
    # Send current data immediately
    with g_data_lock:
        data = dict(g_instrument_data)
    socketio.emit("instrument_data", {
        "status": g_status_message,
        "connected": g_simconnect_active,
        "data": data
    })


# =====================================================================
# MAIN
# =====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("PortalPanel - Live Instrument Server (WebSocket)")
    print("=" * 60)
    print("")

    # Ensure web directory exists
    if not os.path.exists(WEB_DIR):
        os.makedirs(WEB_DIR)
        print("[SYSTEM] Created web directory: {}".format(WEB_DIR))

    # Start SimConnect data reader thread
    sim_thread = threading.Thread(target=simconnect_loop, daemon=True)
    sim_thread.start()

    # Start Flask + WebSocket server
    print("[FLASK] PortalPanel server starting on http://127.0.0.1:8090")
    print("[WEBSOCKET] WebSocket enabled for real-time push")
    socketio.run(app, host="127.0.0.1", port=8090,
                 debug=False, allow_unsafe_werkzeug=True)