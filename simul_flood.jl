using Rasters
using ArchGDAL
using ImageMorphology
using Statistics
using Base64

# Disable overly conservative memory checking for large VRT files
# This is safe because we're using lazy loading and only reading small subsets
Rasters.checkmem!(false)

# Optional dependencies for pixel-perfect HTML maps
# Import at top level so types are available in Main scope
const HAS_IMAGEIO = try
    # These must be imported at module level to export types properly
    @eval Main begin
        using FileIO
        using ImageIO
        using ColorTypes: RGBA, N0f8
    end
    true
catch e
    @warn "Optional image encoding packages not available: $e"
    @warn "Install with: using Pkg; Pkg.add([\"FileIO\", \"ImageIO\", \"ColorTypes\"])"
    false
end

"""
    run_simulation_on_vrt(vrt_path, tide_zh, surge, slr, bounds; datum_offset=2.00)

Runs a coastal flood simulation using Connected Morphological Flooding algorithm.

# Arguments
- `vrt_path::String`: Path to the VRT file (e.g., 'portugal_coast_wgs84.vrt')
- `tide_zh::Float64`: Tide level relative to Hydrographic Zero (ZH) in meters
- `surge::Float64`: Storm surge height in meters
- `slr::Float64`: Sea level rise scenario in meters
- `bounds::Tuple`: Bounding box as (min_lon, min_lat, max_lon, max_lat)
- `datum_offset::Float64`: Vertical offset between ZH and NMM datum (default: 2.00m for Viana/Aveiro)

# Returns
- `flood_mask`: Boolean array indicating flooded areas
- `transform`: Affine transform for georeferencing
- `metadata`: Dict with simulation statistics and parameters

# Example
```julia
result = run_simulation_on_vrt(
    "portugal_coast_wgs84.vrt",
    3.8,   # HAT
    0.6,   # 50-year surge
    1.13,  # 2100 SLR
    (-8.70, 40.95, -8.60, 41.03)  # Espinho bounds
)
```
"""
function run_simulation_on_vrt(vrt_path::String, tide_zh::Float64, surge::Float64, slr::Float64, bounds::Tuple; datum_offset::Float64=2.00)
    # --- 1. PARAMETERS ---
    # Calculate total water level and flood threshold
    # DGT Datum (Cascais 1938) vs Hydrographic Zero (ZH)
    total_water_level = tide_zh + surge + slr
    flood_threshold = total_water_level - datum_offset
    
    println("Simulating TWL: $(round(total_water_level, digits=2))m (ZH) -> Threshold: $(round(flood_threshold, digits=2))m (NMM)")

    # --- 2. LOAD & CLIP DATA ---
    # bounds tuple in Julia: (min_lon, min_lat, max_lon, max_lat)
    min_lon, min_lat, max_lon, max_lat = bounds

    println("Loading and clipping raster...")

    # Load VRT and handle errors
    local rast, dem_clip, dem_array, transform
    try
        # Load VRT lazily (memory check disabled globally)
        # X=Longitude, Y=Latitude
        rast = Raster(vrt_path; lazy=true)

        # Clip the raster to area of interest using view (efficient subsetting)
        dem_clip = view(rast, X(Between(min_lon, max_lon)), Y(Between(min_lat, max_lat)))

        # Read only the clipped subset into memory
        dem_array = read(dem_clip)

        # Extract first band if multi-band
        if hasdim(dem_array, Band)
            dem_array = dem_array[Band(1)]  # Extract first band
        end

        # Store the transform for output
        transform = (dims(dem_clip, X), dims(dem_clip, Y))

    catch e
        error("Failed to load raster file: $e")
    end

    # --- 3. HANDLE NODATA ---
    # Rasters.jl handles missing values automatically, but ImageMorphology needs clean floats
    nodata_marker = 9999.0

    # Try to read nodata value from metadata
    nodata_value = try
        missingval(dem_array)
    catch
        -9999.0  # Default DGT nodata value
    end

    if nodata_value !== nothing && !ismissing(nodata_value) && nodata_value != -9999.0
        println("NoData value from metadata: $nodata_value")
    end

    # Create a clean Float64 array for calculation
    # Replace 'missing', nodata values, and extreme negative values with high elevation

    # First, replace all missing values with nodata_marker using coalesce
    # This ensures we have a concrete numeric array
    dem_clean = map(x -> coalesce(x, nodata_marker), collect(dem_array))

    # Now map to handle nodata values and unrealistic elevations
    # At this point, no missing values exist
    dem_calc = map(dem_clean) do x
        # Use isequal for nodata comparison (handles NaN correctly)
        if !isnothing(nodata_value) && !ismissing(nodata_value) && isequal(x, nodata_value)
            return nodata_marker
        end

        # Check for unrealistic elevations
        if x < -100  # Portugal has no elevations below -100m
            return nodata_marker
        end

        return Float64(x)
    end

    # --- 4. CONNECTED FLOODING ---
    println("Calculating hydrological connectivity...")

    # Seed logic:
    # 1. Create a copy of the DEM
    seed = copy(dem_calc)
    
    # 2. Set the "interior" of the seed to the Maximum value (infinite wall)
    # Note: Julia uses 1-based indexing. 
    # Python [1:-1, 1:-1] is Julia [2:end-1, 2:end-1]
    max_val = maximum(skipmissing(dem_calc))
    seed[2:end-1, 2:end-1] .= max_val
    
    # 3. Apply Threshold Logic for Seed
    # If DEM < threshold (potential flood zone), keep Seed as MAX (so it can be eroded down)
    # If DEM >= threshold (land), Seed becomes DEM
    # This sets up the 'Reconstruction by Erosion' constraint: Marker (seed) >= Mask (dem)
    seed = map((s, d) -> d < flood_threshold ? s : d, seed, dem_calc)

    # 4. Run Morphological Reconstruction (Erosion)
    # Erode the seed (high water) down to DEM level, only where connected to edges
    # This ensures only hydrologically-connected areas are flooded
	flooded_surface = mreconstruct(erode, seed, dem_calc)
    
    # Create Binary Mask
    # Areas where the reconstructed surface is lower than water level
    flood_mask = flooded_surface .< flood_threshold

    # --- 5. STATISTICS ---
    # Calculate pixel area in real-world units (m² and km²)
    # Note: We're in WGS84 (EPSG:4326), so coordinates are in degrees
    x_step_deg = abs(step(dims(dem_array, X)))
    y_step_deg = abs(step(dims(dem_array, Y)))

    # Get center latitude for area calculation
    center_lat = (min_lat + max_lat) / 2
    center_lat_rad = deg2rad(center_lat)

    # Convert degrees to meters at this latitude
    # 1 degree latitude ≈ 111,320 meters (constant)
    # 1 degree longitude ≈ 111,320 * cos(latitude) meters (varies with latitude)
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * cos(center_lat_rad)

    # Calculate pixel dimensions in meters
    pixel_width_m = x_step_deg * meters_per_deg_lon
    pixel_height_m = y_step_deg * meters_per_deg_lat
    pixel_area_m2 = pixel_width_m * pixel_height_m
    pixel_area_km2 = pixel_area_m2 / 1_000_000  # Convert to km²

    flooded_pixels = count(flood_mask)
    flooded_area_m2 = flooded_pixels * pixel_area_m2
    flooded_area_km2 = flooded_area_m2 / 1_000_000

    println("Flooded pixels: $(flooded_pixels)")
    println("Pixel size: $(round(pixel_width_m, digits=2))m × $(round(pixel_height_m, digits=2))m")
    println("Flooded area: $(round(flooded_area_km2, digits=3)) km² ($(round(flooded_area_m2, digits=0)) m²)")

    # --- 6. PREPARE OUTPUT ---
    # Create metadata dictionary
    metadata = Dict(
        "tide_zh" => tide_zh,
        "surge" => surge,
        "slr" => slr,
        "datum_offset" => datum_offset,
        "total_water_level" => total_water_level,
        "flood_threshold" => flood_threshold,
        "flooded_pixels" => flooded_pixels,
        "flooded_area_m2" => flooded_area_m2,
        "flooded_area_km2" => flooded_area_km2,
        "pixel_area_m2" => pixel_area_m2,
        "pixel_size_m" => (pixel_width_m, pixel_height_m),
        "center_latitude" => center_lat,
        "bounds" => bounds
    )

    # Return flood mask as a georeferenced Raster, transform, and metadata
    result_raster = rebuild(dem_clip, flood_mask)

    return result_raster, transform, metadata
