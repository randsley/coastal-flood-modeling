# Tiled Flood Simulation for Large Coastal Areas
# Automatically splits large regions into manageable tiles

include("simul_flood.jl")

using Dates

"""
    create_tiles(bounds, tile_size_deg; overlap=0.001)

Divide a large bounding box into smaller tiles for processing.

# Arguments
- `bounds::Tuple`: Overall bounds (min_lon, min_lat, max_lon, max_lat)
- `tile_size_deg::Float64`: Approximate tile size in degrees (e.g., 0.1 = ~11km)
- `overlap::Float64`: Overlap between tiles in degrees (default: 0.001 = ~100m)

# Returns
- Vector of tile bounds, each as (min_lon, min_lat, max_lon, max_lat)

# Example
```julia
# Northern Portugal coast: Caminha to Aveiro
large_bounds = (-8.90, 40.55, -8.60, 41.87)
tiles = create_tiles(large_bounds, 0.15, overlap=0.005)
```

# Notes
Overlap is important for hydrological connectivity at tile boundaries.
Recommended overlap: 500m (0.005°) for coastal zones.
"""
function create_tiles(bounds::Tuple, tile_size_deg::Float64; overlap::Float64=0.001)
    min_lon, min_lat, max_lon, max_lat = bounds

    # Calculate number of tiles needed
    n_tiles_x = ceil(Int, (max_lon - min_lon) / tile_size_deg)
    n_tiles_y = ceil(Int, (max_lat - min_lat) / tile_size_deg)

    println("Creating tiling scheme:")
    println("  Total area: $(round(max_lon - min_lon, digits=3))° × $(round(max_lat - min_lat, digits=3))°")
    println("  Tile size: $(tile_size_deg)° (~$(round(tile_size_deg * 111, digits=1)) km)")
    println("  Grid: $(n_tiles_x) × $(n_tiles_y) = $(n_tiles_x * n_tiles_y) tiles")
    println("  Overlap: $(overlap)° (~$(round(overlap * 111 * 1000, digits=0)) m)")

    tiles = []

    for j in 1:n_tiles_y
        for i in 1:n_tiles_x
            # Calculate tile bounds with overlap
            tile_min_lon = min_lon + (i - 1) * tile_size_deg - (i > 1 ? overlap : 0)
            tile_max_lon = min(min_lon + i * tile_size_deg + overlap, max_lon)

            tile_min_lat = min_lat + (j - 1) * tile_size_deg - (j > 1 ? overlap : 0)
            tile_max_lat = min(min_lat + j * tile_size_deg + overlap, max_lat)

            # Ensure we don't exceed overall bounds
            tile_min_lon = max(tile_min_lon, min_lon)
            tile_min_lat = max(tile_min_lat, min_lat)

            push!(tiles, (tile_min_lon, tile_min_lat, tile_max_lon, tile_max_lat))
        end
    end

    return tiles
end

