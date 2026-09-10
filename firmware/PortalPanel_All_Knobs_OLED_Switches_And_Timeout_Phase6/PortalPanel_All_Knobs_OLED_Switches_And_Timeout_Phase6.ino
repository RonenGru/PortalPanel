#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Fonts/FreeSansBold9pt7b.h>

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

// --- Encoder Pins ---
#define ENC1_CLK 4
#define ENC1_DT  5
#define ENC1_SW  6
#define ENC2_CLK 7
#define ENC2_DT  10
#define ENC2_SW  11
#define ENC3_CLK 12
#define ENC3_DT  13
#define ENC3_SW  14
#define ENC4_CLK 15
#define ENC4_DT  16
#define ENC4_SW  17
#define ENC5_CLK 38
#define ENC5_DT  39
#define ENC5_SW  40

// --- Momentary Toggle Buttons (active LOW, internal pullup) ---
#define BTN_CDI  1
#define BTN_DME  2
#define BTN_NRST 42

// 0 = STBY mode, 1 = ACTIVE mode
int oled_mode = 0;

struct EncoderState {
  int last_clk;
  int mode; // 0 = Small (0.05 MHz), 1 = Big (1.0 MHz)
  unsigned long sw_press_time;
  bool sw_was_pressed;
  unsigned long last_turn_time;
};

EncoderState enc1 = {0, 0, 0, false, 0};
EncoderState enc2 = {0, 0, 0, false, 0};
EncoderState enc3 = {0, 0, 0, false, 0};
EncoderState enc4 = {0, 0, 0, false, 0};
EncoderState enc5 = {0, 0, 0, false, 0};

unsigned long last_turn_time = 0;
const unsigned long TURN_DEBOUNCE_MS = 2;
const unsigned long LONG_PRESS_MS = 800;
const unsigned long BTN_DEBOUNCE_MS = 50;

#define STATUS_LED 48

unsigned long last_data_poll = 0;
const unsigned long DATA_POLL_MS = 200;

// --- INSTANT LOCAL PREDICTION FREQUENCIES ---
float nav1_local = 110.50f;
float nav2_local = 113.80f;
bool nav1_has_data = false;
bool nav2_has_data = false;
unsigned long last_local_tune_time = 0;
const unsigned long POLL_IGNORE_WINDOW_MS = 350; // Protect local tuning from stale Wi-Fi packets

// --- AUTO-SLEEP CONFIGURATION (15 Minutes) ---
const unsigned long SLEEP_TIMEOUT_MS = 15UL * 60UL * 1000UL; // 15 minutes
unsigned long last_activity_time = 0;
bool is_sleeping = false;

// Button debounce state
bool btn_cdi_last = HIGH;
bool btn_dme_last = HIGH;
bool btn_nrst_last = HIGH;
unsigned long btn_cdi_time = 0;
unsigned long btn_dme_time = 0;
unsigned long btn_nrst_time = 0;

void wakeDisplay();
void updateDisplay();

void recordActivity() {
  last_activity_time = millis();
  if (is_sleeping) {
    wakeDisplay();
  }
}

void sleepDisplay() {
  is_sleeping = true;
  display.clearDisplay();
  display.display();
  display.ssd1306_command(SSD1306_DISPLAYOFF);
  Serial.println("[OLED] Auto-sleep activated.");
}

void wakeDisplay() {
  is_sleeping = false;
  display.ssd1306_command(SSD1306_DISPLAYON);
  last_data_poll = 0;
  updateDisplay();
  Serial.println("[OLED] Display awake.");
}

// Helper: Adjust frequency locally (0ms lag) with VOR band bounds (108.00 - 117.95 MHz)
void adjustLocalFrequency(float &freq, bool right, bool big_step) {
  float step = big_step ? 1.00f : 0.05f;
  if (right) freq += step;
  else freq -= step;
  
  // Clean floating point precision issues
  freq = round(freq * 20.0f) / 20.0f;
  
  // Wrap-around VOR Navigation band
  if (freq > 117.975f) freq = 108.00f;
  if (freq < 107.975f) freq = 117.95f;
  
  last_local_tune_time = millis();
  updateDisplay(); // REDRAW OLED INSTANTLY!
}

int getRepetitions(EncoderState &state) {
  unsigned long now = millis();
  if (state.last_turn_time == 0) { state.last_turn_time = now; return 1; }
  unsigned long dt = now - state.last_turn_time;
  state.last_turn_time = now;
  if (dt < 25) return 3;
  if (dt < 60) return 2;
  return 1;
}

