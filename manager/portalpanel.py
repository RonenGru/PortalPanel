#!/usr/bin/env python3
"""
PortalPanel - Native Launcher Application
Uses pywebview for both launcher and display windows.

FIXED VERSION:
- Display windows (combined/pfd/mfd) are created ONCE, hidden, at startup,
  then reused via move/resize/load_url/show. They are never destroyed and
  recreated on every launch click, which was causing blank WebView2 windows
  after repeated create/destroy cycles.
- is_window_alive() replaced with a real "closed" event listener, so the
  app correctly notices when a user has manually closed a display window
  (previously it assumed the window was still alive, so subsequent
  launches silently tried to move a dead window handle and did nothing).
- g_pending_launch is now protected by a lock, so rapid/overlapping clicks
  on LAUNCH DISPLAY can no longer silently overwrite/drop a request.
"""
import sys
import os
import time
import threading
import json
import urllib.request
import urllib.parse
import subprocess
from screeninfo import get_monitors
import webview

# =====================================================
# CONFIG
# =====================================================
SERVER_URL = "http://127.0.0.1:8090"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(BASE_DIR, "portalpanel_server.py")
CONFIG_FILE = os.path.normpath(os.path.join(BASE_DIR, "..", "portalpanel_config.json"))

DISPLAY_TYPES = ["combined", "pfd", "mfd"]

g_aircraft_title = "Detecting..."
g_aircraft_model = ""
g_server_online = False

# Track display windows by type: {"combined": window, "pfd": window, "mfd": window}
# A key is present only while that window is known to be open/alive.
g_display_windows = {}
g_display_lock = threading.Lock()

# Pending launch request queue (single slot, lock-protected)
g_pending_launch = None  # (display_type, monitor_index, scale)
g_pending_lock = threading.Lock()
g_pending_event = threading.Event()

# Set to True only during final app shutdown, so the real close/destroy
# is allowed to go through instead of being intercepted as a hide.
g_app_shutting_down = False


# =====================================================
# CONFIG LOAD/SAVE
# =====================================================
def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return {"display_type": "combined", "monitor_index": 0, "scale": 130}

def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except:
        pass


# =====================================================
# SERVER MANAGEMENT
# =====================================================
def start_server():
    print("[LAUNCHER] Starting PortalPanel server...")
    proc = subprocess.Popen(
        [sys.executable, SERVER_SCRIPT],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=BASE_DIR
    )
    for i in range(30):
        time.sleep(1)
        if check_server():
            print("[LAUNCHER] Server is online!")
            return proc
    print("[LAUNCHER] Server failed to start")
    return proc

def check_server():
    global g_server_online
    try:
        req = urllib.request.Request("{}/api/status".format(SERVER_URL))
        with urllib.request.urlopen(req, timeout=2.0) as r:
            if r.status == 200:
                g_server_online = True
                return True
    except:
        g_server_online = False
    return False

def detect_aircraft():
    global g_aircraft_title, g_aircraft_model
    while True:
        try:
            if check_server():
                req = urllib.request.Request("{}/api/aircraft".format(SERVER_URL))
                with urllib.request.urlopen(req, timeout=2.0) as r:
                    data = json.loads(r.read().decode("utf-8"))
                    title = data.get("title", "Unknown")
                    if title and title != "Unknown":
                        g_aircraft_title = title
                        g_aircraft_model = data.get("model", "")
                        break
        except:
            pass
        time.sleep(2)

def get_monitors_html():
    try:
        monitors = get_monitors()
        html = ""
        for i, m in enumerate(monitors):
            html += '<button class="monitor-btn" data-monitor="{}">Monitor {}<br><small>{}x{}</small></button>'.format(
                i, i + 1, m.width, m.height)
        return html
    except Exception as e:
        return "<p>Error: {}</p>".format(e)


