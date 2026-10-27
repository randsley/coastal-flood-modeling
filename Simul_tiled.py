"""
Tiled Flood Simulation for Large Coastal Areas
Automatically splits large regions into manageable tiles

This script imports the base simulation from Simul_corrected.py and provides a
convenient interface for processing large areas.

Tiles are computed on a padded extent for hydrological connectivity and then
cropped to their non-overlapping core, so the regional total counts every pixel
exactly once. The headline figure is newly inundated land: the scenario extent
minus the water that is already there today.
"""

import glob
import os
import sys

from Simul_corrected import (
    create_index_map,
    create_tiles,
    merge_tiles_to_vrt,
    process_tiles,
    run_simulation_on_vrt,
    save_flood_geotiff,
    save_html_map,
)

# Caminha (north) to Aveiro (south), roughly 150 km of coastline
CAMINHA_TO_AVEIRO = (-8.90, 40.55, -8.60, 41.87)

# 0.15 deg ~ 16.5 km cores, with 500 m of overlap for connectivity
TILE_SIZE_DEG = 0.15
OVERLAP_DEG = 0.005

# Scenario: HAT + 50-year surge + 2100 sea-level rise
TIDE_ZH = 3.8
SURGE = 0.6
SLR = 1.13

# Decimation factor for reading. The 50 cm VRT over this whole region is
# 1.8e10 pixels, which does not fit in RAM; 4 gives a ~2 m grid.
DOWNSAMPLE = 4


if __name__ == "__main__":
    print("=" * 70)
    print("LARGE AREA FLOOD SIMULATION - NORTHERN PORTUGAL COAST")
    print("=" * 70)

    vrt_file = "portugal_coast_wgs84.vrt"

    if not os.path.isfile(vrt_file):
        print(f"Error: VRT file not found: {vrt_file}")
        print("Run makeVRT.py first.")
        sys.exit(1)

    # Step 1: Create tiles (each carries a padded extent and a core extent)
    tiles = create_tiles(CAMINHA_TO_AVEIRO, TILE_SIZE_DEG, overlap=OVERLAP_DEG)

    # Step 2: Create index map (for reference)
    create_index_map(tiles, "tile_index.html")
    print("\n→ Open tile_index.html to see the tile grid\n")

    # Step 3: Process all tiles
    results, totals = process_tiles(
        vrt_file,
        tiles,
        TIDE_ZH,
        SURGE,
        SLR,
        output_dir="tiles_output",
        save_individual_maps=True,  # Set to False for faster processing
        downsample=DOWNSAMPLE,
    )

    # Step 4: Create merged VRT. The tiles are cropped to their cores, so the
    # mosaic has no overlapping pixels and can be counted directly.
    print("\n4. Creating merged VRT...")
    tile_files = sorted(glob.glob("tiles_output/tile_*.tif"))

    if tile_files:
        merge_tiles_to_vrt(tile_files, "merged_flood_north_portugal.vrt")

    print("\n" + "=" * 70)
    print("ALL PROCESSING COMPLETE")
    print("=" * 70)
    print("\nRegional totals:")
    print(f"  Newly inundated land: {totals['new_km2']:.3f} km²")
    print(f"  Baseline water today: {totals['baseline_km2']:.3f} km²")
    print(f"  Gross below water level: {totals['gross_km2']:.3f} km²")
    print("\nOutputs:")
    print("  • Individual tiles: tiles_output/tile_*.tif "
          "(0=dry, 1=new, 2=baseline water)")
    print("  • Individual maps: tiles_output/tile_*.html")
    print("  • Tile index: tile_index.html")
    print("  • Merged VRT: merged_flood_north_portugal.vrt (open in QGIS)")
    print("\nRecommendations:")
    print("  • For presentations: Use individual HTML maps for specific areas")
    print("  • For GIS analysis: Open merged VRT in QGIS/ArcGIS")
    print("  • For statistics: use the totals above. Do not sum the padded "
          "tiles; that counts the overlap strips twice.")
    print("=" * 70)