end

"""
    save_flood_geotiff(raster_mask, output_file; compress=true)

Save flood mask as a GeoTIFF file.

# Arguments
- `raster_mask`: Raster object with flood mask (Bool or UInt8)
- `output_file::String`: Path to output GeoTIFF file
- `compress::Bool`: Apply LZW compression (default: true)
"""
function save_flood_geotiff(raster_mask, output_file::String; compress::Bool=true)
    # Convert Bool mask to UInt8 (1=Flooded, 0=Dry)
    save_raster = map(x -> x ? UInt8(1) : UInt8(0), raster_mask)

    try
        write(output_file, save_raster)
        println("✓ Saved to: $output_file")
    catch e
        error("Failed to save GeoTIFF: $e")
    end
end

"""
    save_html_map(raster_mask, output_file, metadata; map_center=nothing, zoom=12)

Create an interactive HTML map with basemap and pixel-perfect flood overlay.
Uses Leaflet.js for web-based visualization with OpenStreetMap tiles.

# Arguments
- `raster_mask`: Raster object with flood mask
- `output_file::String`: Path to output HTML file
- `metadata::Dict`: Simulation metadata
- `map_center::Union{Nothing,Tuple}`: Optional (lat, lon) center, auto-calculated if nothing
- `zoom::Int`: Initial zoom level (default: 12)

# Requirements
Requires FileIO.jl and ImageIO.jl for PNG encoding.
Install with: `using Pkg; Pkg.add(["FileIO", "ImageIO"])`

# Example
```julia
save_html_map(result, "flood_map.html", metadata)
```
"""
function save_html_map(raster_mask, output_file::String, metadata::Dict; map_center=nothing, zoom::Int=12)
    println("Generating HTML map with pixel-perfect overlay...")

    # Get bounds
    bounds = metadata["bounds"]
    min_lon, min_lat, max_lon, max_lat = bounds

    # Calculate map center if not provided
    if isnothing(map_center)
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2
    else
        center_lat, center_lon = map_center
    end

    # Try to create pixel-perfect PNG overlay
    flood_overlay_url = nothing

    if HAS_IMAGEIO
        try
            # Convert flood mask to RGBA image
            data_array = Array(raster_mask)

            # Get dimensions - Raster arrays are (X, Y) where:
            # - First index (i) is X/longitude (west to east)
            # - Second index (j) is Y/latitude (south to north)
            nx, ny = size(data_array)

            # Create image with dimensions (height, width) = (rows, cols)
            # - Rows correspond to latitude (Y) - ny rows
            # - Columns correspond to longitude (X) - nx columns
            img_data = Matrix{RGBA{N0f8}}(undef, ny, nx)

            # Fill the image: blue for flooded, transparent for dry
            # Try direct mapping - let Leaflet handle orientation via bounds
            for j in 1:ny  # Latitude index (south to north)
                for i in 1:nx  # Longitude index (west to east)
                    # Direct mapping: j→row, i→col
                    if data_array[i, j]  # Flooded pixel
                        # Blue color with transparency
                        img_data[j, i] = RGBA{N0f8}(0.0, 0.4, 1.0, 0.7)
                    else  # Dry pixel
                        # Fully transparent
                        img_data[j, i] = RGBA{N0f8}(0.0, 0.0, 0.0, 0.0)
                    end
                end
            end

            # Save as temporary PNG file
            temp_png = tempname() * ".png"
            save(temp_png, img_data)

            # Read PNG and encode as base64
            png_bytes = read(temp_png)
            png_base64 = base64encode(png_bytes)

            # Clean up temp file
            rm(temp_png)

            # Create data URL for embedding
            flood_overlay_url = "data:image/png;base64," * png_base64

            println("  ✓ Encoded flood mask as PNG ($(length(png_bytes)) bytes)")

        catch e
            @warn "Failed to encode PNG: $e"
            @warn "Falling back to rectangle overlay"
        end
    else
        @info "  Note: Install FileIO and ImageIO for pixel-perfect overlay"
        @info "  Run: using Pkg; Pkg.add([\"FileIO\", \"ImageIO\"])"
        println("  → Using rectangle approximation overlay")
    end

    # Create HTML with Leaflet.js
    # Choose between pixel-perfect overlay or rectangle fallback
    if !isnothing(flood_overlay_url)
        # Pixel-perfect overlay using embedded PNG
        overlay_code = """
            // Add pixel-perfect flood overlay from embedded PNG
            var floodBounds = [[$(min_lat), $(min_lon)], [$(max_lat), $(max_lon)]];
            var floodOverlay = L.imageOverlay(
                '$(flood_overlay_url)',
                floodBounds,
                {opacity: 1.0, interactive: true}
            ).addTo(map);

            floodOverlay.bindPopup("<b>Flooded Area</b><br>$(round(metadata["flooded_area_km2"], digits=3)) km²");
        """
    else
        # Fallback to rectangle overlay
        overlay_code = """
            // Add flood overlay (rectangle approximation)
            var floodBounds = [[$(min_lat), $(min_lon)], [$(max_lat), $(max_lon)]];
            var floodOverlay = L.rectangle(floodBounds, {
                color: '#0064ff',
                weight: 2,
                fillColor: '#0064ff',
                fillOpacity: 0.4
            }).addTo(map);

            floodOverlay.bindPopup("<b>Flooded Area</b><br>$(round(metadata["flooded_area_km2"], digits=3)) km²");
        """
    end

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Coastal Flood Simulation - Julia</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body { margin: 0; padding: 0; }
            #map { height: 100vh; width: 100vw; }
            .info {
                padding: 10px;
                background: white;
                border-radius: 5px;
                box-shadow: 0 0 15px rgba(0,0,0,0.2);
            }
            .info h4 { margin: 0 0 5px; color: #777; }
            .legend {
                line-height: 18px;
                color: #555;
                background: white;
                padding: 10px;
                border-radius: 5px;
                box-shadow: 0 0 15px rgba(0,0,0,0.2);
            }
            .legend i {
                width: 18px;
                height: 18px;
                float: left;
                margin-right: 8px;
                opacity: 0.7;
            }
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            // Initialize map
            var map = L.map('map').setView([$(center_lat), $(center_lon)], $(zoom));

            // Add OpenStreetMap tiles (default)
            var osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                maxZoom: 19
            }).addTo(map);

            // Add satellite layer option
            var satellite = L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {
                attribution: 'Google Satellite',
                maxZoom: 20
            });

            $(overlay_code)

            // Add info box
            var info = L.control({position: 'topright'});
            info.onAdd = function (map) {
                this._div = L.DomUtil.create('div', 'info');
                this.update();
                return this._div;
            };
            info.update = function (props) {
                this._div.innerHTML = '<h4>Flood Simulation Results</h4>' +
                    '<b>Total Water Level:</b> $(round(metadata["total_water_level"], digits=2)) m (ZH)<br>' +
                    '<b>Flood Threshold:</b> $(round(metadata["flood_threshold"], digits=2)) m (NMM)<br>' +
                    '<b>Flooded Area:</b> $(round(metadata["flooded_area_km2"], digits=3)) km²<br>' +
                    '<b>Flooded Pixels:</b> $(metadata["flooded_pixels"])<br>' +
                    '<small>Pixel size: $(round(metadata["pixel_size_m"][1], digits=2))m × $(round(metadata["pixel_size_m"][2], digits=2))m</small>';
            };
            info.addTo(map);

            // Add legend
            var legend = L.control({position: 'bottomright'});
            legend.onAdd = function (map) {
                var div = L.DomUtil.create('div', 'legend');
                div.innerHTML = '<i style="background: rgba(0, 100, 255, 0.7)"></i> Flooded Area<br>';
                return div;
            };
            legend.addTo(map);

            // Layer control
            var baseMaps = {
                "OpenStreetMap": osm,
                "Satellite": satellite
            };
            var overlayMaps = {
                "Flood Extent": floodOverlay
            };
            L.control.layers(baseMaps, overlayMaps).addTo(map);

            // Fit map to flood bounds
            var floodBounds = [[$(min_lat), $(min_lon)], [$(max_lat), $(max_lon)]];
            map.fitBounds(floodBounds);
        </script>
        <div style="position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); z-index: 1000; background: white; padding: 5px; border-radius: 3px; font-size: 10px;">
            Generated with Julia + Rasters.jl | Tide: $(metadata["tide_zh"])m + Surge: $(metadata["surge"])m + SLR: $(metadata["slr"])m
        </div>
    </body>
    </html>
    """

    # Write HTML file
    open(output_file, "w") do f
        write(f, html_content)
    end

    println("✓ HTML map saved to: $output_file")
    return output_file
end

"""
    plot_results(raster_mask; title="Flood Extent", interactive=true, background_map=false)

