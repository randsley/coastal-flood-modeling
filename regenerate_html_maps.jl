#!/usr/bin/env julia
# Regenerate the per-tile HTML maps for an existing tiled run.
#
# Useful after changing the map template, or to repair HTML written before the
# UTF-8 fix (Python used to open these files in the platform's default
# encoding, which mangled "km²" and "×" on Windows).
#
# The simulation is re-run per tile because the HTML embeds the flood classes
# as a PNG; the tile GeoTIFF is only used to decide which tiles exist.

include("simul_flood_tiled.jl")

println("="^70)
println("REGENERATING HTML MAPS FOR AN EXISTING TILED RUN")
println("="^70)

const VRT_FILE = "portugal_coast_wgs84.vrt"
const OUTPUT_DIR = get(ENV, "FLOOD_TILES_DIR", "tiles_output_julia")

# These must match the run that produced the GeoTIFFs.
const CAMINHA_TO_AVEIRO = (-8.90, 40.55, -8.60, 41.87)
const TILE_SIZE_DEG = 0.15
const OVERLAP_DEG = 0.005
const TIDE_ZH = 3.8
const SURGE = 0.6
const SLR = 1.13
const DOWNSAMPLE = 4

isfile(VRT_FILE) || error("VRT file not found: $VRT_FILE\nRun makeVRT.py first.")
isdir(OUTPUT_DIR) || error("Output directory not found: $OUTPUT_DIR")

tiles = create_tiles(CAMINHA_TO_AVEIRO, TILE_SIZE_DEG, overlap=OVERLAP_DEG)

levels = compute_thresholds(TIDE_ZH, SURGE, SLR)
global_seed = build_global_seed_mask(
    VRT_FILE, CAMINHA_TO_AVEIRO,
    levels.flood_threshold, levels.baseline_threshold)

println("\nRegenerating up to $(length(tiles)) HTML maps in $OUTPUT_DIR...\n")

regenerated = 0

for tile in tiles
    idx = tile.index
    tif_file = joinpath(OUTPUT_DIR, "tile_$(lpad(idx, 3, '0')).tif")
    html_file = joinpath(OUTPUT_DIR, "tile_$(lpad(idx, 3, '0')).html")

    if !isfile(tif_file)
        println("[$idx/$(length(tiles))] Skipping tile $idx (GeoTIFF not found)")
        continue
    end

    println("[$idx/$(length(tiles))] Regenerating HTML for tile $idx...")

    try
        result, gt, metadata = run_simulation_on_vrt(
            VRT_FILE, TIDE_ZH, SURGE, SLR, tile.bounds;
            downsample=DOWNSAMPLE, global_seed=global_seed, verbose=false)

        # The saved GeoTIFFs are cropped to the core, so crop here too.
        mask_core, gt_core, bounds_core = crop_to_core(
            UInt8.(Array(result)), gt, tile.core)

        meta_core = copy(metadata)
        merge!(meta_core, summarize_mask(mask_core, gt_core, bounds_core))
        meta_core["geotransform"] = gt_core

        save_html_map(classified_raster(mask_core, gt_core; crs=metadata["crs"]),
                      html_file, meta_core)

        println("  ✓ Regenerated: $html_file " *
                "($(round(meta_core["flooded_area_new_km2"], digits=3)) km² new)")
        global regenerated += 1

    catch e
        @warn "Failed to regenerate tile $idx: $e"
    end
end

println()
println("="^70)
println("HTML REGENERATION COMPLETE: $regenerated file(s)")
println("="^70)
println("The maps show newly inundated land in red and present-day water in blue,")
println("and are written as UTF-8, matching the charset they declare.")
println("Open any $OUTPUT_DIR/tile_*.html file in your browser")
println("="^70)