void setup() {
  Serial.begin(115200);
  
  Wire.begin(8, 9);
  if(!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println("[OLED] SSD1306 allocation failed");
  }

  // --- OVERCLOCK OLED REFRESH RATE (VR Passthrough Anti-Scanline) ---
  display.ssd1306_command(SSD1306_SETDISPLAYCLOCKDIV);
  display.ssd1306_command(0xF0);

  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0,0);
  display.println("PortalPanel");
  display.display();

  pinMode(ENC1_CLK, INPUT_PULLUP); pinMode(ENC1_DT, INPUT_PULLUP); pinMode(ENC1_SW, INPUT_PULLUP);
  enc1.last_clk = digitalRead(ENC1_CLK);
  pinMode(ENC2_CLK, INPUT_PULLUP); pinMode(ENC2_DT, INPUT_PULLUP); pinMode(ENC2_SW, INPUT_PULLUP);
  enc2.last_clk = digitalRead(ENC2_CLK);
  pinMode(ENC3_CLK, INPUT_PULLUP); pinMode(ENC3_DT, INPUT_PULLUP); pinMode(ENC3_SW, INPUT_PULLUP);
  enc3.last_clk = digitalRead(ENC3_CLK);
  pinMode(ENC4_CLK, INPUT_PULLUP); pinMode(ENC4_DT, INPUT_PULLUP); pinMode(ENC4_SW, INPUT_PULLUP);
  enc4.last_clk = digitalRead(ENC4_CLK);
  pinMode(ENC5_CLK, INPUT_PULLUP); pinMode(ENC5_DT, INPUT_PULLUP); pinMode(ENC5_SW, INPUT_PULLUP);
  enc5.last_clk = digitalRead(ENC5_CLK);

  // Toggle buttons (active LOW)
  pinMode(BTN_CDI, INPUT_PULLUP);
  pinMode(BTN_DME, INPUT_PULLUP);
  pinMode(BTN_NRST, INPUT_PULLUP);
  btn_cdi_last = digitalRead(BTN_CDI);
  btn_dme_last = digitalRead(BTN_DME);
  btn_nrst_last = digitalRead(BTN_NRST);

  pinMode(STATUS_LED, OUTPUT);
  digitalWrite(STATUS_LED, LOW);

  Serial.printf("Connecting to WiFi '%s'", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int timeout = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
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

  last_activity_time = millis();
}

bool sendKnobCommand(const char* cmd) {
  recordActivity();
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  String json = "{\"cmd\":\"" + String(cmd) + "\"}";
  int httpCode = http.POST(json);
  http.end();
  return (httpCode == HTTP_CODE_OK);
}

// --- Button debouncer ---
void readButton(int pin, bool &last, unsigned long &last_time, const char* cmd) {
  int state = digitalRead(pin);
  unsigned long now = millis();
  if (state == LOW && last == HIGH && (now - last_time) > BTN_DEBOUNCE_MS) {
    last_time = now;
    last = state;
    recordActivity();
    sendKnobCommand(cmd);
    Serial.printf("[BTN] %s\n", cmd);
  }
  last = state;
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
    
    // Parse NAV1
    int nav1_idx = payload.indexOf(n1_key);
    if (nav1_idx >= 0) {
      int start = payload.indexOf(":", nav1_idx) + 1;
      int end = payload.indexOf(",", start);
      if (end < 0) end = payload.indexOf("}", start);
      String val = payload.substring(start, end);
      val.trim();
      if (!val.equals("null") && val.length() >= 4) {
        float s_val = val.toFloat();
        nav1_has_data = true;
        // Only reconcile if we aren't actively spinning the knob
        if (millis() - last_local_tune_time > POLL_IGNORE_WINDOW_MS) {
          nav1_local = s_val;
        }
      }
    }
    
    // Parse NAV2
    int nav2_idx = payload.indexOf(n2_key);
    if (nav2_idx >= 0) {
      int start = payload.indexOf(":", nav2_idx) + 1;
      int end = payload.indexOf(",", start);
      if (end < 0) end = payload.indexOf("}", start);
      String val = payload.substring(start, end);
      val.trim();
      if (!val.equals("null") && val.length() >= 4) {
        float s_val = val.toFloat();
        nav2_has_data = true;
        // Only reconcile if we aren't actively spinning the knob
        if (millis() - last_local_tune_time > POLL_IGNORE_WINDOW_MS) {
          nav2_local = s_val;
        }
      }
    }
  }
  http.end();
}

