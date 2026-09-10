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
  int mode;
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
String nav1_stby = "---.--";
String nav2_stby = "---.--";

// Button debounce state
bool btn_cdi_last = HIGH;
bool btn_dme_last = HIGH;
bool btn_nrst_last = HIGH;
unsigned long btn_cdi_time = 0;
unsigned long btn_dme_time = 0;
unsigned long btn_nrst_time = 0;

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

// --- Button debouncer: fires once per press (LOW transition) ---
void readButton(int pin, bool &last, unsigned long &last_time, const char* cmd) {
  int state = digitalRead(pin);
  unsigned long now = millis();
  if (state == LOW && last == HIGH && (now - last_time) > BTN_DEBOUNCE_MS) {
    last_time = now;
    last = state;
    sendKnobCommand(cmd);
    Serial.printf("[BTN] %s\n", cmd);
  }
  last = state; // always track pin state for edge detection
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
      nav1_stby = (val.equals("null") || val.length() < 1) ? "---.--" : val;
    }
    int nav2_idx = payload.indexOf(n2_key);
    if (nav2_idx >= 0) {
      int start = payload.indexOf(":", nav2_idx) + 1;
      int end = payload.indexOf(",", start);
      if (end < 0) end = payload.indexOf("}", start);
      String val = payload.substring(start, end);
      val.trim();
      nav2_stby = (val.equals("null") || val.length() < 1) ? "---.--" : val;
    }
  }
  http.end();
}

void updateDisplay() {
  display.clearDisplay();
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
  String n1 = nav1_stby;
  if (n1 == "---.--" || n1 == "null" || n1.length() < 4) n1 = "---.--";
  else { n1.trim(); if (n1.indexOf(".") >= 0 && n1.substring(n1.indexOf(".")).length() < 3) n1 += "0"; }
  String n2 = nav2_stby;
  if (n2 == "---.--" || n2 == "null" || n2.length() < 4) n2 = "---.--";
  else { n2.trim(); if (n2.indexOf(".") >= 0 && n2.substring(n2.indexOf(".")).length() < 3) n2 += "0"; }
  display.setTextSize(1);
  display.setCursor(9, 12);
  display.print(n1);
  display.setCursor(74, 12);
  display.print(n2);
  display.display();
}

// --- Encoders (1=NAV1, 2=NAV2, 3=HDG, 4=CRS, 5=BARO) ---
void readEnc1() {
  int c = digitalRead(ENC1_CLK);
  if (c != enc1.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) { enc1.last_clk = c; return; }
    last_turn_time = now;
    int reps = getRepetitions(enc1);
    bool right = (c != digitalRead(ENC1_DT));
    const char* cmd = enc1.mode ? (right ? "NAV1_BIG_RIGHT" : "NAV1_BIG_LEFT")
                                : (right ? "NAV1_SMALL_RIGHT" : "NAV1_SMALL_LEFT");
    for (int i = 0; i < reps; i++) sendKnobCommand(cmd);
    enc1.last_clk = c;
  }
}
void readBtn1() {
  int s = digitalRead(ENC1_SW);
  if (s == LOW && !enc1.sw_was_pressed) enc1.sw_press_time = millis(), enc1.sw_was_pressed = true;
  if (s == HIGH && enc1.sw_was_pressed) {
    unsigned long dur = millis() - enc1.sw_press_time;
    if (dur >= LONG_PRESS_MS) { sendKnobCommand("NAV1_SWAP"); last_data_poll = 0; }
    else { oled_mode = !oled_mode; pollData(); updateDisplay(); }
    enc1.sw_was_pressed = false;
  }
}
void readEnc2() {
  int c = digitalRead(ENC2_CLK);
  if (c != enc2.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) { enc2.last_clk = c; return; }
    last_turn_time = now;
    int reps = getRepetitions(enc2);
    bool right = (c != digitalRead(ENC2_DT));
    const char* cmd = enc2.mode ? (right ? "NAV2_BIG_RIGHT" : "NAV2_BIG_LEFT")
                                : (right ? "NAV2_SMALL_RIGHT" : "NAV2_SMALL_LEFT");
    for (int i = 0; i < reps; i++) sendKnobCommand(cmd);
    enc2.last_clk = c;
  }
}
void readBtn2() {
  int s = digitalRead(ENC2_SW);
  if (s == LOW && !enc2.sw_was_pressed) enc2.sw_press_time = millis(), enc2.sw_was_pressed = true;
  if (s == HIGH && enc2.sw_was_pressed) {
    unsigned long dur = millis() - enc2.sw_press_time;
    if (dur >= LONG_PRESS_MS) { sendKnobCommand("NAV2_SWAP"); last_data_poll = 0; }
    else { enc2.mode = !enc2.mode; }
    enc2.sw_was_pressed = false;
  }
}
void readEnc3() {
  int c = digitalRead(ENC3_CLK);
  if (c != enc3.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) { enc3.last_clk = c; return; }
    last_turn_time = now;
    int reps = getRepetitions(enc3);
    const char* cmd = (c != digitalRead(ENC3_DT)) ? "HDG_RIGHT" : "HDG_LEFT";
    for (int i = 0; i < reps; i++) sendKnobCommand(cmd);
    enc3.last_clk = c;
  }
}
void readBtn3() {
  int s = digitalRead(ENC3_SW);
  if (s == LOW && !enc3.sw_was_pressed) enc3.sw_press_time = millis(), enc3.sw_was_pressed = true;
  if (s == HIGH && enc3.sw_was_pressed) { enc3.mode = !enc3.mode; enc3.sw_was_pressed = false; }
}
void readEnc4() {
  int c = digitalRead(ENC4_CLK);
  if (c != enc4.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) { enc4.last_clk = c; return; }
    last_turn_time = now;
    int reps = getRepetitions(enc4);
    const char* cmd = (c != digitalRead(ENC4_DT)) ? "CRS_RIGHT" : "CRS_LEFT";
    for (int i = 0; i < reps; i++) sendKnobCommand(cmd);
    enc4.last_clk = c;
  }
}
void readBtn4() {
  int s = digitalRead(ENC4_SW);
  if (s == LOW && !enc4.sw_was_pressed) enc4.sw_press_time = millis(), enc4.sw_was_pressed = true;
  if (s == HIGH && enc4.sw_was_pressed) { enc4.mode = !enc4.mode; enc4.sw_was_pressed = false; }
}
void readEnc5() {
  int c = digitalRead(ENC5_CLK);
  if (c != enc5.last_clk) {
    unsigned long now = millis();
    if (now - last_turn_time < TURN_DEBOUNCE_MS) { enc5.last_clk = c; return; }
    last_turn_time = now;
    int reps = getRepetitions(enc5);
    const char* cmd = (c != digitalRead(ENC5_DT)) ? "BARO_RIGHT" : "BARO_LEFT";
    for (int i = 0; i < reps; i++) sendKnobCommand(cmd);
    enc5.last_clk = c;
  }
}
void readBtn5() {
  int s = digitalRead(ENC5_SW);
  if (s == LOW && !enc5.sw_was_pressed) enc5.sw_press_time = millis(), enc5.sw_was_pressed = true;
  if (s == HIGH && enc5.sw_was_pressed) { enc5.mode = !enc5.mode; enc5.sw_was_pressed = false; }
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
  if (now - last_data_poll >= DATA_POLL_MS) {
    last_data_poll = now;
    pollData();
    updateDisplay();
  }
}