"""
    process_tiles(vrt_path, tiles, tide_zh, surge, slr;
                  output_dir="tiles", datum_offset=2.00,
                  save_individual_maps=true)

Process multiple tiles and save results.

# Arguments
- `vrt_path::String`: Path to VRT file
- `tiles::Vector`: Vector of tile bounds
- `tide_zh::Float64`: Tide level (ZH)
- `surge::Float64`: Storm surge
- `slr::Float64`: Sea level rise
- `output_dir::String`: Directory for outputs (default: "tiles")
- `datum_offset::Float64`: Vertical datum offset
- `save_individual_maps::Bool`: Save HTML map for each tile

# Returns
- Vector of (result, metadata) tuples for each tile
"""
function process_tiles(vrt_path::String, tiles::Vector,
                      tide_zh::Float64, surge::Float64, slr::Float64;
                      output_dir::String="tiles",
                      datum_offset::Float64=2.00,
                      save_individual_maps::Bool=true)

    # Create output directory
    mkpath(output_dir)

    println("\n" * "="^70)
    println("TILED FLOOD SIMULATION")
    println("="^70)
    println("Number of tiles: $(length(tiles))")
    println("Scenario: Tide=$(tide_zh)m + Surge=$(surge)m + SLR=$(slr)m")
    println("Output directory: $output_dir")
    println("="^70 * "\n")

    results = []
    total_flooded_area_km2 = 0.0
    total_flooded_pixels = 0

    start_time = now()

    for (idx, tile_bounds) in enumerate(tiles)
        println("\n[$idx/$(length(tiles))] Processing tile $(idx)...")
        println("  Bounds: $(tile_bounds)")

        try
            # Run simulation for this tile
            result, transform, metadata = run_simulation_on_vrt(
                vrt_path, tide_zh, surge, slr, tile_bounds,
                datum_offset=datum_offset
            )

            # Save GeoTIFF
            tif_file = joinpath(output_dir, "tile_$(lpad(idx, 3, '0')).tif")
            save_flood_geotiff(result, tif_file)

            # Optionally save HTML map
            if save_individual_maps
                html_file = joinpath(output_dir, "tile_$(lpad(idx, 3, '0')).html")
                save_html_map(result, html_file, metadata)
            end

            # Accumulate statistics
            total_flooded_area_km2 += metadata["flooded_area_km2"]
            total_flooded_pixels += metadata["flooded_pixels"]

            push!(results, (result, metadata, tile_bounds))

            println("  ✓ Tile $(idx) complete: $(round(metadata["flooded_area_km2"], digits=3)) km²")

        catch e
            @warn "Failed to process tile $(idx): $e"
            println("Stack trace:")
            for (exc, bt) in Base.catch_stack()
                showerror(stdout, exc, bt)
                println()
            end
            push!(results, (nothing, nothing, tile_bounds))
        end
    end

    elapsed = now() - start_time

    # Summary
    println("\n" * "="^70)
    println("SIMULATION COMPLETE")
    println("="^70)
    println("Total flooded area: $(round(total_flooded_area_km2, digits=3)) km²")
    println("Total flooded pixels: $(total_flooded_pixels)")
    println("Processing time: $(elapsed)")
    println("Output location: $output_dir")
    println("="^70 * "\n")

    return results
end

"""
    merge_tiles_to_vrt(tile_files, output_vrt)

Create a VRT mosaic from individual tile GeoTIFFs.

# Arguments
- `tile_files::Vector{String}`: List of tile GeoTIFF paths
- `output_vrt::String`: Output VRT filename

# Example
```julia
tile_files = glob("tiles/tile_*.tif")
merge_tiles_to_vrt(tile_files, "merged_flood.vrt")
```
"""
function merge_tiles_to_vrt(tile_files::Vector{String}, output_vrt::String)
    println("Creating merged VRT from $(length(tile_files)) tiles...")

    # Use GDAL to build VRT
    cmd = `gdalbuildvrt $output_vrt $tile_files`

    try
        run(cmd)
        println("✓ Merged VRT created: $output_vrt")
        println("  Open in QGIS to view the complete mosaic")
    catch e
        @warn "Failed to create VRT: $e"
        @warn "Make sure GDAL is installed and in PATH"
    end
end

