# Tiled Flood Simulation for Large Coastal Areas
# Splits large regions into manageable tiles, counting each pixel exactly once.

include("simul_flood.jl")

using Dates
using Printf

"""
    create_tiles(bounds, tile_size_deg; overlap=0.001)

Divide a large bounding box into tiles.

Each tile carries two extents: `core`, the nominal non-overlapping extent, and
`bounds`, the core padded by `overlap` on every interior side. The simulation
runs on `bounds` so flooding can cross tile boundaries; results are cropped to
`core` so every pixel belongs to exactly one tile.

# Arguments
- `bounds::Tuple`: `(min_lon, min_lat, max_lon, max_lat)`.
- `tile_size_deg::Float64`: core tile size in degrees (0.1 ≈ 11 km).
- `overlap::Float64`: padding in degrees on each side (default 0.001 ≈ 100 m).

# Returns
`Vector{Tile}`.

# Example
```julia
tiles = create_tiles((-8.90, 40.55, -8.60, 41.87), 0.15, overlap=0.005)
tiles[1].core, tiles[1].bounds
```

# Notes
Overlap matters for hydrological connectivity at tile boundaries; 500 m
(0.005°) is a sensible minimum for coastal zones.
"""
function create_tiles(bounds::Tuple, tile_size_deg::Float64; overlap::Float64=0.001)
    min_lon, min_lat, max_lon, max_lat = bounds

    n_tiles_x = ceil(Int, (max_lon - min_lon) / tile_size_deg)
    n_tiles_y = ceil(Int, (max_lat - min_lat) / tile_size_deg)

    println("Creating tiling scheme:")
    println("  Total area: $(round(max_lon - min_lon, digits=3))° × $(round(max_lat - min_lat, digits=3))°")
    println("  Tile size: $(tile_size_deg)° (~$(round(tile_size_deg * 111, digits=1)) km)")
    println("  Grid: $(n_tiles_x) × $(n_tiles_y) = $(n_tiles_x * n_tiles_y) tiles")
    println("  Overlap: $(overlap)° (~$(round(Int, overlap * 111 * 1000)) m) on each interior side")

    # Rounding in the ceil above can ask for one row or column more than the
    # extent needs, which would yield zero-width cores. Drop any sliver.
    sliver = tile_size_deg * 1e-6

    tiles = Tile[]

    for j in 1:n_tiles_y, i in 1:n_tiles_x
        core_min_lon = min_lon + (i - 1) * tile_size_deg
        core_max_lon = min(min_lon + i * tile_size_deg, max_lon)
        core_min_lat = min_lat + (j - 1) * tile_size_deg
        core_max_lat = min(min_lat + j * tile_size_deg, max_lat)

        if core_max_lon - core_min_lon <= sliver || core_max_lat - core_min_lat <= sliver
            continue
        end

        padded = (
            max(core_min_lon - overlap, min_lon),
            max(core_min_lat - overlap, min_lat),
            min(core_max_lon + overlap, max_lon),
            min(core_max_lat + overlap, max_lat),
        )

        push!(tiles, Tile(length(tiles) + 1, padded,
                          (core_min_lon, core_min_lat, core_max_lon, core_max_lat)))
    end

    if length(tiles) != n_tiles_x * n_tiles_y
        println("  Dropped $(n_tiles_x * n_tiles_y - length(tiles)) empty edge " *
                "tile(s); $(length(tiles)) tiles to process")
    end

    return tiles
end


