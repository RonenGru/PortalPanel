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
from flask import Flask, jsonify, send_from_directory, request
from flask_socketio import SocketIO

# Try to import SimConnect
try:
    from SimConnect import SimConnect, AircraftRequests, AircraftEvents
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
g_simconnect_requests = None  # Stores the AircraftRequests object for writing
g_simconnect_events = None    # Stores the AircraftEvents object for events
g_status_message = "Initializing..."

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
    # Autopilot / Heading Bug
    "hdg_bug":              "AUTOPILOT_HEADING_LOCK_DIR",
    "ap_master":            "AUTOPILOT_MASTER",
    "ap_alt_lock":          "AUTOPILOT_ALTITUDE_LOCK",
    "ap_hdg_lock":          "AUTOPILOT_HEADING_LOCK",
    "ap_nav_lock":          "AUTOPILOT_NAV1_LOCK",
    "ap_apr_lock":          "AUTOPILOT_APPROACH_HOLD",
    "ap_vs_lock":           "AUTOPILOT_VERTICAL_HOLD",
    "ap_fdir_bank":         "AUTOPILOT_FLIGHT_DIRECTOR_BANK",
    "ap_fdir_pitch":        "AUTOPILOT_FLIGHT_DIRECTOR_PITCH",
    # CDI
    "nav1_cdi":             "NAV_CDI:1",
    "nav2_cdi":             "NAV_CDI:2",
    "gps_cdi":              "GPS_DRIVES_NAV1",
    "gps_cross_trk":        "GPS_WP_CROSS_TRK",
    "gps_wp_distance":      "GPS_WP_DISTANCE",
    "gps_wp_ete":           "GPS_ETE",
    "gps_wp_id":            "GPS_WP_NEXT_ID",
    # Weather
    "oat":                  "AMBIENT_TEMPERATURE",
    "wind_dir":             "AMBIENT_WIND_DIRECTION",
    "wind_speed":            "AMBIENT_WIND_VELOCITY",
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


def to_display_str(value, default="Unknown"):
    """
    Safely convert a SimConnect value to a clean, JSON-serializable display
    string. Some SimConnect wrapper calls return `bytes` instead of `str`
    for string simvars (e.g. TITLE, ATC_MODEL) -- bytes objects also have
    a .strip() method, so a naive .strip() "succeeds" but silently leaves
    the value as bytes, which later blows up jsonify() with:
    "TypeError: Object of type bytes is not JSON serializable".
    """
    if value is None:
        return default
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore").strip()
        except Exception:
            return default
    try:
        return str(value).strip()
    except Exception:
        return default


