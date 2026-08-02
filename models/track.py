"""
models/track.py

Takes raw telemetry and segments the lap into classified zones.
Each segment knows:
  - What type it is (straight, braking, corner, superclip)
  - The energy opportunity it represents (harvest or deploy)
  - Key physics values (entry speed, exit speed, length)
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Literal


SegmentType = Literal["straight", "braking", "corner", "superclip", "lift_coast"]


@dataclass
class TrackSegment:
    index:        int
    seg_type:     SegmentType
    d_start:      float          # metres from lap start
    d_end:        float
    length:       float          # metres
    speed_entry:  float          # kph
    speed_min:    float          # kph (apex / min in zone)
    speed_exit:   float          # kph
    speed_mean:   float          # kph
    throttle_mean: float         # 0–100%
    brake_mean:   float          # 0–1
    time_s:       float          # seconds spent in segment

    # Energy opportunity (filled by physics model)
    kinetic_energy_delta_mj: float = 0.0   # +ve = energy released (harvestable)
    harvest_opportunity_mj:  float = 0.0   # how much could be recovered
    deploy_opportunity_mj:   float = 0.0   # how much could be gainfully deployed

    def __repr__(self):
        return (f"Seg[{self.index:03d}] {self.seg_type:<12} "
                f"d={self.d_start:.0f}-{self.d_end:.0f}m  "
                f"v={self.speed_entry:.0f}→{self.speed_min:.0f}→{self.speed_exit:.0f} kph  "
                f"t={self.time_s:.2f}s")


def segment_lap(df: pd.DataFrame,
                min_segment_length: float = 30.0,
                smooth_window: int = 5) -> list[TrackSegment]:
    """
    Classify lap telemetry into a list of TrackSegments.

    Strategy:
      1. Smooth speed/throttle/brake to reduce sensor noise
      2. Detect zone transitions using threshold rules
      3. Merge tiny fragments into their neighbours
      4. Classify each zone by its dominant behaviour
    """

    df = df.copy().reset_index(drop=True)

    # ── 1. Smooth signals ───────────────────────────────
    df["Speed_s"]    = df["Speed"].rolling(smooth_window, center=True, min_periods=1).mean()
    df["Throttle_s"] = df["Throttle"].rolling(smooth_window, center=True, min_periods=1).mean()
    df["Brake_s"]    = df["Brake"].rolling(smooth_window, center=True, min_periods=1).mean()

    # ── 2. Point-level classification ──────────────────
    # Raw label per telemetry point
    labels = []
    for _, row in df.iterrows():
        thr = row["Throttle_s"]
        brk = row["Brake_s"]
        spd = row["Speed_s"]

        if brk > 0.3:
            labels.append("braking")
        elif thr >= 98:
            # High speed + full throttle → straight (possible superclip zone)
            labels.append("straight")
        elif thr < 20:
            labels.append("lift_coast")
        else:
            labels.append("corner")

    df["label"] = labels

    # ── 3. Build contiguous zones ──────────────────────
    zones = []
    current_label = labels[0]
    zone_start_idx = 0

    for i, lbl in enumerate(labels[1:], 1):
        if lbl != current_label:
            zones.append((zone_start_idx, i - 1, current_label))
            current_label = lbl
            zone_start_idx = i
    zones.append((zone_start_idx, len(labels) - 1, current_label))

    # ── 4. Merge tiny zones into neighbours ────────────
    merged = []
    for zone in zones:
        start_idx, end_idx, lbl = zone
        d_start = df.loc[start_idx, "Distance"]
        d_end   = df.loc[end_idx,   "Distance"]
        length  = d_end - d_start

        if length < min_segment_length and merged:
            # Absorb into previous
            prev = merged[-1]
            merged[-1] = (prev[0], end_idx, prev[2])
        else:
            merged.append(zone)

    # ── 5. Build TrackSegment objects ──────────────────
    segments = []
    for seg_idx, (start_idx, end_idx, lbl) in enumerate(merged):
        chunk = df.loc[start_idx:end_idx]

        speed_vals = chunk["Speed_s"].values
        thr_vals   = chunk["Throttle_s"].values
        brk_vals   = chunk["Brake_s"].values
        dt_vals    = chunk["DeltaTime"].values

        d_start    = float(chunk["Distance"].iloc[0])
        d_end      = float(chunk["Distance"].iloc[-1])
        length     = d_end - d_start

        time_s     = float(np.sum(dt_vals))

        # Identify superclip zones:
        # Full throttle + speed above 260kph + at end of straight
        seg_type = lbl
        if lbl == "straight" and np.mean(speed_vals) > 260 and np.mean(thr_vals) > 97:
            seg_type = "superclip"

        seg = TrackSegment(
            index         = seg_idx,
            seg_type      = seg_type,
            d_start       = d_start,
            d_end         = d_end,
            length        = length,
            speed_entry   = float(speed_vals[0]),
            speed_min     = float(np.min(speed_vals)),
            speed_exit    = float(speed_vals[-1]),
            speed_mean    = float(np.mean(speed_vals)),
            throttle_mean = float(np.mean(thr_vals)),
            brake_mean    = float(np.mean(brk_vals)),
            time_s        = time_s,
        )
        segments.append(seg)

    return segments


def print_track_summary(segments: list[TrackSegment], circuit_name: str):
    """Print a readable summary of the segmented track."""
    counts = {}
    for s in segments:
        counts[s.seg_type] = counts.get(s.seg_type, 0) + 1

    total_dist = segments[-1].d_end if segments else 0
    braking_segs = [s for s in segments if s.seg_type == "braking"]
    total_braking = sum(s.length for s in braking_segs)

    print(f"\n{'═'*55}")
    print(f"  Track Model: {circuit_name}")
    print(f"{'═'*55}")
    print(f"  Total segments:  {len(segments)}")
    print(f"  Lap distance:    {total_dist:.0f} m")
    print(f"  Braking zones:   {counts.get('braking', 0)}  ({total_braking:.0f}m total)")
    print(f"  Straights:       {counts.get('straight', 0)}")
    print(f"  Superclip zones: {counts.get('superclip', 0)}")
    print(f"  Corners:         {counts.get('corner', 0)}")
    print(f"  Lift/Coast:      {counts.get('lift_coast', 0)}")
    print(f"\n  Key braking zones:")
    for s in braking_segs:
        print(f"    {s}")
    print(f"{'═'*55}\n")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from fetcher import generate_synthetic_telemetry

    for circuit in ["Australia", "China", "Japan"]:
        df  = generate_synthetic_telemetry(circuit)
        seg = segment_lap(df)
        print_track_summary(seg, circuit)