"""
    process_tiles(vrt_path, tiles, tide_zh, surge, slr; kwargs...)

Process a list of tiles and total their areas without double counting.

Each tile is simulated on its padded extent and then cropped to its core before
anything is saved or counted, so the overlap strips contribute to connectivity
but not to the total.

# Keywords
- `output_dir::String="tiles"`
- `datum_offset::Real=2.00`
- `save_individual_maps::Bool=true`
- `downsample::Integer=1`
- `global_seed_downsample=16`: resolution of the coarse whole-region
  connectivity pass that stops tile borders from seeding closed basins. Set to
  `nothing` to seed from every tile border, which is faster but over-predicts
  inland flooding.
- any further keywords are forwarded to [`run_simulation_on_vrt`](@ref), e.g.
  `baseline_tide_zh`, `water_mask_path`.

# Returns
`(results, totals)`. `results` holds `(mask_core, metadata_core, tile)` per
tile, or `(nothing, nothing, tile)` on failure. `totals` holds the corrected
regional figures plus `naive_*` figures showing what the uncropped sum would
have been.
"""
function process_tiles(vrt_path::String, tiles::Vector{Tile},
                       tide_zh::Real, surge::Real, slr::Real;
                       output_dir::String="tiles",
                       datum_offset::Real=2.00,
                       save_individual_maps::Bool=true,
                       downsample::Integer=1,
                       global_seed_downsample=16,
                       simulation_kwargs...)

    mkpath(output_dir)

    println("\n" * "="^70)
    println("TILED FLOOD SIMULATION")
    println("="^70)
    println("Number of tiles: $(length(tiles))")
    println("Scenario: Tide=$(tide_zh)m + Surge=$(surge)m + SLR=$(slr)m")
    println("Downsample: $downsample")
    println("Output directory: $output_dir")
    println("="^70 * "\n")

    kwargs = Dict{Symbol,Any}(simulation_kwargs)

    global_seed = nothing
    if global_seed_downsample !== nothing && global_seed_downsample !== false
        levels = compute_thresholds(tide_zh, surge, slr;
            datum_offset=datum_offset,
            baseline_tide_zh=get(kwargs, :baseline_tide_zh, nothing),
            baseline_surge=get(kwargs, :baseline_surge, 0.0),
            baseline_slr=get(kwargs, :baseline_slr, 0.0))

        region = (
            minimum(t.core[1] for t in tiles),
            minimum(t.core[2] for t in tiles),
            maximum(t.core[3] for t in tiles),
            maximum(t.core[4] for t in tiles),
        )
        global_seed = build_global_seed_mask(
            vrt_path, region, levels.flood_threshold, levels.baseline_threshold;
            downsample=global_seed_downsample)
        println()
    end

    results = []
    totals = Dict{String,Any}(
        "new_km2" => 0.0, "baseline_km2" => 0.0, "gross_km2" => 0.0,
        "pixels_new" => 0, "pixels_baseline" => 0,
        # What the previous implementation reported: the padded tiles summed,
        # which counts every overlap strip twice.
        "naive_new_km2" => 0.0, "naive_baseline_km2" => 0.0,
        "naive_gross_km2" => 0.0,
        "tiles_ok" => 0, "tiles_failed" => 0,
        "downsample" => Int(downsample),
        "global_seed_downsample" => global_seed_downsample,
    )

    start_time = now()

    for tile in tiles
        idx = tile.index
        println("\n[$idx/$(length(tiles))] Processing tile $(idx)...")
        println("  Computed on: $(round.(tile.bounds, digits=4))")
        println("  Counted on:  $(round.(tile.core, digits=4))")

        try
            result, gt, metadata = run_simulation_on_vrt(
                vrt_path, tide_zh, surge, slr, tile.bounds;
                datum_offset=datum_offset,
                downsample=downsample,
                global_seed=global_seed,
                verbose=false,
                kwargs...)

            # The padded figures, for the double-counting comparison only.
            totals["naive_new_km2"] += metadata["flooded_area_new_km2"]
            totals["naive_baseline_km2"] += metadata["baseline_area_km2"]
            totals["naive_gross_km2"] += metadata["flooded_area_gross_km2"]

            # Crop to the core so no pixel is counted twice.
            mask = UInt8.(Array(result))
            mask_core, gt_core, bounds_core = crop_to_core(mask, gt, tile.core)

            meta_core = copy(metadata)
            merge!(meta_core, summarize_mask(mask_core, gt_core, bounds_core))
            meta_core["geotransform"] = gt_core
            # This count was for the padded window and no longer matches the
            # cropped array; the fraction stays, as a property of the tile.
            delete!(meta_core, "nodata_pixels")
            meta_core["core_bounds"] = tile.core
            meta_core["padded_bounds"] = tile.bounds

            raster_core = classified_raster(mask_core, gt_core;
                                            crs=metadata["crs"])

            tif_file = joinpath(output_dir, "tile_$(lpad(idx, 3, '0')).tif")
            save_flood_geotiff(raster_core, tif_file)

            if save_individual_maps
                html_file = joinpath(output_dir, "tile_$(lpad(idx, 3, '0')).html")
                save_html_map(raster_core, html_file, meta_core)
            end

            totals["new_km2"] += meta_core["flooded_area_new_km2"]
            totals["baseline_km2"] += meta_core["baseline_area_km2"]
            totals["gross_km2"] += meta_core["flooded_area_gross_km2"]
            totals["pixels_new"] += meta_core["pixels_new"]
            totals["pixels_baseline"] += meta_core["pixels_baseline"]
            totals["tiles_ok"] += 1

            push!(results, (mask_core, meta_core, tile))

            println("  ✓ Tile $(idx): " *
                    "$(round(meta_core["flooded_area_new_km2"], digits=3)) km² new " *
                    "(gross $(round(meta_core["flooded_area_gross_km2"], digits=3)) km²)")

        catch e
            @warn "Failed to process tile $(idx): $e"
            for (exc, bt) in current_exceptions()
                showerror(stdout, exc, bt)
                println()
            end
            totals["tiles_failed"] += 1
            push!(results, (nothing, nothing, tile))
        end
    end

    elapsed = now() - start_time
    totals["elapsed"] = string(elapsed)

    println("\n" * "="^70)
    println("SIMULATION COMPLETE")
    println("="^70)
    @printf("NEWLY INUNDATED LAND (total): %.3f km²\n", totals["new_km2"])
    @printf("  baseline water today:       %.3f km²\n", totals["baseline_km2"])
    @printf("  gross below water level:    %.3f km²\n", totals["gross_km2"])
    println("Tiles: $(totals["tiles_ok"]) ok, $(totals["tiles_failed"]) failed")
    println("")
    println("Sum over padded tiles (double counts the overlaps, for comparison):")
    @printf("  new %.3f km², gross %.3f km²\n",
            totals["naive_new_km2"], totals["naive_gross_km2"])
    if totals["gross_km2"] > 0
        inflation = totals["naive_gross_km2"] / totals["gross_km2"] - 1
        @printf("  overlap inflation of the gross figure: %.1f%%\n", inflation * 100)
    end
    println("Processing time: $(elapsed)")
    println("Output location: $output_dir")
    println("="^70 * "\n")

    return results, totals
