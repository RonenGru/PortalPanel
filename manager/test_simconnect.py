#!/usr/bin/env python3
"""PortalPanel - SimConnect Connection Test v3"""
import sys
import time

print("=" * 50)
print("PortalPanel - SimConnect Connection Test v3")
print("=" * 50)
print("")

try:
    from SimConnect import SimConnect, AircraftRequests, AircraftEvents

    sm = SimConnect()
    print("[OK] Connected to MSFS via SimConnect!")

    # AircraftRequests is the key class for reading data
    ar = AircraftRequests(sm, _time=2000)
    print("[OK] AircraftRequests created!")

    # Give it a moment to start collecting data
    print("Waiting 2 seconds for data to populate...")
    time.sleep(2)

    # Try reading some basic flight data using the .get() method
    print("")
    print("Reading flight data...")
    print("")

    altitude = ar.get("PLANE_ALTITUDE")
    airspeed = ar.get("AIRSPEED_INDICATED")
    heading = ar.get("PLANE_HEADING_DEGREES_TRUE")
    latitude = ar.get("PLANE_LATITUDE")
    longitude = ar.get("PLANE_LONGITUDE")

    print("Flight Data Retrieved:")
    print("  Altitude:   {} ft".format(altitude))
    print("  Airspeed:   {} knots".format(airspeed))
    print("  Heading:    {} degrees".format(heading))
    print("  Latitude:   {}".format(latitude))
    print("  Longitude:  {}".format(longitude))

    # Try a few more instrument-relevant variables
    print("")
    print("Additional Instrument Data:")

    vspeed = ar.get("VERTICAL_SPEED")
    fuel_total = ar.get("FUEL_TOTAL_QUANTITY")
    rpm = ar.get("ENG RPM:1")
    on_ground = ar.get("SIM ON GROUND")

    print("  Vertical Speed: {} ft/min".format(vspeed))
    print("  Fuel Total:     {} gallons".format(fuel_total))
    print("  Engine RPM:     {}".format(rpm))
    print("  On Ground:     {}".format(on_ground))

    print("")
    print("[SUCCESS] SimConnect is fully operational! Ready for PortalPanel!")

    sm.exit()
    sys.exit(0)

except ImportError as e:
    print("[FAIL] Could not import SimConnect: {}".format(e))
    sys.exit(1)

except Exception as e:
    print("[ERROR] {}".format(e))
    print("  Type: {}".format(type(e).__name__))
    import traceback
    traceback.print_exc()
    sys.exit(1)