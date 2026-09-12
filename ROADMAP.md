# PortalPanel Development Roadmap

## Overview
This document tracks the development goals and progress for PortalPanel, a live instrument panel display for MSFS 2024/2020.

---

## PFD (Primary Flight Display)

### Completed
- [x] Attitude Indicator (pitch/roll artificial horizon)
- [x] Airspeed Tape
- [x] Altitude Tape
- [x] Heading Tape (magnetic compass)
- [x] VSI (Vertical Speed Indicator)
- [x] NAV Frequencies (NAV1/NAV2)
- [x] Baro Setting

### Phase 1 — Polish & Core Features
- [X] G1000 bezel styling (realistic Garmin look)
- [X] Borderless fullscreen mode
- [x] Monitor selection button
- [x] Airspeed trend arrow
- [x] Altitude trend arrow
- [x] Heading bug
- [x] CDI (Course Deviation Indicator)
- [x] OAT (Outside Air Temp)
- [x] Wind display
- [x] Autopilot status

### Phase 2 — PFD Extended
- [x] GPS status
- [ ] Speed bug / V-Speeds
- [ ] Alerts/Messages system
- [ ] Softkeys (menu buttons)
- [x] Location/range to waypoint (GPS wp id + distance)

---

## MFD (Multi-Function Display)

### Completed
- [x] Engine RPM
- [x] Engine Temperatures (oil temp, EGT, CHT)
- [x] Oil Pressure
- [x] Fuel Flow
- [x] Fuel Quantity (left, right, total)
- [x] Electrical (bus voltage, load)
- [x] Vacuum
- [x] Position (lat/long, ground speed)

### Phase 1.5 — Moving Map
- [x] Basic moving map (aircraft position, heading)
- [x] Map with terrain features (MapLibre tile mode)
- [x] Waypoints display
- [x] Nearest airports (NRST)
- [x] Navigation log (flight plan waypoints, .pln parser)

### Phase 2 — MFD Extended
- [ ] Terrain page
- [ ] Engine lean assist
- [ ] Fuel calculator (endurance, range)
- [ ] Traffic display
- [ ] Weather overlay

---

## Interaction (Phase 3)

- [x] NAV frequency tuning knobs (NAV1/NAV2, big + small)
- [x] Course knob
- [x] Heading bug knob
- [x] Baro knob
- [x] Map zoom (software-based; hardware encoder TBD)
- [ ] Softkeys (mode switches)
- [ ] Direct-To button
- [x] Flight plan button (.pln route overlay)

---

## Analog Instrument Pack (Phase 4)

- [ ] Round airspeed indicator
- [ ] Round attitude indicator
- [ ] Round altimeter
- [ ] Round heading indicator
- [ ] Round VSI
- [ ] Round turn coordinator

---

## Aircraft Profile System (Phase 5)

- [ ] Landing/startup page (aircraft selection)
- [x] Pre-built profiles (C172 G1000 shipped; more planned)
- [x] Auto-detect which aircraft is loaded in MSFS

---

## VR Passthrough Integration (Phase 6)

- [ ] Test and optimize for VR + passthrough setup
- [ ] Ensure displays float nicely in real-world cockpit view
- [ ] Optimize performance for VR session

---

## Packaging & Release (Phase 7)

- [x] GPL-3.0 license
- [x] PyInstaller build (two-exe: launcher + server)
- [x] GitHub repository (RonenGru/PortalPanel)
- [x] v1.1 release (portable zip + installer)
- [x] Inno Setup installer (.exe)
- [ ] CI/CD automated builds (optional, future)