def convert_units(raw_data):
    """Convert MSFS internal units to display-friendly values"""
    converted = dict(raw_data)

    # Pitch and roll: MSFS 2024 returns radians, convert to degrees
    if converted.get("pitch") is not None:
        converted["pitch"] = round(converted["pitch"] * 57.2958, 2)
    if converted.get("roll") is not None:
        converted["roll"] = round(converted["roll"] * 57.2958, 2)
    # Heading: MSFS 2024 also returns radians, convert to degrees
    if converted.get("heading_true") is not None:
        converted["heading_true"] = round(converted["heading_true"] * 57.2958, 2)
    if converted.get("heading_mag") is not None:
        converted["heading_mag"] = round(converted["heading_mag"] * 57.2958, 2)
    # Heading bug: SimConnect library already returns this in degrees — no conversion needed
        # Flight Director: MSFS 2024 returns radians, convert to degrees
    if converted.get("ap_fdir_bank") is not None:
        converted["ap_fdir_bank"] = round(converted["ap_fdir_bank"] * 57.2958, 2)
    if converted.get("ap_fdir_pitch") is not None:
        converted["ap_fdir_pitch"] = round(converted["ap_fdir_pitch"] * 57.2958, 2)

    # Temperature: Rankine -> Fahrenheit
    for key in ["eng_oil_temp", "eng_egt", "eng_cht"]:
        if converted.get(key) is not None:
            converted[key] = round(converted[key] - 459.67, 1)

    # OAT: Celsius -> Fahrenheit (MSFS 2024 returns ambient temp in Celsius)
    if converted.get("oat") is not None:
        converted["oat"] = round(converted["oat"] * 9 / 5 + 32, 0)

    # Oil pressure: Pascals -> PSI
    if converted.get("eng_oil_pressure") is not None:
        converted["eng_oil_pressure"] = round(converted["eng_oil_pressure"] / 6894.76, 1)

    # Round common values for cleaner display
    for key in ["altitude", "airspeed", "heading_true", "heading_mag",
            "vertical_speed", "baro_pressure", "turn_rate", "slip_ball",
            "nav1_dme", "nav2_dme", "gps_ground_speed", "gps_magvar",
            "wind_dir", "wind_speed",
            "eng_rpm", "eng_manifold_press", "eng_fuel_flow", "fuel_total",
            "fuel_left", "fuel_right", "bus_voltage", "bus_load",
            "vacuum"]:
        if converted.get(key) is not None and isinstance(converted[key], float):
            converted[key] = round(converted[key], 2)
    # GPS cross-track: meters -> nautical miles (1 nm = 1852 m)
    if converted.get("gps_cross_trk") is not None:
        converted["gps_cross_trk"] = round(converted["gps_cross_trk"] / 1852.0, 3)
    # GPS waypoint distance: meters -> nautical miles
    if converted.get("gps_wp_distance") is not None:
        converted["gps_wp_distance"] = round(converted["gps_wp_distance"] / 1852.0, 1)
    # GPS ETE: seconds -> minutes
    if converted.get("gps_wp_ete") is not None:
        converted["gps_wp_ete"] = round(converted["gps_wp_ete"] / 60.0, 1)    

    # Format NAV frequencies nicely
    for key in ["nav1_freq", "nav1_stby_freq", "nav2_freq", "nav2_stby_freq"]:
        if converted.get(key) is not None:
            converted[key] = round(converted[key], 2)

    # Aircraft title / model -- always normalize to a clean JSON-safe string,
    # handling the bytes-vs-str SimConnect quirk described above.
    converted["aircraft_title"] = to_display_str(converted.get("aircraft_title"))
    converted["aircraft_model"] = to_display_str(converted.get("aircraft_model"), default="")
    converted["gps_wp_id"] = to_display_str(converted.get("gps_wp_id"), default="")
    return converted


# =====================================================================
# GLOBAL CORS HEADERS DECORATOR
# =====================================================================
@app.after_request
def add_cors_headers(response):
    """Injects standard CORS headers to bypass local file Webview2 security blocks."""
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response


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
    global g_simconnect_requests, g_simconnect_events

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
                "oat": 15.0, "wind_dir": 270, "wind_speed": 10,
                "hdg_bug": 180, "ap_master": 0, "ap_alt_lock": 0,
                "ap_hdg_lock": 0, "ap_nav_lock": 0, "ap_apr_lock": 0,
                "ap_vs_lock": 0, "ap_fdir_bank": 0, "ap_fdir_pitch": 0,
                "nav1_cdi": 0, "nav2_cdi": 0, "gps_cdi": 0,
                "gps_wp_id": "MOCKWP",
                "gps_wp_distance": 12.3,
                "gps_wp_ete": 8.5,
                "eng_rpm": 2300, "eng_manifold_press": 23.0,
                "eng_oil_temp": 168.0, "eng_oil_pressure": 50.0,
                "eng_egt": 1250.0, "eng_cht": 300.0,
                "eng_fuel_flow": 12.0, "fuel_total": 25.8,
                "fuel_left": 12.9, "fuel_right": 12.9,
                "bus_voltage": 28.0, "bus_load": 15.0,
                "vacuum": 5.0,
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
                g_simconnect_requests = ar
                g_simconnect_events = AircraftEvents(sm)
                g_simconnect_active = True
                g_status_message = "Connected to MSFS"
                print("[SIMCONNECT] Connected!")
            raw_data = read_instrument_data(ar)
            
            # Check for silent disconnect: if core variables return None,
            # MSFS has likely closed but SimConnect didn't throw an error.
            if raw_data.get("altitude") is None and raw_data.get("airspeed") is None:
                raise Exception("MSFS data stream lost (silent disconnect)")
                
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
            
            # Clear the instrument data so aircraft detection resets
            with g_data_lock:
                g_instrument_data = {}
                
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


