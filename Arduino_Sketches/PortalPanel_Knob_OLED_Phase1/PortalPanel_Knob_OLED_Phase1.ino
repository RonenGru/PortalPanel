#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// --- WiFi & Server ---
const char* WIFI_SSID     = "Reelstories";
const char* WIFI_PASSWORD = "Me@gh@n1";
const char* SERVER_URL     = "http://192.168.0.162:8090/api/knob";
const char* DATA_URL       = "http://192.168.0.162:8090/api/data";

// --- OLED Config ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 32
#define OLED_RESET     -1
#define SCREEN_ADDRESS 0x3C
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// --- Encoder 1 (NAV1) Pins ---
#define ENC1_CLK 4
#define ENC1_DT  5
#define ENC1_SW  6

int enc1_last_clk;
int enc1_mode = 0; // 0=SMALL, 1=BIG
// 0 = STBY mode, 1 = ACTIVE mode
int oled_mode = 0;
unsigned long sw1_press_time = 0;
bool sw1_was_pressed = false;
unsigned long last_turn_time = 0;
const unsigned long TURN_DEBOUNCE_MS = 5;
const unsigned long LONG_PRESS_MS = 800;

#define STATUS_LED 48

// --- Data Polling ---
unsigned long last_data_poll = 0;
const unsigned long DATA_POLL_MS = 200;
String nav1_stby = "---.--";
String nav2_stby = "---.--";

void setup() {
  Serial.begin(115200);
  
  // OLED Init
  Wire.begin(8, 9); // SDA=8, SCL=9
  if(!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println("[OLED] SSD1306 allocation failed");
  }
  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0,0);
  display.println("PortalPanel");
  display.display();

  // Encoder Pins
  pinMode(ENC1_CLK, INPUT_PULLUP);
  pinMode(ENC1_DT, INPUT_PULLUP);
  pinMode(ENC1_SW, INPUT_PULLUP);
  enc1_last_clk = digitalRead(ENC1_CLK);

  pinMode(STATUS_LED, OUTPUT);
  digitalWrite(STATUS_LED, LOW);

  // WiFi
  Serial.printf("Connecting to WiFi '%s'", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int timeout = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    digitalWrite(STATUS_LED, !digitalRead(STATUS_LED));
    if (++timeout > 40) ESP.restart();
  }
  digitalWrite(STATUS_LED, HIGH);
  Serial.println("\n[WiFi] Connected!");
  Serial.printf("IP: %s | RSSI: %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  
  display.clearDisplay();
  display.setCursor(0,0);
  display.println("Connected!");
  display.display();
  delay(1000);
}

bool sendKnobCommand(const char* cmd) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  String json = "{\"cmd\":\"" + String(cmd) + "\"}";
  int httpCode = http.POST(json);
  http.end();
  return (httpCode == HTTP_CODE_OK);
}

void pollData() {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(DATA_URL);
  int httpCode = http.GET();
  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    // Manual JSON parsing (avoids extra heavy JSON library)
    String n1_key = oled_mode ? "\"nav1_freq\":" : "\"nav1_stby_freq\":";
    String n2_key = oled_mode ? "\"nav2_freq\":" : "\"nav2_stby_freq\":";
    
    int nav1_idx = payload.indexOf(n1_key);
    if (nav1_idx >= 0) {
      int start = payload.indexOf(":", nav1_idx) + 1;
      int end = payload.indexOf(",", start);
      if (end < 0) end = payload.indexOf("}", start);
      String val = payload.substring(start, end);
      val.trim();
      if (val.equals("null") || val.length() < 1) nav1_stby = "---.--";
      else nav1_stby = val;
    }
    int nav2_idx = payload.indexOf(n2_key);
    if (nav2_idx >= 0) {
      int start = payload.indexOf(":", nav2_idx) + 1;
      int end = payload.indexOf(",", start);
      if (end < 0) end = payload.indexOf("}", start);
      String val = payload.substring(start, end);
      val.trim();
      if (val.equals("null") || val.length() < 1) nav2_stby = "---.--";
      else nav2_stby = val;
    }
  }
  http.end();
}

void updateDisplay() {
  display.clearDisplay();
  
    // Title row
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  if (oled_mode == 0) {
    display.print("NAV1 STBY:");
    display.setCursor(65, 0);
    display.print("NAV2 STBY:");
  } else {
    display.print("NAV1 ACTV:");
    display.setCursor(65, 0);
    display.print("NAV2 ACTV:");
  }

     // --- Format strings to 2 decimal places ---
  String n1 = nav1_stby;
  if (n1 == "---.--" || n1 == "null" || n1.length() < 4) n1 = "---.--";
  n1.trim();
  
  String n2 = nav2_stby;
  if (n2 == "---.--" || n2 == "null" || n2.length() < 4) n2 = "---.--";
  n2.trim();

  // --- Draw the frequencies ---
  // We might need to trim the decimal down so it fits.
  
  // NAV1 (Left side)
  display.setTextSize(2);            // Medium size
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 16);          // Start at bottom left
  display.print(n1);                 // Print up to 5 chars ("113.9" fits, "113.90" misses the '0')
  
  // NAV2 (Right side)
  display.setCursor(68, 16);
  display.print(n2);
  
  display.display();
}

void readEncoder1() {
  int clk_state = digitalRead(ENC1_CLK);
  if (clk_state != enc1_last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) {
      enc1_last_clk = clk_state;
      return;
    }
    last_turn_time = now;
    
    int dt_state = digitalRead(ENC1_DT);
    if (clk_state != dt_state) {
      sendKnobCommand(enc1_mode ? "NAV1_BIG_RIGHT" : "NAV1_SMALL_RIGHT");
    } else {
      sendKnobCommand(enc1_mode ? "NAV1_BIG_LEFT" : "NAV1_SMALL_LEFT");
    }
    enc1_last_clk = clk_state;
  }
}

void readButton1() {
  int sw_state = digitalRead(ENC1_SW);
  if (sw_state == LOW && !sw1_was_pressed) {
    sw1_press_time = millis();
    sw1_was_pressed = true;
  }
    if (sw_state == HIGH && sw1_was_pressed) {
    unsigned long dur = millis() - sw1_press_time;
    
    if (dur >= LONG_PRESS_MS) {
      // Long press → SWAP in MSFS
      sendKnobCommand("NAV1_SWAP");
      // Force immediate data refresh so we see the swap happen
      last_data_poll = 0; 
    } else {
      // Short press → Toggle OLED between STBY and ACTV
      oled_mode = !oled_mode;
      Serial.printf("[OLED] Switched to %s mode\n", oled_mode ? "ACTIVE" : "STBY");
      // Force immediate data refresh and screen update
      pollData();
      updateDisplay();
    }
    
    sw1_was_pressed = false;
  }
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(STATUS_LED, !digitalRead(STATUS_LED));
    delay(200);
    return;
  }
  
  readEncoder1();
  readButton1();
  
  unsigned long now = millis();
  if (now - last_data_poll >= DATA_POLL_MS) {
    last_data_poll = now;
    pollData();
    updateDisplay();
  }
}