void updateDisplay() {
  if (is_sleeping) return;

  display.clearDisplay();
  
  // --- TOP ROW: SMALL LABELS (Standard Font) ---
  display.setFont(); // Default small 5x7 font
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  
  display.setCursor(4, 2);
  if (oled_mode == 0) {
    display.print(enc1.mode ? "N1 [MHZ]" : "NAV1 STBY");
    display.setCursor(68, 2);
    display.print(enc2.mode ? "N2 [MHZ]" : "NAV2 STBY");
  } else {
    display.print("NAV1 ACTV");
    display.setCursor(68, 2);
    display.print("NAV2 ACTV");
  }

  // --- BOTTOM ROW: BIG BOLD FREQUENCIES (FreeSansBold 9pt) ---
  display.setFont(&FreeSansBold9pt7b); // Switch to bold, larger font
  display.setTextSize(1);
  
  char n1_buf[10];
  char n2_buf[10];
  
  if (nav1_has_data) dtostrf(nav1_local, 0, 2, n1_buf);
  else strcpy(n1_buf, "---.--");
  
  if (nav2_has_data) dtostrf(nav2_local, 0, 2, n2_buf);
  else strcpy(n2_buf, "---.--");

  // In custom fonts, setCursor Y is the baseline (bottom) of the text
  display.setCursor(2, 28); 
  display.print(n1_buf);
  
  display.setCursor(66, 28); 
  display.print(n2_buf);
  
  // Reset font back to default for any other menus
  display.setFont(); 
  
  display.display();
}

// --- Encoders (1=NAV1, 2=NAV2, 3=HDG, 4=CRS, 5=BARO) ---
void readEnc1() {
  int c = digitalRead(ENC1_CLK);
  if (c != enc1.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) { enc1.last_clk = c; return; }
    last_turn_time = now;
    recordActivity();
    int reps = getRepetitions(enc1);
    bool right = (c != digitalRead(ENC1_DT));
    
    // 1. INSTANT LOCAL UPDATE ON SCREEN (0 ms latency)
    for (int i = 0; i < reps; i++) {
      adjustLocalFrequency(nav1_local, right, enc1.mode);
    }
    
    // 2. Send SimConnect command over Wi-Fi in background
    const char* cmd = enc1.mode ? (right ? "NAV1_BIG_RIGHT" : "NAV1_BIG_LEFT")
                                : (right ? "NAV1_SMALL_RIGHT" : "NAV1_SMALL_LEFT");
    for (int i = 0; i < reps; i++) sendKnobCommand(cmd);
    enc1.last_clk = c;
  }
}

void readBtn1() {
  int s = digitalRead(ENC1_SW);
  if (s == LOW && !enc1.sw_was_pressed) {
    enc1.sw_press_time = millis();
    enc1.sw_was_pressed = true;
    recordActivity();
  }
  if (s == HIGH && enc1.sw_was_pressed) {
    recordActivity();
    unsigned long dur = millis() - enc1.sw_press_time;
    if (dur >= LONG_PRESS_MS) {
      // Long press: SWAP Active <-> Standby
      sendKnobCommand("NAV1_SWAP");
      last_data_poll = 0;
    } else {
      // Short click: Toggle MHz (Big) vs kHz (Small) step size
      enc1.mode = !enc1.mode;
      updateDisplay();
    }
    enc1.sw_was_pressed = false;
  }
}

void readEnc2() {
  int c = digitalRead(ENC2_CLK);
  if (c != enc2.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) { enc2.last_clk = c; return; }
    last_turn_time = now;
    recordActivity();
    int reps = getRepetitions(enc2);
    bool right = (c != digitalRead(ENC2_DT));
    
    // 1. INSTANT LOCAL UPDATE ON SCREEN (0 ms latency)
    for (int i = 0; i < reps; i++) {
      adjustLocalFrequency(nav2_local, right, enc2.mode);
    }
    
    // 2. Send SimConnect command over Wi-Fi in background
    const char* cmd = enc2.mode ? (right ? "NAV2_BIG_RIGHT" : "NAV2_BIG_LEFT")
                                : (right ? "NAV2_SMALL_RIGHT" : "NAV2_SMALL_LEFT");
    for (int i = 0; i < reps; i++) sendKnobCommand(cmd);
    enc2.last_clk = c;
  }
}

