# PortalPanel — Hardware Wiring Guide

This guide covers the physical control box that sends knob and button commands
to the PortalPanel server (which relays them to MSFS via SimConnect).

Everything below is **verified against the firmware** in
`PortalPanel_All_Knobs_OLED_Switches_And_Timeout_Phase6/` — the most complete
sketch. Earlier phases (0–5) are subsets of this same pin map.

## Overview

The box consists of:
- 1 × **ESP32-S3** dev board (N16R8 = 16 MB flash / 8 MB PSRAM, dual USB-C)
- 5 × **KY-040 rotary encoders** (each with an integrated push button)
- 1 × **SSD1306 OLED** display, 128×32 px, I2C (address `0x3C`)
- 3 × **momentary push buttons** (active-LOW, wired to GND)

## Bill of Materials

| Component | Qty | Notes |
|-----------|-----|-------|
| ESP32-S3 Dev Board (N16R8) | 1 | 16 MB flash / 8 MB PSRAM, dual USB-C |
| KY-040 Rotary Encoder | 5 | With integrated push button (SW pin) |
| SSD1306 OLED 128×32 (I2C) | 1 | I2C address `0x3C` |
| Momentary Push Button | 3 | Active-LOW (one leg to GND) |

## Pin Assignments

### Rotary Encoders

| Encoder | Function        | CLK | DT  | SW  |
|---------|-----------------|-----|-----|-----|
| ENC1    | NAV1 Frequency  | 4   | 5   | 6   |
| ENC2    | NAV2 Frequency  | 7   | 10  | 11  |
| ENC3    | Heading Bug (HDG) | 12 | 13  | 14  |
| ENC4    | Course (CRS/OBS)  | 15 | 16  | 17  |
| ENC5    | Barometer (BARO)  | 38 | 39  | 40  |

**Every KY-040 encoder needs power, in addition to its three signal pins:**

| KY-040 pin | Connect to |
|------------|-----------|
| `+`        | ESP32 **3.3V** |
| `GND`      | ESP32 **GND**  |
| `CLK`      | CLK GPIO (table above) |
| `DT`       | DT GPIO (table above)  |
| `SW`       | SW GPIO (table above)  |

All five encoders share the same **3.3V rail** and **GND rail**. Tip: use a
small breadboard or solderless strip to make one common 3.3V rail and one common
GND rail, then connect all encoders' `+`/`GND` pins to those rails.

### OLED Display (SSD1306, I2C)

| OLED pin | Connect to |
|----------|-----------|
| SDA      | GPIO 8    |
| SCL      | GPIO 9    |
| VCC      | 3.3V      |
| GND      | GND       |

> I2C pins are set in firmware via `Wire.begin(8, 9)`. If you use a different
> board layout, change both the wiring *and* that line to match.

### Toggle Buttons (active-LOW)

| Button   | Function            | GPIO |
|----------|---------------------|------|
| BTN_CDI  | CDI toggle (GPS/VOR)| 1    |
| BTN_DME  | DME toggle          | 2    |
| BTN_NRST | NRST toggle         | 42   |

Each button: **one leg to the GPIO, the other leg to GND.** The firmware uses
`INPUT_PULLUP`, so no external pull resistor is needed.

## Encoder Button Behaviors (from firmware)

| Encoder | Short press (<800 ms)        | Long press (>800 ms)   |
|---------|------------------------------|------------------------|
| NAV1    | Toggle MHz / kHz step size   | SWAP active/standby    |
| NAV2    | Toggle MHz / kHz step size   | SWAP active/standby    |
| HDG     | Toggle step mode             | (reserved)             |
| CRS     | Toggle step mode             | (reserved)             |
| BARO    | Toggle step mode             | (reserved)             |

## Power

Power the ESP32-S3 via **USB-C** with a **5V** supply. The onboard regulator
provides 3.3V to all peripherals. Do not apply higher voltage to the USB port.

## Wiring Diagram

```
                        ESP32-S3 (N16R8)
   ┌──────────────────────────────────────────────────────────┐
   │                                                          │
   │  3V3 ──┬────────────────────────────── (shared 3.3V rail)│
   │        │                                                  │
   │  GND ──┴────────────────────────────── (shared GND rail) │
   │                                                          │
   │  GPIO 4  ── CLK ─┐                                      │
   │  GPIO 5  ── DT  ─┤  KY-040 #1 (NAV1)                    │
   │  GPIO 6  ── SW  ─┘        + → 3V3 rail                  │
   │                          GND → GND rail                 │
   │                                                          │
   │  GPIO 7  ── CLK ─┐                                      │
   │  GPIO 10 ── DT  ─┤  KY-040 #2 (NAV2)                    │
   │  GPIO 11 ── SW  ─┘        + → 3V3 rail                  │
   │                          GND → GND rail                 │
   │                                                          │
   │  GPIO 12 ── CLK ─┐                                      │
   │  GPIO 13 ── DT  ─┤  KY-040 #3 (HDG)                     │
   │  GPIO 14 ── SW  ─┘        + → 3V3 rail                  │
   │                          GND → GND rail                 │
   │                                                          │
   │  GPIO 15 ── CLK ─┐                                      │
   │  GPIO 16 ── DT  ─┤  KY-040 #4 (CRS)                     │
   │  GPIO 17 ── SW  ─┘        + → 3V3 rail                  │
   │                          GND → GND rail                 │
   │                                                          │
   │  GPIO 38 ── CLK ─┐                                      │
   │  GPIO 39 ── DT  ─┤  KY-040 #5 (BARO)                    │
   │  GPIO 40 ── SW  ─┘        + → 3V3 rail                  │
   │                          GND → GND rail                 │
   │                                                          │
   │  GPIO 1  ──────────────── BTN CDI  (other leg → GND)    │
   │  GPIO 2  ──────────────── BTN DME  (other leg → GND)    │
   │  GPIO 42 ──────────────── BTN NRST (other leg → GND)    │
   │                                                          │
   │  GPIO 8  ── SDA ─┐                                      │
   │  GPIO 9  ── SCL ─┤  SSD1306 OLED 128×32                 │
   │  3V3    ── VCC ─┘        VCC → 3.3V rail                │
   │                          GND → GND rail                 │
   └──────────────────────────────────────────────────────────┘

  Note: All KY-040 `+` pins → 3.3V rail, all `GND` pins → common GND rail.
```

## Notes for Replicating This Build

1. **I2C pins (8/9):** Firmware sets I2C to GPIO 8 (SDA) / GPIO 9 (SCL) via
   `Wire.begin(8, 9)`. Adjust if using a different board layout.
2. **STATUS_LED (GPIO 48):** Defined in firmware but unused on this build — it
   was for an optional status LED. Safe to ignore or leave unconnected.
3. **Buttons are active-LOW:** Firmware uses `INPUT_PULLUP`, so buttons connect
   to GND (no external resistor needed).
4. **Network config:** Edit the `WIFI_SSID` / `WIFI_PASSWORD` / `SERVER_URL` /
   `DATA_URL` placeholders at the top of the sketch before uploading. See the
   firmware README for details.
