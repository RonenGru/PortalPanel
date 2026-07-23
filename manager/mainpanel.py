import os
import sys
import time
import threading
from flask import Flask, Response, jsonify, send_from_directory
import webview
from PIL import Image, ImageDraw, ImageFont

# =====================================================================
# PATH RESOLUTION ENGINE (SAFE FOR DEV & PYINSTALLER)
# =====================================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
    USER_DATA_DIR = os.path.join(EXE_DIR, "user_data")
    WEB_DIR = os.path.join(BASE_DIR, "web")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    USER_DATA_DIR = os.path.join(BASE_DIR, "../user_data")
    WEB_DIR = os.path.join(BASE_DIR, "../web")

# Initialize Flask (Serving from the web asset directory)
app = Flask(__name__, static_folder=WEB_DIR, static_url_path="/web")

# Ensure persistent directories exist
if not os.path.exists(USER_DATA_DIR):
    os.makedirs(USER_DATA_DIR)

# Global memory buffer holding the active binary JPEG frames
g_raw_frame = b""
g_frame_lock = threading.Lock()

# =====================================================================
# THE MOCK COCKPIT TEXTURE GENERATOR (25 FPS Background Thread)
# =====================================================================
def generate_mock_cockpit_texture():
    """Generates a simulated glass cockpit display (rolling horizon & gauges) in memory."""
    global g_raw_frame
    print("[MOCK CORE] Dynamic cockpit texture generator started.")
    
    # Coordinates for simulated motion
    pitch_offset = 0
    pitch_direction = 1
    roll_angle = 0
    altitude = 5000
    
    while True:
        if sys.is_finalizing():
            break
            
        # Create a blank 1920x1080 canvas (representing our raw MSFS texture sheet)
        img = Image.new("RGB", (1920, 1080), (15, 15, 15))
        draw = ImageDraw.Draw(img)
        
        # --- UPDATE SIMULATED TELEMETRY ---
        pitch_offset += 2 * pitch_direction
        if abs(pitch_offset) > 100:
            pitch_direction *= -1  # Reverse bounce direction
        roll_angle = (roll_angle + 1) % 360
        altitude = (altitude + 5) if altitude < 12000 else 5000
        
        # --- DRAW LEFT SCREEN: ATTITUDE INDICATOR (G1000 STYLE) ---
        # Draw Sky (Blue)
        draw.rectangle([50, 140, 910, 940], fill=(0, 130, 230))
        # Draw Ground (Brown) based on pitch
        mid_y = 540 + pitch_offset
        draw.rectangle([50, mid_y, 910, 940], fill=(130, 80, 20))
        
        # Draw Horizon Line
        draw.line([50, mid_y, 910, mid_y], fill=(255, 255, 255), width=4)
        
        # --- DRAW RIGHT SCREEN: ENGINE & NAV MAP SHEET ---
        # Draw a simulated GPS track grid
        for x in range(1010, 1870, 100):
            draw.line([x, 140, x, 940], fill=(40, 40, 40), width=1)
        for y in range(140, 940, 100):
            draw.line([1010, y, 1870, y], fill=(40, 40, 40), width=1)
            
        # Draw moving flight path coordinate
        draw.ellipse([1440 - 15, 540 - 15, 1440 + 15, 540 + 15], fill=(0, 255, 0))
        
        # Draw descriptive text onto the screens
        draw.text((100, 180), "PORTAL PANEL - MOCK COCKPIT ENGINE", fill=(255, 255, 255))
        draw.text((100, 230), f"SIMULATED ALTITUDE: {altitude} FT", fill=(0, 255, 255))
        draw.text((100, 280), "PFD SIMULATION (LEFT PANEL)", fill=(255, 255, 0))
        draw.text((1060, 180), "MFD / GPS / ENGINE SIMULATION (RIGHT PANEL)", fill=(255, 255, 0))
        
        # Compile the canvas into a high-quality compressed JPEG in memory
        import io
        byte_arr = io.BytesIO()
        img.save(byte_arr, format='JPEG', quality=85)
        raw_bytes = byte_arr.getvalue()
        
        # Update our global raw frame under thread safety lock
        with g_frame_lock:
            g_raw_frame = raw_bytes
            
        # Rest for exactly 40 milliseconds (~25 FPS)
        time.sleep(0.04)

# =====================================================================
# FLASK WEB SERVER API ENDPOINTS
# =====================================================================
@app.route("/")
def home():
    """Serves the main layout configuration GUI."""
    try:
        with open(os.path.join(WEB_DIR, "panel.html"), "r") as f:
            return f.read()
    except FileNotFoundError:
        return "ERROR: panel.html not found in web directory!", 404

def get_mjpeg_stream_generator():
    """Generates a low-latency multipart JPEG boundary stream for browsers and Air Manager."""
    global g_raw_frame
    while True:
        time.sleep(0.04) # Sleep to keep rate matching generator
        with g_frame_lock:
            frame = g_raw_frame
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route("/stream/raw")
def raw_stream():
    """Serves the complete raw MSFS texture sheet as a live streaming video feed."""
    return Response(get_mjpeg_stream_generator(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# =====================================================================
# BACKGROUND THREADS AND MAIN LOOP
# =====================================================================
def start_flask():
    """Starts the production Waitress web server on Port 8090."""
    from waitress import serve
    print("[FLASK] PortalPanel local server started on http://127.0.0.1:8090")
    serve(app, host="127.0.0.1", port=8090, _quiet=True)

if __name__ == "__main__":
    # 1. Start the simulated cockpit texture generator thread
    mock_thread = threading.Thread(target=generate_mock_cockpit_texture, daemon=True)
    mock_thread.start()
    
    # 2. Start the local Flask web server thread on Port 8090
    server_thread = threading.Thread(target=start_flask, daemon=True)
    server_thread.start()
    
    time.sleep(0.5)
    print("[SYSTEM] Launching PortalPanel Control Center...")
    
    # 3. Create the PyWebView standalone desktop window
    webview.create_window(
        title="PortalPanel Studio v1.0",
        url="http://127.0.0.1:8090/",
        width=1280,
        height=720,
        resizable=True
    )
    webview.start()
    
    print("[SYSTEM] PortalPanel closed. Exiting.")
    os._exit(0)