void readBtn2() {
  int s = digitalRead(ENC2_SW);
  if (s == LOW && !enc2.sw_was_pressed) {
    enc2.sw_press_time = millis();
    enc2.sw_was_pressed = true;
    recordActivity();
  }
  if (s == HIGH && enc2.sw_was_pressed) {
    recordActivity();
    unsigned long dur = millis() - enc2.sw_press_time;
    if (dur >= LONG_PRESS_MS) {
      // Long press: SWAP Active <-> Standby
      sendKnobCommand("NAV2_SWAP");
      last_data_poll = 0;
    } else {
      // Short click: Toggle MHz (Big) vs kHz (Small) step size
      enc2.mode = !enc2.mode;
      updateDisplay();
    }
    enc2.sw_was_pressed = false;
  }
}

void readEnc3() {
  int c = digitalRead(ENC3_CLK);
  if (c != enc3.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) { enc3.last_clk = c; return; }
    last_turn_time = now;
    recordActivity();
    int reps = getRepetitions(enc3);
    const char* cmd = (c != digitalRead(ENC3_DT)) ? "HDG_RIGHT" : "HDG_LEFT";
    for (int i = 0; i < reps; i++) sendKnobCommand(cmd);
    enc3.last_clk = c;
  }
}
void readBtn3() {
  int s = digitalRead(ENC3_SW);
  if (s == LOW && !enc3.sw_was_pressed) enc3.sw_press_time = millis(), enc3.sw_was_pressed = true, recordActivity();
  if (s == HIGH && enc3.sw_was_pressed) { enc3.mode = !enc3.mode; enc3.sw_was_pressed = false; recordActivity(); }
}

void readEnc4() {
  int c = digitalRead(ENC4_CLK);
  if (c != enc4.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) { enc4.last_clk = c; return; }
    last_turn_time = now;
    recordActivity();
    int reps = getRepetitions(enc4);
    const char* cmd = (c != digitalRead(ENC4_DT)) ? "CRS_RIGHT" : "CRS_LEFT";
    for (int i = 0; i < reps; i++) sendKnobCommand(cmd);
    enc4.last_clk = c;
  }
}
void readBtn4() {
  int s = digitalRead(ENC4_SW);
  if (s == LOW && !enc4.sw_was_pressed) enc4.sw_press_time = millis(), enc4.sw_was_pressed = true, recordActivity();
  if (s == HIGH && enc4.sw_was_pressed) { enc4.mode = !enc4.mode; enc4.sw_was_pressed = false; recordActivity(); }
}

void readEnc5() {
  int c = digitalRead(ENC5_CLK);
  if (c != enc5.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) { enc5.last_clk = c; return; }
    last_turn_time = now;
    recordActivity();
    int reps = getRepetitions(enc5);
    const char* cmd = (c != digitalRead(ENC5_DT)) ? "BARO_RIGHT" : "BARO_LEFT";
    for (int i = 0; i < reps; i++) sendKnobCommand(cmd);
    enc5.last_clk = c;
  }
}
void readBtn5() {
  int s = digitalRead(ENC5_SW);
  if (s == LOW && !enc5.sw_was_pressed) enc5.sw_press_time = millis(), enc5.sw_was_pressed = true, recordActivity();
  if (s == HIGH && enc5.sw_was_pressed) { enc5.mode = !enc5.mode; enc5.sw_was_pressed = false; recordActivity(); }
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(STATUS_LED, !digitalRead(STATUS_LED));
    delay(200);
    return;
  }
  
  readEnc1(); readBtn1();
  readEnc2(); readBtn2();
  readEnc3(); readBtn3();
  readEnc4(); readBtn4();
  readEnc5(); readBtn5();

  // Toggle buttons
  readButton(BTN_CDI, btn_cdi_last, btn_cdi_time, "CDI_TOGGLE");
  readButton(BTN_DME, btn_dme_last, btn_dme_time, "DME_TOGGLE");
  readButton(BTN_NRST, btn_nrst_last, btn_nrst_time, "NRST_TOGGLE");
  
  unsigned long now = millis();

  // --- AUTO-SLEEP CHECK ---
  if (!is_sleeping && (now - last_activity_time >= SLEEP_TIMEOUT_MS)) {
    sleepDisplay();
  }

  // --- ONLY POLL DATA AND REFRESH SCREEN IF AWAKE ---
  if (!is_sleeping) {
    if (now - last_data_poll >= DATA_POLL_MS) {
      last_data_poll = now;
      pollData();
      // Only refresh screen from background poll if we aren't actively turning dials
      if (millis() - last_local_tune_time > POLL_IGNORE_WINDOW_MS) {
        updateDisplay();
      }
    }
  }
}