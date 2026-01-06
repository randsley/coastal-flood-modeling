#!/usr/bin/env julia
# Regenerate HTML maps from existing GeoTIFF files with corrected PNG encoding

include("simul_flood.jl")

println("="^70)
println("REGENERATING HTML MAPS FROM GEOTIFFS")
println("="^70)

vrt_file = "portugal_coast_wgs84.vrt"
output_dir = "tiles_output"

# Read tile bounds from the tiled script
caminha_to_aveiro = (-8.90, 40.55, -8.60, 41.87)

# Import the create_tiles function by including the tiled script
include("simul_flood_tiled.jl")

# Recreate tiles (must match original run)
tiles = create_tiles(caminha_to_aveiro, 0.15, overlap=0.005)

println("\nRegenerating $(length(tiles)) HTML maps...")
println()

for (idx, tile_bounds) in enumerate(tiles)
    tif_file = joinpath(output_dir, "tile_$(lpad(idx, 3, '0')).tif")
    html_file = joinpath(output_dir, "tile_$(lpad(idx, 3, '0')).html")

    if !isfile(tif_file)
        println("[$idx/$(length(tiles))] Skipping tile $idx (GeoTIFF not found)")
        continue
    end

    println("[$idx/$(length(tiles))] Regenerating HTML for tile $idx...")

    try
        # Re-run simulation to get the result raster and metadata
        result, transform, metadata = run_simulation_on_vrt(
            vrt_file, 3.8, 0.6, 1.13, tile_bounds
        )

        # Regenerate HTML with pixel-perfect PNG overlay
        save_html_map(result, html_file, metadata)

        println("  ✓ Regenerated: $html_file ($(round(metadata["flooded_area_km2"], digits=3)) km²)")

    catch e
        @warn "Failed to regenerate tile $idx: $e"
    end
end

println()
println("="^70)
println("HTML REGENERATION COMPLETE")
println("="^70)
println("HTML maps now show pixel-accurate flood extent overlays")
println("Open any tiles_output/tile_*.html file in your browser")
println("="^70)
