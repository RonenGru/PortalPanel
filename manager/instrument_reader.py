#!/usr/bin/env python3
"""
PortalPanel - Full Instrument Data Reader
Reads all G1000-relevant variables from MSFS via SimConnect
"""
import sys
import time
import json

from SimConnect import SimConnect, AircraftRequests

print("=" * 60)
print("PortalPanel - Full Instrument Data Reader")
print("=" * 60)
print("")

# =====================================================
# Define all the variables we want to read
# G1000-relevant data for a C172
# =====================================================

PFD_VARIABLES = {
    # --- Attitude / Position ---
    "ALTITUDE":              "PLANE_ALTITUDE",
    "AIRSPEED":              "AIRSPEED_INDICATED",
    "VERTICAL_SPEED":        "VERTICAL_SPEED",
    "HEADING_TRUE":          "PLANE_HEADING_DEGREES_TRUE",
    "HEADING_MAG":           "PLANE_HEADING_DEGREES_MAGNETIC",
    "PITCH":                 "PLANE_PITCH_DEGREES",
    "ROLL":                  "PLANE_BANK_DEGREES",
    "LATITUDE":              "PLANE_LATITUDE",
    "LONGITUDE":             "PLANE_LONGITUDE",
    "ON_GROUND":             "SIMON_GROUND",

    # --- Altimeter / Baro ---
    "BARO_PRESSURE":         "KOHLSMAN_SETTING_MB",
    "ALTITUDE_STD":          "INDICATED_ALTITUDE",

    # --- Turn / Slip ---
    "TURN_RATE":             "TURN_INDICATOR_RATE",
    "YAW_RATE":              "YAW_RATE",
    "BALL":                  "TURN_COORDINATOR_BALL",

    # --- NAV1 ---
    "NAV1_FREQ":             "NAV_ACTIVE_FREQUENCY:1",
    "NAV1_STBY_FREQ":        "NAV_STBY_FREQUENCY:1",
    "NAV1_RADIAL":           "NAV_RADIAL:1",
    "NAV1_SIGNAL":           "NAV_HAS_NAV:1",
    "NAV1_GLIDESLOPE":       "NAV_GLIDE_SLOPE:1",
    "NAV1_DIST":             "NAV_DME:1",

    # --- NAV2 ---
    "NAV2_FREQ":             "NAV_ACTIVE_FREQUENCY:2",
    "NAV2_STBY_FREQ":        "NAV_STBY_FREQUENCY:2",
    "NAV2_RADIAL":           "NAV_RADIAL:2",
    "NAV2_SIGNAL":           "NAV_HAS_NAV:2",
    "NAV2_DIST":             "NAV_DME:2",

    # --- GPS ---
    "GPS_COURSE":            "GPS_TARGET_DISTANCE",
    "GPS_DIST":              "GPS_DISTANCE_TO_GO",
    "GPS_GROUND_SPEED":      "GPS_GROUND_SPEED",
    "GPS_MAGVAR":            "GPS_MAGVAR",
}

MFD_VARIABLES = {
    # --- Engine ---
    "ENG_RPM":               "ENG_RPM:1",
    "ENG_MANIFOLD_PRESSURE": "ENG_MANIFOLD_PRESSURE:1",
    "ENG_OIL_TEMP":          "ENG_OIL_TEMPERATURE:1",
    "ENG_OIL_PRESSURE":      "ENG_OIL_PRESSURE:1",
    "ENG_EGT":               "ENG_EXHAUST_GAS_TEMPERATURE:1",
    "ENG_CHT":               "ENG_CYLINDER_HEAD_TEMPERATURE:1",
    "ENG_FUEL_FLOW":         "ENG_FUEL_FLOW_GPH:1",

    # --- Fuel ---
    "FUEL_TOTAL":            "FUEL_TOTAL_QUANTITY",
    "FUEL_LEFT":             "FUEL_LEFT_QUANTITY",
    "FUEL_RIGHT":            "FUEL_RIGHT_QUANTITY",
    "FUEL_PRESSURE":         "FUEL_PRESSURE:1",

    # --- Electrical ---
    "ELECT_BUS_VOLTAGE":     "ELECTRICAL_MAIN_BUS_VOLTAGE",
    "ELECT_BUS_LOAD":        "ELECTRICAL_MAIN_BUS_AMPS",
    "ELECT_GENALT":          "ELECTRICAL_GENALT_BUS_VOLTAGE:1",
    "ELECT_BATTERY":         "ELECTRICAL_BATTERY_LOAD:1",

    # --- Vacuum / Pitot ---
    "VACUUM":                "SUCTION_PRESSURE",
    "PITOT_HEAT":            "PITOT_HEAT:1",
}

# Combine all variables
ALL_VARIABLES = {}
ALL_VARIABLES.update(PFD_VARIABLES)
ALL_VARIABLES.update(MFD_VARIABLES)


def read_all_instruments(ar, variables_dict):
    """Read all instrument variables and return as a dictionary"""
    data = {}
    for key, simvar in variables_dict.items():
        try:
            value = ar.get(simvar)
            data[key] = value
        except Exception:
            data[key] = None
    return data


def print_instruments(data, label=""):
    """Pretty print the instrument data"""
    if label:
        print("\n--- {} ---".format(label))
        print("-" * 40)

    for key, value in data.items():
        if value is None:
            print("  {:<25} : N/A".format(key))
        elif isinstance(value, float):
            print("  {:<25} : {:.2f}".format(key, value))
        else:
            print("  {:<25} : {}".format(key, value))


def main():
    try:
        print("Connecting to MSFS via SimConnect...")
        sm = SimConnect()
        ar = AircraftRequests(sm, _time=1000)

        print("[OK] Connected! Reading instrument data...\n")
        time.sleep(2)

        # Read all variables
        all_data = read_all_instruments(ar, ALL_VARIABLES)

        # Print results
        pfd_data = read_all_instruments(ar, PFD_VARIABLES)
        mfd_data = read_all_instruments(ar, MFD_VARIABLES)

        print_instruments(pfd_data, "PFD DATA (Primary Flight Display)")
        print_instruments(mfd_data, "MFD DATA (Multi-Function Display)")

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        successful = sum(1 for v in all_data.values() if v is not None)
        failed = sum(1 for v in all_data.values() if v is None)

        print("  Variables attempted: {}".format(len(all_data)))
        print("  Successfully read:   {}".format(successful))
        print("  Failed (N/A):        {}".format(failed))

        if failed > 0:
            print("\n  Variables that returned None (may need different names):")
            for key, value in all_data.items():
                if value is None:
                    print("    - {} (tried as: {})".format(key, ALL_VARIABLES[key]))

        print("\n[SUCCESS] Instrument reader complete!")

        sm.exit()
        sys.exit(0)

    except Exception as e:
        print("\n[ERROR] {}".format(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()