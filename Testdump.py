import json, glob
from collections import defaultdict
vals = defaultdict(list)
for p in glob.glob("store/2026_R*_Q.json"):
    for fp in json.load(open(p))["fingerprints"]:
        vals[fp["team"]].append((fp["driver_code"], fp["corner_speed_delta_kph"]))

for t in sorted(vals, key=lambda t: -sum(v for _, v in vals[t])/len(vals[t])):
    v = [x for _, x in vals[t]]
    zeros = sum(1 for x in v if x == 0.0)
    print(f"{t:<14} avg={sum(v)/len(v):>7.2f}  n={len(v):>3}  zeros={zeros:>2}  "
          f"min={min(v):>7.2f} max={max(v):>6.2f}")