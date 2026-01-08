"""
Tiled Flood Simulation for Large Coastal Areas
Automatically splits large regions into manageable tiles

This script imports the base simulation from Simul_corrected.py
and provides a convenient interface for processing large areas.
"""

from Simul_corrected import (
    run_simulation_on_vrt,
    save_flood_geotiff,
    save_html_map,
    create_tiles,
    process_tiles,
    merge_tiles_to_vrt,
    create_index_map
)
import sys
import os
import glob


if __name__ == "__main__":
    print("="*70)
    print("LARGE AREA FLOOD SIMULATION - NORTHERN PORTUGAL COAST")
    print("="*70)

    # Define large region: Caminha (north) to Aveiro (south)
    # This covers approximately 150km of coastline
    caminha_to_aveiro = (-8.90, 40.55, -8.60, 41.87)

    vrt_file = "portugal_coast_wgs84.vrt"

    if not os.path.isfile(vrt_file):
        print(f"Error: VRT file not found: {vrt_file}")
        print("Run makeVRT.py first.")
        sys.exit(1)

    # Step 1: Create tiles
    # 0.15° ≈ 16.5 km tiles with 500m overlap
    tiles = create_tiles(caminha_to_aveiro, 0.15, overlap=0.005)

    # Step 2: Create index map (for reference)
    create_index_map(tiles, "tile_index.html")
    print("\n→ Open tile_index.html to see the tile grid\n")

    # Step 3: Process all tiles
    results = process_tiles(
        vrt_file,
        tiles,
        3.8,   # HAT
        0.6,   # 50-year surge
        1.13,  # 2100 SLR
        output_dir="tiles_output",
        save_individual_maps=True  # Set to False for faster processing
    )

    # Step 4: Create merged VRT (requires GDAL)
    # This allows viewing all tiles as one continuous dataset in QGIS
    print("\n4. Creating merged VRT...")
    tile_files = glob.glob("tiles_output/tile_*.tif")

    if tile_files:
        try:
            merge_tiles_to_vrt(tile_files, "merged_flood_north_portugal.vrt")
        except Exception as e:
            print(f"  (Optional) Could not create merged VRT: {e}")

    print("\n" + "="*70)
    print("ALL PROCESSING COMPLETE")
    print("="*70)
    print("\nOutputs:")
    print("  • Individual tiles: tiles_output/tile_*.tif")
    print("  • Individual maps: tiles_output/tile_*.html")
    print("  • Tile index: tile_index.html")
    print("  • Merged VRT: merged_flood_north_portugal.vrt (open in QGIS)")
    print("\nRecommendations:")
    print("  • For presentations: Use individual HTML maps for specific areas")
    print("  • For GIS analysis: Open merged VRT in QGIS/ArcGIS")
    print("  • For statistics: Sum the flooded areas from individual tiles")
    print("="*70)
