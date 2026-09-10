/*
=====================================================================
 PortalPanel — Hardware Knob Controller
 Phase 0: Single Encoder Proof of Concept
=====================================================================
 
 Hardware:
   - ESP32-S3-N16R8 on expansion board (screw terminals)
   - 1x KY-040 rotary encoder (NAV1 for this test)
   
 Wiring:
   KY-040    →  Expansion Board Terminal
   CLK       →  GPIO 4
   DT        →  GPIO 5
   SW        →  GPIO 6
   +         →  3.3V
   GND       →  GND
   
 What it does:
   Turn knob CW  → sends "NAV1_SMALL_RIGHT" to server
   Turn knob CCW → sends "NAV1_SMALL_LEFT" to server
   Push knob     → sends "NAV1_SWAP" to server
   (Long push    → toggles between SMALL and BIG mode)
 
 Server: POST http://<PC_IP>:8090/api/knob with JSON {"cmd": "NAV1_SMALL_RIGHT"}
=====================================================================
*/

#include <WiFi.h>
#include <HTTPClient.h>

// ===================================================================
// CONFIGURATION — Edit these for your network
// ===================================================================
// EDIT BEFORE UPLOAD: replace the placeholders below with your own values.
//   NEVER commit your real WiFi password or IP address to a public repository.
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL     = "http://YOUR_PC_IP_ADDRESS:8090/api/knob";

// ===================================================================
// PIN ASSIGNMENTS (Phase 0 — single encoder for NAV1)
// ===================================================================
#define ENC1_CLK   4   // KY-040 CLK pin
#define ENC1_DT    5   // KY-040 DT pin
#define ENC1_SW    6   // KY-040 SW pin (push button)

// ===================================================================
// ENCODER STATE
// ===================================================================
int enc1_last_clk_state;
int enc1_mode = 0;       // 0 = SMALL (fine), 1 = BIG (coarse)
unsigned long sw1_press_time = 0;
bool sw1_was_pressed = false;

// Debounce timing
unsigned long last_turn_time = 0;
const unsigned long TURN_DEBOUNCE_MS = 5;    // 5ms between detents
const unsigned long LONG_PRESS_MS = 800;     // hold threshold for mode toggle

// ===================================================================
// WIFI STATUS LED (built-in RGB on many S3 boards, GPIO 48)
// ===================================================================
#define STATUS_LED 48
bool led_state = false;