end


"""
    merge_tiles_to_vrt(tile_files, output_vrt)

Create a VRT mosaic from the tile GeoTIFFs.

The tiles are already cropped to their cores, so the mosaic has no overlapping
pixels and can be counted directly in QGIS.
"""
function merge_tiles_to_vrt(tile_files::Vector{String}, output_vrt::String)
    println("Creating merged VRT from $(length(tile_files)) tiles...")

    # Prefer ArchGDAL, which needs no GDAL command-line tools on PATH.
    try
        datasets = [ArchGDAL.read(f) for f in tile_files]
        ArchGDAL.gdalbuildvrt(datasets; dest=output_vrt) do _
            nothing
        end
        println("✓ Merged VRT created: $output_vrt")
        println("  Open in QGIS to view the complete mosaic")
        return output_vrt
    catch e
        @warn "ArchGDAL.gdalbuildvrt failed: $e"
    end

    try
        run(`gdalbuildvrt $output_vrt $tile_files`)
        println("✓ Merged VRT created: $output_vrt")
        return output_vrt
    catch e
        @warn "Failed to create VRT: $e"
        @warn "Make sure GDAL is installed and in PATH"
        return nothing
    end
end


"""
    create_index_map(tiles, output_file)

Write an HTML map of the tile grid, showing core and padded extents.
"""
function create_index_map(tiles::Vector{Tile}, output_file::String)
    println("Creating tile index map...")

    all_lons = vcat([t.bounds[1] for t in tiles], [t.bounds[3] for t in tiles])
    all_lats = vcat([t.bounds[2] for t in tiles], [t.bounds[4] for t in tiles])

    center_lon = (minimum(all_lons) + maximum(all_lons)) / 2
    center_lat = (minimum(all_lats) + maximum(all_lats)) / 2

    tile_html = ""
    for tile in tiles
        c_min_lon, c_min_lat, c_max_lon, c_max_lat = tile.core
        p_min_lon, p_min_lat, p_max_lon, p_max_lat = tile.bounds
        tile_html *= """
            L.rectangle([[$(p_min_lat), $(p_min_lon)], [$(p_max_lat), $(p_max_lon)]], {
                color: '#999999', weight: 1, dashArray: '4 3', fill: false
            }).addTo(map);
            L.rectangle([[$(c_min_lat), $(c_min_lon)], [$(c_max_lat), $(c_max_lon)]], {
                color: '#ff7800',
                weight: 2,
                fillColor: '#ffaa00',
                fillOpacity: 0.1
            }).addTo(map).bindPopup('<b>Tile $(tile.index)</b><br>Core: [$(round(c_min_lon, digits=3)), $(round(c_min_lat, digits=3)), $(round(c_max_lon, digits=3)), $(round(c_max_lat, digits=3))]<br>Computed: [$(round(p_min_lon, digits=3)), $(round(p_min_lat, digits=3)), $(round(p_max_lon, digits=3)), $(round(p_max_lat, digits=3))]');
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
            L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
                attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, &copy; OpenStreetMap contributors',
                maxZoom: 19
            }).addTo(map);

            $(tile_html)
        </script>
        <div style="position: absolute; top: 10px; right: 10px; z-index: 1000; background: white; padding: 10px; border-radius: 5px; font: 13px/1.4 system-ui, sans-serif;">
            <h3>Tile Grid</h3>
            <p>Total tiles: $(length(tiles))</p>
            <p><span style="color:#ff7800">■</span> core (counted once)<br>
               <span style="color:#999">⬚</span> computed extent (with overlap)</p>
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

    # Caminha (north) to Aveiro (south), roughly 150 km of coastline
    caminha_to_aveiro = (-8.90, 40.55, -8.60, 41.87)

    vrt_file = "portugal_coast_wgs84.vrt"

    if !isfile(vrt_file)
        error("VRT file not found: $vrt_file\nRun makeVRT.py first.")
    end

    # 0.15° ≈ 16.5 km cores with 500 m of overlap for connectivity
    tiles = create_tiles(caminha_to_aveiro, 0.15, overlap=0.005)

    create_index_map(tiles, "tile_index_julia.html")
    println("\n→ Open tile_index_julia.html to see the tile grid\n")

    results, totals = process_tiles(
        vrt_file,
        tiles,
        3.8,   # HAT
        0.6,   # 50-year surge
        1.13;  # 2100 SLR
        output_dir="tiles_output_julia",
        save_individual_maps=true,
        downsample=4,  # ~2 m; the 50 cm VRT does not fit in RAM at 1
    )

    println("\n4. Creating merged VRT...")
    tile_files = [joinpath("tiles_output_julia", "tile_$(lpad(i, 3, '0')).tif")
                  for i in 1:length(tiles)]
    tile_files = filter(isfile, tile_files)

    if !isempty(tile_files)
        merge_tiles_to_vrt(tile_files, "merged_flood_north_portugal_julia.vrt")
    end

    println("\n" * "="^70)
    println("ALL PROCESSING COMPLETE")
    println("="^70)
    println("\nOutputs:")
    println("  • Individual tiles: tiles_output_julia/tile_*.tif")
    println("  • Individual maps: tiles_output_julia/tile_*.html")
    println("  • Tile index: tile_index_julia.html")
    println("  • Merged VRT: merged_flood_north_portugal_julia.vrt (open in QGIS)")
    println("\nRecommendations:")
    println("  • For presentations: Use individual HTML maps for specific areas")
    println("  • For GIS analysis: Open merged VRT in QGIS/ArcGIS")
    println("  • For statistics: use the totals returned by process_tiles; the " *
            "tiles are cropped to their cores so nothing is counted twice")
    println("="^70)
end