Visualize flood extent using GLMakie. Requires GLMakie to be loaded.
Properly handles Raster spatial context - coordinates represent pixel centers.

# Arguments
- `raster_mask`: Raster object with flood mask
- `title::String`: Plot title
- `interactive::Bool`: Enable interactive display
- `background_map::Bool`: Add map tile background (requires Tyler.jl)

# Note
This function preserves the spatial referencing from the Raster object.
Pixels are plotted as areas with coordinates representing their centers.

For map backgrounds, install Tyler.jl: `using Pkg; Pkg.add("Tyler")`
"""
function plot_results(raster_mask; title::String="Flood Extent", interactive::Bool=true, background_map::Bool=false)
    # Check if GLMakie is loaded
    if !isdefined(@__MODULE__, :GLMakie)
        @warn "GLMakie not loaded. Call 'using GLMakie' first."
        return nothing
    end

    # Try to use map background if requested
    try
        fig = Figure(size=(1000, 700))

        if background_map
            # Try to use Tyler.jl for map tiles background
            if isdefined(@__MODULE__, :Tyler)
                println("Using Tyler.jl for map background...")

                # Create GeoAxis (geographic axis) for Tyler integration
                ga = GeoAxis(fig[1, 1],
                            title=title,
                            dest="+proj=longlat +datum=WGS84")

                # Add map tiles
                Tyler.Map(ga)

                # Overlay flood data
                plot_data = Float64.(raster_mask)
                x_coords = Array(dims(raster_mask, X))
                y_coords = Array(dims(raster_mask, Y))
                data_matrix = permutedims(Array(plot_data), (2, 1))

                # Create RGBA overlay (blue for flooded, transparent for dry)
                rgba_overlay = similar(data_matrix, RGBA{Float32})
                for i in eachindex(data_matrix)
                    if data_matrix[i] > 0.5
                        rgba_overlay[i] = RGBA{Float32}(0.0, 0.4, 1.0, 0.6)  # Blue with transparency
                    else
                        rgba_overlay[i] = RGBA{Float32}(0.0, 0.0, 0.0, 0.0)  # Transparent
                    end
                end

                hm = heatmap!(ga, x_coords, y_coords, rgba_overlay, interpolate=false)
                Colorbar(fig[1, 2], hm, label="Flood Extent")

            else
                @warn "Tyler.jl not loaded. Install with: using Pkg; Pkg.add(\"Tyler\")"
                println("Falling back to basic plot...")
                background_map = false  # Fall back to basic plot
            end
        end

        if !background_map
            # Basic plot without map background
            ax = Axis(fig[1, 1],
                      title=title,
                      xlabel="Longitude (°E)",
                      ylabel="Latitude (°N)",
                      aspect=DataAspect())

            # Plot the Raster directly - this preserves all spatial metadata
            plot_data = Float64.(raster_mask)
            x_coords = Array(dims(raster_mask, X))
            y_coords = Array(dims(raster_mask, Y))
            data_matrix = permutedims(Array(plot_data), (2, 1))

            hm = heatmap!(ax, x_coords, y_coords, data_matrix,
                          colormap=[:white, :dodgerblue3],
                          colorrange=(0, 1),
                          interpolate=false)

            Colorbar(fig[1, 2], hm, label="Flooded (1) / Dry (0)")

            # Add grid for better spatial reference
            ax.xgridvisible = true
            ax.ygridvisible = true
            ax.xgridstyle = :dash
            ax.ygridstyle = :dash
        end

        if interactive
            display(fig)
        end

        return fig

    catch e
        @warn "Plotting failed: $e"
        println("Make sure GLMakie is loaded: using GLMakie")
        return nothing
    end
end

# --- EXAMPLE USAGE ---
if abspath(PROGRAM_FILE) == @__FILE__
    println("="^60)
    println("Coastal Flood Simulation - Julia Implementation")
    println("="^60)

    # Configuration
    vrt_file = "portugal_coast_wgs84.vrt"
    output_file = "espinho_flood_result.tif"

    # Predefined bounding boxes
    espinho_bounds = (-8.70, 40.95, -8.60, 41.03)
    aveiro_bounds = (-8.75, 40.55, -8.60, 40.75)
    espinho_aveiro_bounds = (-8.75, 40.55, -8.60, 41.03)

    # Use combined region
    selected_bounds = espinho_aveiro_bounds

    if !isfile(vrt_file)
        error("VRT file '$vrt_file' not found. Run makeVRT.py first.")
    end

    println("\n1. Running simulation...")
    println("   Region: $(selected_bounds)")
    println("   Scenario: HAT + 50yr surge + 2100 SLR")

    # Run simulation
    result, transform, metadata = run_simulation_on_vrt(
        vrt_file,
        3.8,   # HAT (Highest Astronomical Tide)
        0.6,   # 50-year storm surge
        1.13,  # Sea level rise scenario for 2100
        selected_bounds
    )

    # Display metadata
    println("\n2. Simulation Results:")
    println("   Total Water Level: $(round(metadata["total_water_level"], digits=2))m (ZH)")
    println("   Flood Threshold: $(round(metadata["flood_threshold"], digits=2))m (NMM)")
    println("   Flooded Area: $(round(metadata["flooded_area_km2"], digits=3)) km²")

    # Save outputs
    println("\n3. Saving results...")
    save_flood_geotiff(result, output_file)

    # Save HTML map
    html_file = replace(output_file, ".tif" => ".html")
    save_html_map(result, html_file, metadata)

    # Optional visualization
    println("\n4. Visualization options:")
    println("   • HTML map: Open $html_file in browser")
    println("   • GeoTIFF: Open $output_file in QGIS/ArcGIS")
    println("   • GLMakie plot: using GLMakie; plot_results(result)")
    println("   • With map background: using GLMakie, Tyler; plot_results(result, background_map=true)")

    println("\n" * "="^60)
    println("Simulation complete!")
    println("="^60)
end