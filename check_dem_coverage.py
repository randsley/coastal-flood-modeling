"""
Diagnose the rectangular blocks along the coast in the flood output.

The flooded extent has straight, stair-stepped edges offshore and the odd
rectangular hole. This script decides whether those come from NoData handling
or from where the DGT DEM coverage simply stops, by reporting:

1. the DGT tile footprint of the mosaic, as an ASCII coverage map;
2. the NoData fraction of the region;
3. what the gross flood extent borders on - NoData, or land above the water
   level. A perimeter that mostly abuts NoData means the edges are the limit of
   DEM coverage, not a flooding artefact.

Usage:
    python check_dem_coverage.py [vrt] [mosaic_vrt]
"""

import os
import re
import sys

import numpy as np

from Simul_corrected import (
    compute_thresholds,
    connected_flood,
    read_dem_window,
)

DEFAULT_VRT = "portugal_coast_wgs84.vrt"
DEFAULT_MOSAIC = "portugal_coast_mosaic.vrt"

# The region and scenario the figures are quoted for.
REGION = (-8.90, 40.55, -8.60, 41.87)
TIDE_ZH, SURGE, SLR = 3.8, 0.6, 1.13

# Coarse enough to sweep 150 km of coastline in seconds.
DOWNSAMPLE = 16


def report_tile_footprint(mosaic_vrt):
    """Print the DGT tile grid of the source mosaic."""
    if not os.path.isfile(mosaic_vrt):
        print(f"(skipping tile footprint: {mosaic_vrt} not found)")
        return

    with open(mosaic_vrt, encoding='utf-8', errors='replace') as f:
        xml = f.read()

    sources = re.findall(r'<SourceFilename[^>]*>([^<]+)</SourceFilename>', xml)
    keys = set()
    for src in sources:
        m = re.search(r'MDT-\d+(?:cm|m)-(\d{3})(\d{3})', src)
        if m:
            keys.add((int(m.group(1)), int(m.group(2))))

    if not keys:
        print(f"(no DGT tile names recognised in {mosaic_vrt})")
        return

    cols = sorted({k[0] for k in keys})
    rows = sorted({k[1] for k in keys})

    print(f"Source tiles in mosaic: {len(sources)}")
    print(f"DGT grid columns {cols[0]}-{cols[-1]} ({len(cols)}), "
          f"rows {rows[0]}-{rows[-1]} ({len(rows)})")
    print(f"Tiles present: {len(keys)} of a full "
          f"{len(cols) * len(rows)}-tile rectangle "
          f"({100 * len(keys) / (len(cols) * len(rows)):.1f}%)")
    print("")
    print("Coverage ('#' = tile present), north at the top, 1 km per cell:")
    for row in sorted(rows, reverse=True):
        line = ''.join('#' if (c, row) in keys else '.' for c in cols)
        print(f"  {row} {line}")

    # Interior holes: a missing tile with neighbours on both sides in its row.
    holes = []
    for row in rows:
        present = sorted(c for c in cols if (c, row) in keys)
        if len(present) < 2:
            continue
        for c in range(present[0], present[-1] + 1):
            if (c, row) not in keys:
                holes.append((c, row))
    print("")
    print(f"Missing tiles enclosed by coverage in their own row: {len(holes)}")
    if holes:
        print("  " + ", ".join(f"{c}{r}" for c, r in holes[:20]))


def report_flood_perimeter(vrt_path):
    """Report what the gross flood extent borders on."""
    levels = compute_thresholds(TIDE_ZH, SURGE, SLR)

    print(f"Reading {vrt_path} over {REGION} at downsample={DOWNSAMPLE}...")
    dem, nodata_mask, transform, bounds_read, _ = read_dem_window(
        vrt_path, REGION, downsample=DOWNSAMPLE
    )
    print(f"  Grid: {dem.shape[1]} x {dem.shape[0]} px")
    print(f"  NoData: {nodata_mask.mean() * 100:.1f}% of the window")

    flooded = connected_flood(dem, levels["flood_threshold"], nodata_mask)
    print(f"  Gross flooded (below {levels['flood_threshold']:.2f} m NMM "
          "and connected): "
          f"{flooded.mean() * 100:.1f}% of the window")

    # Classify the outer edge of the flooded region by what lies beyond it.
    def shift(mask, dr, dc):
        out = np.zeros_like(mask)
        rows = slice(max(0, dr), mask.shape[0] + min(0, dr))
        cols = slice(max(0, dc), mask.shape[1] + min(0, dc))
        src_rows = slice(max(0, -dr), mask.shape[0] + min(0, -dr))
        src_cols = slice(max(0, -dc), mask.shape[1] + min(0, -dc))
        out[rows, cols] = mask[src_rows, src_cols]
        return out

    neighbours = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    touches_nodata = np.zeros_like(flooded)
    touches_dry = np.zeros_like(flooded)
    for dr, dc in neighbours:
        shifted_nodata = shift(nodata_mask, dr, dc)
        shifted_flood = shift(flooded, dr, dc)
        touches_nodata |= flooded & shifted_nodata
        touches_dry |= flooded & ~shifted_flood & ~shifted_nodata

    perimeter = touches_nodata | touches_dry
    n_perimeter = int(perimeter.sum())
    n_nodata_edge = int((touches_nodata & ~touches_dry).sum())
    n_dry_edge = int((touches_dry & ~touches_nodata).sum())
    n_both = int((touches_nodata & touches_dry).sum())

    print("")
    print("Gross flood perimeter, by what lies immediately beyond it:")
    if n_perimeter:
        print(f"  abuts NoData only           : {n_nodata_edge:>10,} "
              f"({100 * n_nodata_edge / n_perimeter:5.1f}%)")
        print(f"  abuts dry land only         : {n_dry_edge:>10,} "
              f"({100 * n_dry_edge / n_perimeter:5.1f}%)")
        print(f"  abuts both                  : {n_both:>10,} "
              f"({100 * n_both / n_perimeter:5.1f}%)")
        print(f"  total perimeter pixels      : {n_perimeter:>10,}")
    else:
        print("  (nothing flooded)")

    print("")
    print("Elevation of the NoData neighbours' flooded pixels is irrelevant: "
          "NoData is\nreplaced by a high value and never floods, so a flood "
          "edge that abuts NoData is\nthe edge of DEM coverage, not a "
          "thresholding artefact.")

    return flooded, nodata_mask


if __name__ == "__main__":
    vrt_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VRT
    mosaic_vrt = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MOSAIC

    print("=" * 70)
    print("DEM COVERAGE DIAGNOSTIC")
    print("=" * 70)
    report_tile_footprint(mosaic_vrt)

    if not os.path.isfile(vrt_path):
        print(f"\nError: {vrt_path} not found. Run makeVRT.py first.")
        sys.exit(1)

    print("")
    print("=" * 70)
    report_flood_perimeter(vrt_path)
    print("=" * 70)
