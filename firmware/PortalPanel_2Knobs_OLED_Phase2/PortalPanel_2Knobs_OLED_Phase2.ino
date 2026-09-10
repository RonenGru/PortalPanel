#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// --- WiFi & Server ---
// EDIT BEFORE UPLOAD: replace the placeholders below with your own values.
//   NEVER commit your real WiFi password or IP address to a public repository.
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL     = "http://YOUR_PC_IP_ADDRESS:8090/api/knob";
const char* DATA_URL       = "http://YOUR_PC_IP_ADDRESS:8090/api/data";

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

// --- Encoder 2 (NAV2) Pins ---
#define ENC2_CLK 7
#define ENC2_DT  10
#define ENC2_SW  11

// 0 = STBY mode, 1 = ACTIVE mode
int oled_mode = 0;

struct EncoderState {
  int last_clk;
  int mode; // 0=SMALL, 1=BIG
  unsigned long sw_press_time;
  bool sw_was_pressed;
};

EncoderState enc1 = {0, 0, 0, false};
EncoderState enc2 = {0, 0, 0, false};

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

  // Encoder 1 Pins
  pinMode(ENC1_CLK, INPUT_PULLUP);
  pinMode(ENC1_DT, INPUT_PULLUP);
  pinMode(ENC1_SW, INPUT_PULLUP);
  enc1.last_clk = digitalRead(ENC1_CLK);

  // Encoder 2 Pins
  pinMode(ENC2_CLK, INPUT_PULLUP);
  pinMode(ENC2_DT, INPUT_PULLUP);
  pinMode(ENC2_SW, INPUT_PULLUP);
  enc2.last_clk = digitalRead(ENC2_CLK);

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
  
  // --- Labels ---
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

  // --- Format strings to exactly 2 decimal places ---
  String n1 = nav1_stby;
  if (n1 == "---.--" || n1 == "null" || n1.length() < 4) n1 = "---.--";
  else {
    n1.trim();
    if (n1.indexOf(".") >= 0 && n1.substring(n1.indexOf(".")).length() < 3) n1 += "0";
  }
  
  String n2 = nav2_stby;
  if (n2 == "---.--" || n2 == "null" || n2.length() < 4) n2 = "---.--";
  else {
    n2.trim();
    if (n2.indexOf(".") >= 0 && n2.substring(n2.indexOf(".")).length() < 3) n2 += "0";
  }

  // --- Draw the frequencies (Size 1) ---
  display.setTextSize(1);
  
  // NAV1: "113.30" is 6 chars ≈ 36px wide. Center under the "NAV1 STBY:" label (which starts at 0 and is ~54px wide).
  // (54 - 36) / 2 = ~9. Start at X=9.
  display.setCursor(9, 12);
  display.print(n1);
  
  // NAV2: Center under the "NAV2 STBY:" label (starts at 65, ~54px wide, ends at ~119).
  // 65 + (54 - 36) / 2 = 65 + 9 = 74. Start at X=74.
  display.setCursor(74, 12);
  display.print(n2);
  
  display.display();
}

// --- Generic Encoder Reader ---
void readEncoder(int clkPin, int dtPin, int swPin, EncoderState &state, const char* cmdSmall, const char* cmdBig, const char* cmdSwap) {
  int clk_state = digitalRead(clkPin);
  if (clk_state != state.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) {
      state.last_clk = clk_state;
      return;
    }
    last_turn_time = now;
    
    int dt_state = digitalRead(dtPin);
    if (clk_state != dt_state) {
      sendKnobCommand(state.mode ? cmdBig : cmdSmall); // Right
    } else {
      // For left, we need the left commands. Since strings are passed, we need both. 
      // Let's handle this cleanly by generating left commands on the fly or passing them.
    }
    state.last_clk = clk_state;
  }
  // Note: The above is simplified to only handle right turns. Let's fix this properly below.
}

// Let's write dedicated functions to keep it clean and avoid string manipulation bugs.
void readEncoder1() {
  int clk_state = digitalRead(ENC1_CLK);
  if (clk_state != enc1.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) {
      enc1.last_clk = clk_state;
      return;
    }
    last_turn_time = now;
    
    int dt_state = digitalRead(ENC1_DT);
    if (clk_state != dt_state) {
      sendKnobCommand(enc1.mode ? "NAV1_BIG_RIGHT" : "NAV1_SMALL_RIGHT");
    } else {
      sendKnobCommand(enc1.mode ? "NAV1_BIG_LEFT" : "NAV1_SMALL_LEFT");
    }
    enc1.last_clk = clk_state;
  }
}

void readButton1() {
  int sw_state = digitalRead(ENC1_SW);
  if (sw_state == LOW && !enc1.sw_was_pressed) {
    enc1.sw_press_time = millis();
    enc1.sw_was_pressed = true;
  }
  if (sw_state == HIGH && enc1.sw_was_pressed) {
    unsigned long dur = millis() - enc1.sw_press_time;
    if (dur >= LONG_PRESS_MS) {
      sendKnobCommand("NAV1_SWAP");
      last_data_poll = 0; 
    } else {
      oled_mode = !oled_mode;
      Serial.printf("[OLED] Switched to %s mode\n", oled_mode ? "ACTIVE" : "STBY");
      pollData();
      updateDisplay();
    }
    enc1.sw_was_pressed = false;
  }
}

void readEncoder2() {
  int clk_state = digitalRead(ENC2_CLK);
  if (clk_state != enc2.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) {
      enc2.last_clk = clk_state;
      return;
    }
    last_turn_time = now;
    
    int dt_state = digitalRead(ENC2_DT);
    if (clk_state != dt_state) {
      sendKnobCommand(enc2.mode ? "NAV2_BIG_RIGHT" : "NAV2_SMALL_RIGHT");
    } else {
      sendKnobCommand(enc2.mode ? "NAV2_BIG_LEFT" : "NAV2_SMALL_LEFT");
    }
    enc2.last_clk = clk_state;
  }
}

void readButton2() {
  int sw_state = digitalRead(ENC2_SW);
  if (sw_state == LOW && !enc2.sw_was_pressed) {
    enc2.sw_press_time = millis();
    enc2.sw_was_pressed = true;
  }
  if (sw_state == HIGH && enc2.sw_was_pressed) {
    unsigned long dur = millis() - enc2.sw_press_time;
    if (dur >= LONG_PRESS_MS) {
      sendKnobCommand("NAV2_SWAP");
      last_data_poll = 0; 
    } else {
      // For Encoder 2, we can use the short press to toggle BIG/SMALL mode 
      // so you have a way to switch modes on NAV2 without affecting the OLED.
      enc2.mode = !enc2.mode;
      Serial.printf("[NAV2] Switched to %s mode\n", enc2.mode ? "BIG" : "SMALL");
    }
    enc2.sw_was_pressed = false;
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
  readEncoder2();
  readButton2();
  
  unsigned long now = millis();
  if (now - last_data_poll >= DATA_POLL_MS) {
    last_data_poll = now;
    pollData();
    updateDisplay();
  }
}