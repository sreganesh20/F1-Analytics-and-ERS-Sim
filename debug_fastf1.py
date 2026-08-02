# debug_fastf1.py
import fastf1
import os

fastf1.Cache.enable_cache("cache")

print("Fetching 2026 Australia Qualifying...")
session = fastf1.get_session(2026, "Australian Grand Prix", "Q")
session.load(telemetry=True)

lap = session.laps.pick_fastest()
print(f"Fastest lap: {lap['Driver']} — {lap['LapTime']}")

tel = lap.get_car_data().add_distance()
print(tel[["Distance", "Speed", "Throttle", "Brake"]].head(10))