"""
    create_index_map(tiles, output_file)

Create an HTML map showing the tile grid for reference.

# Arguments
- `tiles::Vector`: Vector of tile bounds
- `output_file::String`: Output HTML filename
"""
function create_index_map(tiles::Vector, output_file::String)
    println("Creating tile index map...")

    # Calculate overall bounds
    all_lons = vcat([t[1] for t in tiles], [t[3] for t in tiles])
    all_lats = vcat([t[2] for t in tiles], [t[4] for t in tiles])

    center_lon = (minimum(all_lons) + maximum(all_lons)) / 2
    center_lat = (minimum(all_lats) + maximum(all_lats)) / 2

    # Generate tile rectangles HTML
    tile_html = ""
    for (idx, tile) in enumerate(tiles)
        min_lon, min_lat, max_lon, max_lat = tile
        tile_html *= """
            L.rectangle([[$(min_lat), $(min_lon)], [$(max_lat), $(max_lon)]], {
                color: '#ff7800',
                weight: 2,
                fillColor: '#ffaa00',
                fillOpacity: 0.1
            }).addTo(map).bindPopup('<b>Tile $(idx)</b><br>Bounds: [$(round(min_lon, digits=3)), $(round(min_lat, digits=3)), $(round(max_lon, digits=3)), $(round(max_lat, digits=3))]');
        """
    end

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Tile Index Map</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body { margin: 0; padding: 0; }
            #map { height: 100vh; width: 100vw; }
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            var map = L.map('map').setView([$(center_lat), $(center_lon)], 10);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(map);

            $(tile_html)
        </script>
        <div style="position: absolute; top: 10px; right: 10px; z-index: 1000; background: white; padding: 10px; border-radius: 5px;">
            <h3>Tile Grid</h3>
            <p>Total tiles: $(length(tiles))</p>
        </div>
    </body>
    </html>
    """

    open(output_file, "w") do f
        write(f, html_content)
    end

    println("✓ Tile index map saved: $output_file")
end

# =============================================================================
# EXAMPLE USAGE: Northern Portugal Coast (Caminha to Aveiro)
# =============================================================================

if abspath(PROGRAM_FILE) == @__FILE__
    println("="^70)
    println("LARGE AREA FLOOD SIMULATION - NORTHERN PORTUGAL COAST")
    println("="^70)

    # Define large region: Caminha (north) to Aveiro (south)
    # This covers approximately 150km of coastline
    caminha_to_aveiro = (-8.90, 40.55, -8.60, 41.87)

    vrt_file = "portugal_coast_wgs84.vrt"

    if !isfile(vrt_file)
        error("VRT file not found: $vrt_file\nRun makeVRT.py first.")
    end

    # Step 1: Create tiles
    # 0.15° ≈ 16.5 km tiles with 500m overlap
    tiles = create_tiles(caminha_to_aveiro, 0.15, overlap=0.005)

    # Step 2: Create index map (for reference)
    create_index_map(tiles, "tile_index.html")
    println("\n→ Open tile_index.html to see the tile grid\n")

    # Step 3: Process all tiles
    results = process_tiles(
        vrt_file,
        tiles,
        3.8,   # HAT
        0.6,   # 50-year surge
        1.13,  # 2100 SLR
        output_dir="tiles_output",
        save_individual_maps=true  # Set to false for faster processing
    )

    # Step 4: Create merged VRT (requires GDAL CLI tools)
    # This allows viewing all tiles as one continuous dataset in QGIS
    println("\n4. Creating merged VRT...")
    tile_files = [joinpath("tiles_output", "tile_$(lpad(i, 3, '0')).tif")
                  for i in 1:length(tiles)]
    tile_files = filter(isfile, tile_files)  # Only include successful tiles

    if !isempty(tile_files)
        try
            merge_tiles_to_vrt(tile_files, "merged_flood_north_portugal.vrt")
        catch e
            println("  (Optional) Could not create merged VRT: $e")
        end
    end

    println("\n" * "="^70)
    println("ALL PROCESSING COMPLETE")
    println("="^70)
    println("\nOutputs:")
    println("  • Individual tiles: tiles_output/tile_*.tif")
    println("  • Individual maps: tiles_output/tile_*.html")
    println("  • Tile index: tile_index.html")
    println("  • Merged VRT: merged_flood_north_portugal.vrt (open in QGIS)")
    println("\nRecommendations:")
    println("  • For presentations: Use individual HTML maps for specific areas")
    println("  • For GIS analysis: Open merged VRT in QGIS/ArcGIS")
    println("  • For statistics: Sum the flooded areas from individual tiles")
    println("="^70)
end