@app.route("/launcher")
def serve_launcher():
    """Serves the launcher UI page directly from the server to bypass local file security blocks."""
    try:
        return send_from_directory(BASE_DIR, "launcher.html")
    except FileNotFoundError:
        return "ERROR: launcher.html not found in {}".format(BASE_DIR), 404


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
    resp = jsonify({
        "connected": g_simconnect_active,
        "message": g_status_message
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/aircraft")
def api_aircraft():
    """Return detected aircraft info"""
    with g_data_lock:
        data = dict(g_instrument_data)
    resp = jsonify({
        "title": to_display_str(data.get("aircraft_title")),
        "model": to_display_str(data.get("aircraft_model"), default="")
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp

# =====================================================================
# NEAREST AIRPORTS (OurAirports CSV)
# =====================================================================
import csv as csv_module
import math as math_module

AIRPORTS_CSV = os.path.normpath(os.path.join(BASE_DIR, "..", "data", "airports.csv"))
g_airports = []  # List of airport dicts loaded into memory
g_airports_loaded = False

def load_airports():
    """Load airports.csv into memory once at server startup."""
    global g_airports, g_airports_loaded
    if g_airports_loaded:
        return
    if not os.path.exists(AIRPORTS_CSV):
        print("[AIRPORTS] airports.csv not found at {}".format(AIRPORTS_CSV))
        return
    try:
        with open(AIRPORTS_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv_module.DictReader(f)
            count = 0
            for row in reader:
                try:
                    airport_type = row.get("type", "").strip().lower()
                    # Skip heliports and seaplane bases — keep only real airports
                    if airport_type in ("heliport", "seaplane_base", "closed"):
                        continue
                    lat = float(row.get("latitude_deg", 0))
                    lon = float(row.get("longitude_deg", 0))
                    ident = row.get("ident", row.get("gps_code", "")).strip()
                    name = row.get("name", "").strip()
                    if not ident or not name:
                        continue
                    g_airports.append({
                        "ident": ident,
                        "name": name,
                        "lat": lat,
                        "lon": lon,
                        "type": airport_type,
                        "size": "L" if "large" in airport_type else ("M" if "medium" in airport_type else "S")
                    })
                    count += 1
                except (ValueError, TypeError):
                    continue
        g_airports_loaded = True
        print("[AIRPORTS] Loaded {} airports into memory".format(count))
    except Exception as e:
        print("[AIRPORTS] Error loading airports.csv: {}".format(e))

def haversine_nm(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in nautical miles."""
    R_nm = 3440.065  # Earth radius in nautical miles
    dlat = math_module.radians(lat2 - lat1)
    dlon = math_module.radians(lon2 - lon1)
    a = (math_module.sin(dlat / 2) ** 2 +
         math_module.cos(math_module.radians(lat1)) *
         math_module.cos(math_module.radians(lat2)) *
         math_module.sin(dlon / 2) ** 2)
    c = 2 * math_module.atan2(math_module.sqrt(a), math_module.sqrt(1 - a))
    return R_nm * c

@app.route("/api/airports")
def api_airports():
    """Return airports within range of the aircraft's current position."""
    if not g_airports_loaded:
        load_airports()
    if not g_airports_loaded or not g_airports:
        return jsonify({"airports": [], "error": "No airport data loaded"})
    # Get current aircraft position
    with g_data_lock:
        data = dict(g_instrument_data)
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        return jsonify({"airports": [], "error": "No GPS position"})
    # Find airports within 50 nm
    nearby = []
    for airport in g_airports:
        dist = haversine_nm(lat, lon, airport["lat"], airport["lon"])
        if dist <= 50.0:
            bearing = math_module.degrees(
                math_module.atan2(
                    math_module.sin(math_module.radians(airport["lon"] - lon)) *
                    math_module.cos(math_module.radians(airport["lat"])),
                    math_module.cos(math_module.radians(lat)) *
                    math_module.sin(math_module.radians(airport["lat"])) -
                    math_module.sin(math_module.radians(lat)) *
                    math_module.cos(math_module.radians(airport["lat"])) *
                    math_module.cos(math_module.radians(airport["lon"] - lon))
                )
            )
            bearing = (bearing + 360) % 360
            nearby.append({
                "ident": airport["ident"],
                "name": airport["name"],
                "lat": airport["lat"],
                "lon": airport["lon"],
                "type": airport["type"],
                "size": airport["size"],
                "distance": round(dist, 1),
                "bearing": round(bearing, 0)
            })
    # Sort by distance (nearest first)
    nearby.sort(key=lambda a: a["distance"])
    # Return top 20 nearest
    return jsonify({"airports": nearby[:20], "count": len(nearby)})

@app.route("/api/airports/all")
def api_airports_all():
    """Return all airports within range (no limit) for map drawing."""
    if not g_airports_loaded:
        load_airports()
    if not g_airports_loaded or not g_airports:
        return jsonify({"airports": [], "error": "No airport data loaded"})
    with g_data_lock:
        data = dict(g_instrument_data)
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        return jsonify({"airports": [], "error": "No GPS position"})
    nearby = []
    for airport in g_airports:
        dist = haversine_nm(lat, lon, airport["lat"], airport["lon"])
        if dist <= 50.0:
            nearby.append({
                "ident": airport["ident"],
                "lat": airport["lat"],
                "lon": airport["lon"],
                "size": airport["size"],
                "distance": round(dist, 1)
            })
    nearby.sort(key=lambda a: a["distance"])
    return jsonify({"airports": nearby, "count": len(nearby)})

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


@socketio.on("knob_command")
def handle_knob_command(data):
    """Receives knob commands from web UI or hardware and writes to MSFS"""
    if not g_simconnect_active or g_simconnect_requests is None:
        return
    cmd = data.get("cmd")
    print("[KNOB] Received: {}".format(cmd))
    try:
        ar = g_simconnect_requests
        ae = g_simconnect_events
        # --- NAV1 Frequency ---
        if cmd == "NAV1_BIG_RIGHT":
            event = ae.find("NAV1_RADIO_WHOLE_INC")
            event()
        elif cmd == "NAV1_BIG_LEFT":
            event = ae.find("NAV1_RADIO_WHOLE_DEC")
            event()
        elif cmd == "NAV1_SMALL_RIGHT":
            event = ae.find("NAV1_RADIO_FRACT_INC")
            event()
        elif cmd == "NAV1_SMALL_LEFT":
            event = ae.find("NAV1_RADIO_FRACT_DEC")
            event()
        elif cmd == "NAV1_SWAP":
            event = ae.find("NAV1_RADIO_SWAP")
            event()
        # --- NAV2 Frequency ---
        elif cmd == "NAV2_BIG_RIGHT":
            event = ae.find("NAV2_RADIO_WHOLE_INC")
            event()
        elif cmd == "NAV2_BIG_LEFT":
            event = ae.find("NAV2_RADIO_WHOLE_DEC")
            event()
        elif cmd == "NAV2_SMALL_RIGHT":
            event = ae.find("NAV2_RADIO_FRACT_INC")
            event()
        elif cmd == "NAV2_SMALL_LEFT":
            event = ae.find("NAV2_RADIO_FRACT_DEC")
            event()
        elif cmd == "NAV2_SWAP":
            event = ae.find("NAV2_RADIO_SWAP")
            event()
        # --- BARO Setting ---
        elif cmd == "BARO_RIGHT":
            event = ae.find("KOHLSMAN_INC")
            event()
        elif cmd == "BARO_LEFT":
            event = ae.find("KOHLSMAN_DEC")
            event()
        # --- Heading Bug ---
        elif cmd == "HDG_RIGHT":
            event = ae.find("HEADING_BUG_INC")
            event()
        elif cmd == "HDG_LEFT":
            event = ae.find("HEADING_BUG_DEC")
            event()
    except Exception as e:
        print("[KNOB] Error writing to SimConnect: {}".format(e))

@socketio.on("nrst_toggle")
def handle_nrst_toggle(data):
    """Relay NRST airport-overlay toggle to all OTHER connected clients.
    skip_sid excludes the sender -- the sender already updated its own
    UI locally when the button was clicked, so echoing the event back
    to it is unnecessary and, if anything downstream reacts to it,
    can create an infinite toggle-emit-receive-toggle loop."""
    socketio.emit("nrst_state", {"show": data.get("show", False)}, skip_sid=request.sid)

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