// ===================================================================
// SETUP
// ===================================================================
void setup() {
  Serial.begin(115200);
  delay(500);
  
  Serial.println("\n============================================");
  Serial.println("PortalPanel Knob Controller — Phase 0");
  Serial.println("============================================\n");
  
  // Configure encoder pins
  pinMode(ENC1_CLK, INPUT_PULLUP);
  pinMode(ENC1_DT, INPUT_PULLUP);
  pinMode(ENC1_SW, INPUT_PULLUP);   // Push button: LOW = pressed
  enc1_last_clk_state = digitalRead(ENC1_CLK);
  
  // Status LED
  pinMode(STATUS_LED, OUTPUT);
  digitalWrite(STATUS_LED, LOW);
  
  // Connect to WiFi
  Serial.printf("Connecting to WiFi '%s'", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int wifi_timeout = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    // Toggle LED during connection
    led_state = !led_state;
    digitalWrite(STATUS_LED, led_state);
    if (++wifi_timeout > 40) {  // 20 second timeout
      Serial.println("\n[ERROR] WiFi connection failed! Check SSID/password.");
      Serial.println("[INFO] Rebooting in 5 seconds...");
      delay(5000);
      ESP.restart();
    }
  }
  
  digitalWrite(STATUS_LED, HIGH);  // Solid = connected
  Serial.println("\n[WiFi] Connected!");
  Serial.printf("[WiFi] IP address: %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("[WiFi] Signal strength: %d dBm\n", WiFi.RSSI());
  Serial.printf("[Server] Target: %s\n\n", SERVER_URL);
  Serial.println("Ready! Turn the encoder to test NAV1 frequency.");
  Serial.println("  Turn CW  → NAV1_SMALL_RIGHT (increase standby freq)");
  Serial.println("  Turn CCW → NAV1_SMALL_LEFT  (decrease standby freq)");
  Serial.println("  Push     → NAV1_SWAP         (swap active/stby)");
  Serial.println("  Long push → Toggle SMALL/BIG mode\n");
}

// ===================================================================
// SEND KNOB COMMAND TO SERVER
// ===================================================================
bool sendKnobCommand(const char* cmd) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ERROR] WiFi not connected — command lost!");
    return false;
  }
  
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  
  // Build JSON payload: {"cmd": "NAV1_SMALL_RIGHT"}
  String json = "{\"cmd\":\"";
  json += cmd;
  json += "\"}";
  
  Serial.printf("[SEND] %s → ", cmd);
  
  int httpCode = http.POST(json);
  
  if (httpCode == HTTP_CODE_OK) {
    Serial.println("OK");
    // Blink LED on successful send
    digitalWrite(STATUS_LED, LOW);
    delay(10);
    digitalWrite(STATUS_LED, HIGH);
    http.end();
    return true;
  } else {
    Serial.printf("FAILED (HTTP %d)\n", httpCode);
    if (httpCode > 0) {
      String response = http.getString();
      Serial.printf("[SERVER RESPONSE] %s\n", response.c_str());
    }
    http.end();
    return false;
  }
}

// ===================================================================
// READ ENCODER — called every loop iteration
// ===================================================================
void readEncoder1() {
  int clk_state = digitalRead(ENC1_CLK);
  
  // Detect transition (CLK changed)
  if (clk_state != enc1_last_clk_state) {
    // Debounce: ignore transitions too close together
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) {
      enc1_last_clk_state = clk_state;
      return;
    }
    last_turn_time = now;
    
    // Determine direction: compare CLK and DT
    int dt_state = digitalRead(ENC1_DT);
    
    if (clk_state != dt_state) {
      // Clockwise (right)
      if (enc1_mode == 0) {
        sendKnobCommand("NAV1_SMALL_RIGHT");
      } else {
        sendKnobCommand("NAV1_BIG_RIGHT");
      }
    } else {
      // Counter-clockwise (left)
      if (enc1_mode == 0) {
        sendKnobCommand("NAV1_SMALL_LEFT");
      } else {
        sendKnobCommand("NAV1_BIG_LEFT");
      }
    }
    
    enc1_last_clk_state = clk_state;
  }
}

// ===================================================================
// READ PUSH BUTTON — called every loop iteration
// ===================================================================
void readButton1() {
  int sw_state = digitalRead(ENC1_SW);
  
  // Button pressed (active LOW)
  if (sw_state == LOW && !sw1_was_pressed) {
    sw1_press_time = millis();
    sw1_was_pressed = true;
  }
  
  // Button released
  if (sw_state == HIGH && sw1_was_pressed) {
    unsigned long press_duration = millis() - sw1_press_time;
    
    if (press_duration >= LONG_PRESS_MS) {
      // Long press → toggle BIG/SMALL mode
      enc1_mode = !enc1_mode;
      Serial.printf("[MODE] Switched to %s mode\n", 
                     enc1_mode ? "BIG (coarse)" : "SMALL (fine)");
    } else {
      // Short press → swap
      sendKnobCommand("NAV1_SWAP");
    }
    
    sw1_was_pressed = false;
  }
}

// ===================================================================
// MAIN LOOP
// ===================================================================
void loop() {
  // Check WiFi status — blink LED if disconnected
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(STATUS_LED, !digitalRead(STATUS_LED));
    delay(200);
    return;
  }
  
  // Read encoder and button (non-blocking)
  readEncoder1();
  readButton1();
}