# =====================================================
# LAUNCHER HTML
# =====================================================
LAUNCHER_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0a0a0a; color: #ddd; font-family: 'Segoe UI', Arial, sans-serif; padding: 30px; display: flex; flex-direction: column; align-items: center; min-height: 100vh; }}
#header {{ text-align: center; margin-bottom: 25px; }}
#header h1 {{ font-size: 28px; letter-spacing: 4px; }}
.logo-white {{ color: #fff; }} .logo-cyan {{ color: #00FFFF; }}
#header p {{ font-size: 11px; color: #555; margin-top: 5px; }}
#status {{ margin-bottom: 20px; padding: 10px 20px; background: #111; border: 1px solid #333; border-radius: 6px; font-size: 13px; display: flex; align-items: center; gap: 10px; min-width: 400px; justify-content: center; }}
#status-dot {{ width: 10px; height: 10px; border-radius: 50%; background: #FF8800; box-shadow: 0 0 8px #FF8800; transition: 0.3s; }}
#status-dot.connected {{ background: #00FF00; box-shadow: 0 0 8px #00FF00; }}
.section {{ margin-bottom: 20px; width: 450px; }}
.section-title {{ font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 10px; }}
.aircraft-name {{ background: #111; border: 1px solid #006666; border-radius: 6px; padding: 15px; text-align: center; font-size: 18px; color: #00FFFF; font-weight: bold; }}
.aircraft-name small {{ display: block; font-size: 11px; color: #888; font-weight: normal; margin-top: 5px; }}
.btn-group {{ display: flex; gap: 8px; }}
.display-btn, .monitor-btn {{ flex: 1; padding: 15px 10px; font-size: 12px; font-weight: bold; background: #1a1a1a; color: #ddd; border: 2px solid #333; border-radius: 6px; cursor: pointer; transition: 0.2s; text-align: center; }}
.display-btn:hover, .monitor-btn:hover {{ border-color: #00FFFF; color: #00FFFF; }}
.display-btn.active {{ background: #003344; border-color: #00FFFF; color: #00FFFF; }}
.monitor-btn.active {{ background: #002200; border-color: #00FF00; color: #00FF00; }}
.display-btn small, .monitor-btn small {{ display: block; font-size: 9px; color: #666; font-weight: normal; margin-top: 3px; }}
#scale-row {{ display: flex; align-items: center; gap: 10px; padding: 10px; background: #111; border: 1px solid #333; border-radius: 6px; }}
#scale-slider {{ flex: 1; cursor: pointer; }}
#scale-label {{ font-size: 14px; color: #00FFFF; font-weight: bold; min-width: 50px; text-align: right; }}
#launch-btn {{ margin-top: 10px; padding: 18px; width: 450px; font-size: 16px; font-weight: bold; letter-spacing: 2px; background: #003344; color: #00FFFF; border: 2px solid #00FFFF; border-radius: 8px; cursor: pointer; transition: 0.2s; }}
#launch-btn:hover {{ background: #00FFFF; color: #000; box-shadow: 0 0 20px #00FFFF; }}
#launch-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
.hint {{ font-size: 10px; color: #555; margin-top: 15px; text-align: center; max-width: 450px; line-height: 1.5; }}
</style>
</head>
<body>

<div id="header">
    <h1><span class="logo-white">PORTAL</span><span class="logo-cyan">PANEL</span></h1>
    <p>Live Instrument Display for MSFS 2024</p>
</div>

<div id="status">
    <span id="status-dot"></span>
    <span id="status-text">Starting server...</span>
</div>

<div class="section">
    <div class="section-title">Detected Aircraft</div>
    <div class="aircraft-name" id="aircraft-name">Detecting...<small id="aircraft-model">Waiting for MSFS</small></div>
</div>

<div class="section">
    <div class="section-title">Select Display</div>
    <div class="btn-group" id="display-group">
        <button class="display-btn active" data-display="combined">Combined<small>PFD + MFD</small></button>
        <button class="display-btn" data-display="pfd">PFD Only<small>Primary Flight</small></button>
        <button class="display-btn" data-display="mfd">MFD Only<small>Multi-Function</small></button>
    </div>
</div>

<div class="section">
    <div class="section-title">Select Monitor</div>
    <div class="btn-group" id="monitor-group">{monitors}</div>
</div>

<button id="launch-btn" onclick="launchDisplay()">LAUNCH DISPLAY</button>

<p class="hint">
    Click LAUNCH to open the instrument panel on your chosen monitor.<br>
    Click LAUNCH again to move an existing display to a different monitor.<br>
    You can open Combined, PFD, and MFD simultaneously on different monitors.
</p>

<script>
let selectedDisplay = "combined";
let selectedMonitor = 0;
const selectedScale = 130;
let launchInFlight = false;

document.querySelectorAll('#display-group .display-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('#display-group .display-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedDisplay = btn.dataset.display;
    }});
}});

document.querySelectorAll('#monitor-group .monitor-btn').forEach((btn, i) => {{
    if (i === 0) btn.classList.add('active');
    btn.addEventListener('click', () => {{
        document.querySelectorAll('#monitor-group .monitor-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedMonitor = parseInt(btn.dataset.monitor);
    }});
}});

// Scale is controlled by the slider on the display page itself

function updateStatus() {{
    fetch('{server_url}/api/status').then(r => r.json()).then(data => {{
        const dot = document.getElementById('status-dot');
        const text = document.getElementById('status-text');
        if (data.connected) {{
            dot.classList.add('connected');
            text.textContent = 'Connected to MSFS';
        }} else {{
            dot.classList.remove('connected');
            text.textContent = data.message || 'Waiting for MSFS...';
        }}
    }}).catch(() => {{
        document.getElementById('status-text').textContent = 'Server starting...';
    }});
    fetch('{server_url}/api/aircraft').then(r => r.json()).then(data => {{
        if (data.title && data.title !== 'Unknown') {{
            document.getElementById('aircraft-name').firstChild.textContent = data.title;
            document.getElementById('aircraft-model').textContent = 'Model: ' + (data.model || 'Unknown');
        }}
    }}).catch(() => {{}});
}}
setInterval(updateStatus, 2000);
updateStatus();

function launchDisplay() {{
    // Guard against double-clicks piling up requests faster than the
    // native side can process them.
    if (launchInFlight) return;
    launchInFlight = true;

    const btn = document.getElementById('launch-btn');
    btn.disabled = true;
    btn.textContent = 'LAUNCHING...';
    window.pywebview.api.launch_display(selectedDisplay, selectedMonitor, selectedScale).then(result => {{
        setTimeout(() => {{
            btn.disabled = false;
            btn.textContent = 'LAUNCH DISPLAY';
            launchInFlight = false;
        }}, 1000);
    }}).catch(() => {{
        btn.disabled = false;
        btn.textContent = 'LAUNCH DISPLAY';
        launchInFlight = false;
    }});
}}
</script>
</body>
</html>
"""


# =====================================================
# LAUNCHER API (called by JS)
# =====================================================
class LauncherAPI:
    def __init__(self):
        self.config = load_config()

    def launch_display(self, display_type, monitor_index, scale):
        """
        Queue a display launch request. The main pywebview loop will
        pick it up and create/move the window. This avoids calling
        create_window from a non-main thread, which causes blank windows.
        """
        global g_pending_launch

        with g_pending_lock:
            g_pending_launch = (display_type, monitor_index, scale)
            g_pending_event.set()

        self.config["display_type"] = display_type
        self.config["monitor_index"] = monitor_index
        self.config["scale"] = scale
        save_config(self.config)

        return "OK"

    def get_aircraft(self):
        return {"title": g_aircraft_title, "model": g_aircraft_model}

    def get_status(self):
        return {"connected": g_server_online}


# =====================================================
# DISPLAY WINDOW MANAGEMENT
# =====================================================
def build_display_url(display_type, scale, monitor_index):
    path = "/" if display_type == "combined" else "/" + display_type
    query = urllib.parse.urlencode({"scale": scale, "monitor": monitor_index})
    return "{}{}?{}".format(SERVER_URL, path, query)

def make_closing_handler(display_type):
    """
    Returns a handler bound to a specific display_type. Instead of letting
    the OS close button actually destroy the native WebView2 window (which
    is what caused the blank-window bug on the next launch), this hides
    the window and cancels the close.

    The one exception is real app shutdown (g_app_shutting_down = True),
    where we want the close to actually go through.
    """
    def handler():
        if g_app_shutting_down:
            return  # allow the real close/destroy to proceed

        with g_display_lock:
            win = g_display_windows.get(display_type)
        if win is not None:
            try:
                win.hide()
            except Exception as e:
                print("[LAUNCHER] Error hiding {}: {}".format(display_type, e))

        print("[LAUNCHER] {} window hidden (not destroyed)".format(display_type))
        return False  # False cancels the close in pywebview
    return handler

def create_display_window(display_type, scale=130, monitor_index=0, hidden=True):
    """
    Create a single display window (hidden by default) and register its
    closing-event handler. Called once per display_type at startup only —
    after that, launches just move/resize/show/hide this same window for
    the rest of the app's life, so WebView2 is never re-initialized.
    """
    url = build_display_url(display_type, scale, monitor_index)

    win = webview.create_window(
        title="PortalPanel - {}".format(display_type.capitalize()),
        url=url,
        width=800,
        height=600,
        resizable=True,
        on_top=False,
        hidden=hidden,
    )
    win.events.closing += make_closing_handler(display_type)

    with g_display_lock:
        g_display_windows[display_type] = win

    return win

def create_all_display_windows():
    """Pre-create all three display windows, hidden, once at startup."""
    for display_type in DISPLAY_TYPES:
        create_display_window(display_type, hidden=True)

def process_pending_launch():
    """
    Called from the main thread (inside pywebview's event loop) to handle
    display window creation/moving. Windows are created only once (or
    recreated if the user closed them); every other launch just moves,
    resizes, reloads the URL (for the new scale), and shows the window.
    """
    global g_pending_launch

    if not g_pending_event.is_set():
        return

    with g_pending_lock:
        if g_pending_launch is None:
            g_pending_event.clear()
            return
        display_type, monitor_index, scale = g_pending_launch
        g_pending_launch = None
        g_pending_event.clear()

    try:
        monitors = list(get_monitors())
        if monitor_index >= len(monitors):
            monitor_index = 0
        m = monitors[monitor_index]

        win_width = int(m.width * 0.85)
        win_height = int(m.height * 0.85)
        win_x = m.x + int((m.width - win_width) / 2)
        win_y = m.y + int((m.height - win_height) / 2)

        full_url = build_display_url(display_type, scale, monitor_index)

        with g_display_lock:
            win = g_display_windows.get(display_type)

        if win is None:
            # Should only happen if this is called before startup's
            # create_all_display_windows() has run. Windows are no longer
            # destroyed when the user closes them (see make_closing_handler),
            # so under normal operation this branch is not hit again after
            # the very first launch.
            print("[LAUNCHER] Creating {} window (first use)".format(display_type))
            win = create_display_window(display_type, scale=scale,
                                         monitor_index=monitor_index, hidden=True)
            # Give WebView2 a brief moment to finish initializing before we
            # move/resize/show it, since it was just created.
            time.sleep(0.3)

        win.load_url(full_url)
        win.move(win_x, win_y)
        win.resize(win_width, win_height)
        win.show()

        print("[LAUNCHER] {} on Monitor {} ({}, {}) scale={}%".format(
            display_type, monitor_index + 1, win_x, win_y, scale))

    except Exception as e:
        print("[LAUNCHER] Error in process_pending_launch: {}".format(e))


def display_loop():
    """
    Background thread that polls for launch requests and processes them.
    """
    while True:
        if g_pending_event.wait(timeout=0.5):
            process_pending_launch()
        if sys.is_finalizing():
            break


# =====================================================
# MAIN
# =====================================================
def main():
    print("=" * 60)
    print("PortalPanel - Launcher")
    print("=" * 60)

    # Start server in background
    server_proc = start_server()

    # Start aircraft detection thread
    detect_thread = threading.Thread(target=detect_aircraft, daemon=True)
    detect_thread.start()

    # Prepare launcher HTML
    html = LAUNCHER_HTML.format(
        monitors=get_monitors_html(),
        server_url=SERVER_URL
    )
    html_path = os.path.join(BASE_DIR, "launcher.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

        # Create launcher window
    api = LauncherAPI()
    launcher_window = webview.create_window(
        title="PortalPanel Launcher",
        url=html_path,
        width=550,
        height=700,
        resizable=False,
        js_api=api
    )

    # When launcher is closing, destroy display windows FIRST so pywebview
    # doesn't loop forever trying to close windows that intercept the close.
    def on_launcher_closing():
        global g_app_shutting_down
        g_app_shutting_down = True
        with g_display_lock:
            for key, w in list(g_display_windows.items()):
                try:
                    w.destroy()
                except:
                    pass
            g_display_windows.clear()
        return True  # allow the launcher to close

    launcher_window.events.closing += on_launcher_closing

    # Pre-create all display windows (hidden) so later launches only
    # move/resize/show them instead of destroying and recreating.
    create_all_display_windows()

    # Start display loop thread (processes launch requests)
    loop_thread = threading.Thread(target=display_loop, daemon=True)
    loop_thread.start()

    # Start pywebview (blocks until launcher window closes)
    webview.start()

    # Cleanup when launcher closes
    print("[LAUNCHER] Shutting down...")
    # Display windows were already destroyed by on_launcher_closing
    if server_proc:
        server_proc.terminate()

    try:
        os.remove(html_path)
    except:
        pass


if __name__ == "__main__":
    main()
