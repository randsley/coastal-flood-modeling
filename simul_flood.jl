#=
Coastal flood simulation for Portuguese coastal zones (Julia implementation).

Connected morphological flooding on DGT high-resolution DEMs, with a
present-day baseline water mask so that the headline figure is *newly
inundated land* rather than "every pixel below the water level", which
includes the sea itself.

Output classes (see CLASS_* constants):
    0  dry land
    1  newly inundated land   <- the headline figure
    2  baseline water (sea, estuaries, permanent water bodies)

gross = (mask > 0), net = (mask == 1), baseline = (mask == 2).

Arrays here are indexed (x, y) = (longitude, latitude), matching Rasters.jl.
The Python implementation in Simul_corrected.py is indexed (row, col) =
(latitude, longitude); the two are transposes of one another and produce the
same areas. Both read the DEM through the same GDAL call, so they see exactly
the same pixels.
=#

using Rasters
using ArchGDAL
using ImageMorphology
using Statistics
using Base64
using Dates

using Rasters.Lookups: Points

# Disable overly conservative memory checking for large VRT files.
# Safe here: reads go through ArchGDAL windows, never the whole raster.
Rasters.checkmem!(false)

# Optional dependencies for pixel-perfect HTML maps.
# Imported at top level so the types land in Main scope.
const HAS_IMAGEIO = try
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


# --- Output classes -------------------------------------------------------
const CLASS_DRY = UInt8(0)
const CLASS_NEW = UInt8(1)
const CLASS_BASELINE = UInt8(2)

"Elevation used to stand in for NoData so it can never be flooded."
const NODATA_FILL = 9999.0f0

"Portugal has no land below this elevation; anything lower is bad data."
const MIN_PLAUSIBLE_ELEVATION = -100.0f0

"Metres per degree of latitude (and of longitude at the equator)."
const METERS_PER_DEG_LAT = 111320.0


"""
    Tile

A tile of a large region.

- `bounds`: padded extent the simulation is *computed* on. The padding (overlap
  with the neighbouring tiles) exists so flooding can propagate across tile
  boundaries.
- `core`: nominal, non-overlapping extent. Outputs are cropped to this and
  areas are only counted here, so no pixel is counted twice in the regional
  total.
"""
struct Tile
    index::Int
    bounds::NTuple{4,Float64}
    core::NTuple{4,Float64}
end


"""
    DemWindow

A DEM subset: cleaned elevations, the NoData mask, the grid's GDAL
geotransform, the extent actually read and the CRS.
"""
struct DemWindow
    dem::Matrix{Float32}
    nodata_mask::Matrix{Bool}
    geotransform::Vector{Float64}
    bounds::NTuple{4,Float64}
    crs::Any
end


# ============================================================================
# LOW-LEVEL HELPERS
# ============================================================================

"""
    read_dem_window(vrt_path, bounds; downsample=1)

Read a DEM subset, optionally decimated, and clean its NoData.

# Arguments
- `vrt_path::String`: path to the VRT (or any GDAL-readable raster).
- `bounds::Tuple`: `(min_lon, min_lat, max_lon, max_lat)`, clipped to the
  raster extent.
- `downsample::Int`: integer decimation factor. 1 reads at native resolution;
  4 reads every 4th pixel (GDAL nearest neighbour), which is how large regions
  are kept within RAM. Python issues the identical GDAL call, so both read
  exactly the same pixels.

# Returns
A [`DemWindow`](@ref). Its `bounds` may be smaller than the request where that
falls outside the raster; use it, not the request, to place image overlays, or
they will be stretched into the wrong position.
"""
function read_dem_window(vrt_path::String, bounds::Tuple; downsample::Integer=1)
    downsample = max(1, Int(downsample))
    min_lon, min_lat, max_lon, max_lat = bounds

    local dem, nodata_mask, out_gt, bounds_read, crs

    ArchGDAL.read(vrt_path) do ds
        gt = ArchGDAL.getgeotransform(ds)
        raster_w = ArchGDAL.width(ds)
        raster_h = ArchGDAL.height(ds)
        res_x = gt[2]
        res_y = gt[6]   # negative for a north-up raster

        # Fractional pixel window of the request, then snap outwards and clip.
        col_a = (min_lon - gt[1]) / res_x
        col_b = (max_lon - gt[1]) / res_x
        row_a = (max_lat - gt[4]) / res_y
        row_b = (min_lat - gt[4]) / res_y

        col_off = max(0, floor(Int, min(col_a, col_b)))
        col_end = min(raster_w, ceil(Int, max(col_a, col_b)))
        row_off = max(0, floor(Int, min(row_a, row_b)))
        row_end = min(raster_h, ceil(Int, max(row_a, row_b)))

        if col_end <= col_off || row_end <= row_off
            error("Requested bounds $bounds do not overlap the raster extent")
        end

        # Trim to a whole multiple of `downsample` so the output pixel size is
        # exactly downsample x the source pixel size.
        width = col_end - col_off
        height = row_end - row_off
        if downsample > 1
            width = max(downsample, (width ÷ downsample) * downsample)
            height = max(downsample, (height ÷ downsample) * downsample)
            width = min(width, raster_w - col_off)
            height = min(height, raster_h - row_off)
        end

        out_w = max(1, width ÷ downsample)
        out_h = max(1, height ÷ downsample)

        band = ArchGDAL.getband(ds, 1)
        buffer = Array{Float32}(undef, out_w, out_h)
        ArchGDAL.read!(band, buffer, col_off, row_off, width, height)

        nodata_value = ArchGDAL.getnodatavalue(band)
        if nodata_value === nothing
            nodata_value = -9999.0
        end
        nodata_f32 = Float32(nodata_value)

        out_gt = [
            gt[1] + col_off * res_x,
            res_x * (width / out_w),
            0.0,
            gt[4] + row_off * res_y,
            0.0,
            res_y * (height / out_h),
        ]

        bounds_read = (
            gt[1] + col_off * res_x,
            gt[4] + (row_off + height) * res_y,
            gt[1] + (col_off + width) * res_x,
            gt[4] + row_off * res_y,
        )

        nodata_mask = @. isnan(buffer) | (buffer == nodata_f32) |
                         (buffer < MIN_PLAUSIBLE_ELEVATION)
        dem = @. ifelse(nodata_mask, NODATA_FILL, buffer)

        # Carry the raster's own CRS, as the Python side does. The area maths
        # below assumes geographic coordinates (degrees), which is what the
        # project's WGS84 VRT provides.
        wkt = ArchGDAL.getproj(ds)
        crs = isempty(wkt) ? EPSG(4326) :
              WellKnownText(Rasters.GeoFormatTypes.CRS(), wkt)
    end

    return DemWindow(dem, nodata_mask, out_gt, bounds_read, crs)
end


"""
    connected_flood(dem, threshold; nodata_mask=nothing, border_allowed=nothing,
                    seed_from_nodata=true)

Connected morphological flooding: which pixels below `threshold` are
hydrologically connected to open water. See [`flood_sources`](@ref) for where
water is taken to enter.

Isolated depressions below the threshold stay dry, which is the whole point of
using reconstruction rather than a bathtub fill.

`nodata_mask` marks pixels with no DEM value (already replaced by
`NODATA_FILL` in `dem`). Low ground meeting the *outside* of the coverage is
treated as a water source, because the DGT mosaic simply stops partway across
the sea; pass `seed_from_nodata=false` to switch that off.

`border_allowed`, when given, is a Bool array the size of `dem` whose border
ring marks the pixels that may act as a water source. This matters when `dem`
is a tile of a larger region: the tile's interior edges are not really
coastline, and seeding from them floods any closed depression they happen to
cut through.
"""
function connected_flood(dem::AbstractMatrix{Float32}, threshold::Real;
                         nodata_mask=nothing,
                         border_allowed=nothing,
                         seed_from_nodata::Bool=true)
    if ndims(dem) != 2 || minimum(size(dem)) < 3
        error("DEM must be 2D and at least 3x3 pixels, got $(size(dem))")
    end

    thr = Float32(threshold)
    sources = flood_sources(dem, thr; nodata_mask=nodata_mask,
                            border_allowed=border_allowed,
                            seed_from_nodata=seed_from_nodata)

    # Marker: water level at the sources, maximum elevation everywhere else, so
    # the reconstruction can only erode down through a connected path. Ground
    # at or above the threshold keeps its own elevation and acts as a wall.
    max_val = maximum(dem)
    seed = fill(max_val, size(dem))
    seed[sources] .= dem[sources]
    seed .= ifelse.(dem .< thr, seed, dem)

    flooded_surface = mreconstruct(erode, seed, dem)
    return flooded_surface .< thr
end


"""
    exterior_nodata_mask(nodata_mask)

The NoData that lies *outside* the DEM's coverage, as opposed to enclosed holes
within it.

NoData touching the edge of the array is taken to be outside the surveyed area.
NoData that does not touch the edge is an enclosed hole — a missing DGT tile
surrounded by present ones — and is not outside anything.
"""
function exterior_nodata_mask(nodata_mask::AbstractMatrix{Bool})
    any(nodata_mask) || return falses(size(nodata_mask))

    labels = label_components(nodata_mask)

    edge_labels = Set{Int}()
    for l in labels[1, :]; l != 0 && push!(edge_labels, l); end
    for l in labels[end, :]; l != 0 && push!(edge_labels, l); end
    for l in labels[:, 1]; l != 0 && push!(edge_labels, l); end
    for l in labels[:, end]; l != 0 && push!(edge_labels, l); end

    isempty(edge_labels) && return falses(size(nodata_mask))

    return [l in edge_labels for l in labels]
end


"""
    flood_sources(dem, threshold; nodata_mask=nothing, border_allowed=nothing,
                  seed_from_nodata=true)

Where water may enter the window.

Two kinds of source, both of which must be below `threshold`:

- **the edge of the array** — the usual "ocean is off the side of the map"
  assumption;
- **ground that meets the outside of the DEM coverage** — the DGT mosaic is a
  coastal strip with a stair-stepped seaward limit, so for most of the region
  the sea is *inside* the window and simply stops where the survey stops.
  Without this, a window whose edges happen to miss covered water seeds nothing
  at all and the whole region comes back dry.

Enclosed NoData (a missing tile surrounded by present ones) is not a source:
nothing is known to connect through it.

`border_allowed` restricts the *array edge* sources only. The coverage-boundary
sources are physical and are never restricted, since they do not depend on
where the window was drawn.
"""
function flood_sources(dem::AbstractMatrix{Float32}, threshold::Real;
                       nodata_mask=nothing,
                       border_allowed=nothing,
                       seed_from_nodata::Bool=true)
    thr = Float32(threshold)
    below = dem .< thr
    sources = falses(size(dem))

    # 1. The edge of the array.
    sources[1, :] .= below[1, :]
    sources[end, :] .= below[end, :]
    sources[:, 1] .= below[:, 1]
    sources[:, end] .= below[:, end]

    if border_allowed !== nothing
        size(border_allowed) == size(dem) ||
            error("border_allowed must have the same size as dem")
        sources .&= border_allowed
    end

    # 2. Low ground meeting the outside of the DEM coverage.
    if seed_from_nodata && nodata_mask !== nothing && any(nodata_mask)
        exterior = exterior_nodata_mask(nodata_mask)
        if any(exterior)
            sources .|= below .& dilate_one_pixel(exterior) .& .!nodata_mask
        end
    end

    return sources
end


"""
    dilate_one_pixel(mask)

Grow a boolean mask by one pixel in all 8 directions (3x3 box).
"""
function dilate_one_pixel(mask::AbstractMatrix{Bool})
    out = copy(mask)
    @views out[2:end, :] .|= mask[1:end-1, :]
    @views out[1:end-1, :] .|= mask[2:end, :]
    shifted = copy(out)
    @views out[:, 2:end] .|= shifted[:, 1:end-1]
    @views out[:, 1:end-1] .|= shifted[:, 2:end]
    return out
end


"""
    GlobalSeedMask

Coarse whole-region connectivity, used to decide where a tile's border may let
water in.

A tile's border is mostly an artefact of tiling, not coastline. Seeding from
all of it floods every closed basin the border cuts through — around Aveiro
that means salt pans and drainage basins. One cheap connected-flooding pass
over the *entire* region at a coarse resolution tells us where water really
does reach.

The coarse masks are dilated by one coarse pixel so that a connection narrower
than the coarse grid is not lost.
"""
struct GlobalSeedMask
    scenario::Matrix{Bool}
    baseline::Matrix{Bool}
    geotransform::Vector{Float64}
    bounds::NTuple{4,Float64}
    downsample::Int
end


"""
    border_allowed(gs, which, geotransform, size)

Bool array of `size` whose border ring marks the pixels that may act as a water
source. `which` is `:scenario` or `:baseline`. The interior is left `false`; it
is never read.
"""
function border_allowed(gs::GlobalSeedMask, which::Symbol,
                        geotransform::Vector{Float64}, sz::Tuple{Int,Int})
    coarse = which === :scenario ? gs.scenario : gs.baseline
    nx, ny = sz
    coarse_nx, coarse_ny = size(coarse)

    lons = [geotransform[1] + (i - 0.5) * geotransform[2] for i in 1:nx]
    lats = [geotransform[4] + (j - 0.5) * geotransform[6] for j in 1:ny]

    cols = clamp.(
        round.(Int, (lons .- gs.geotransform[1]) ./ gs.geotransform[2] .- 0.5) .+ 1,
        1, coarse_nx)
    rows = clamp.(
        round.(Int, (lats .- gs.geotransform[4]) ./ gs.geotransform[6] .- 0.5) .+ 1,
        1, coarse_ny)

    allowed = falses(nx, ny)
    allowed[:, 1] .= coarse[cols, rows[1]]
    allowed[:, end] .= coarse[cols, rows[end]]
    allowed[1, :] .= coarse[cols[1], rows]
    allowed[end, :] .= coarse[cols[end], rows]
    return allowed
end


"""
    build_global_seed_mask(vrt_path, bounds, flood_threshold, baseline_threshold;
                           downsample=16, verbose=true)

Run the coarse whole-region connectivity pass behind [`GlobalSeedMask`](@ref).

`bounds` is the whole region, not a tile. `downsample` defaults to 16, which on
50 cm source data is an 8 m grid: seconds of work for a 150 km coastline.
"""
function build_global_seed_mask(vrt_path::String, bounds::Tuple,
                                flood_threshold::Real, baseline_threshold::Real;
                                downsample::Integer=16, verbose::Bool=true)
    verbose && println("Coarse whole-region connectivity pass (downsample=$downsample)...")

    window = read_dem_window(vrt_path, bounds; downsample=downsample)

    verbose && println("  Coarse grid: $(size(window.dem, 1)) x $(size(window.dem, 2)) px, " *
                       "$(round(mean(window.nodata_mask) * 100, digits=1))% NoData")

    scenario = dilate_one_pixel(
        connected_flood(window.dem, flood_threshold;
                        nodata_mask=window.nodata_mask))
    baseline = dilate_one_pixel(
        connected_flood(window.dem, baseline_threshold;
                        nodata_mask=window.nodata_mask))

    if verbose
        println("  Coarse connected fraction: scenario " *
                "$(round(mean(scenario) * 100, digits=1))%, baseline " *
                "$(round(mean(baseline) * 100, digits=1))%")
    end

    return GlobalSeedMask(scenario, baseline, window.geotransform,
                          window.bounds, downsample)
end


"""
    compute_thresholds(tide_zh, surge, slr; datum_offset=2.00,
                       baseline_tide_zh=nothing, baseline_surge=0.0,
                       baseline_slr=0.0)

Scenario and baseline water levels and thresholds.

The baseline defaults to today's highest astronomical tide: the same tide, with
no surge and no sea-level rise.
"""
function compute_thresholds(tide_zh::Real, surge::Real, slr::Real;
                            datum_offset::Real=2.00,
                            baseline_tide_zh=nothing,
                            baseline_surge::Real=0.0,
                            baseline_slr::Real=0.0)
    baseline_tide = baseline_tide_zh === nothing ? tide_zh : baseline_tide_zh

    total_water_level = tide_zh + surge + slr
    baseline_water_level = baseline_tide + baseline_surge + baseline_slr

    flood_threshold = total_water_level - datum_offset
    baseline_threshold = baseline_water_level - datum_offset

    if flood_threshold < baseline_threshold
        error("Scenario threshold ($(round(flood_threshold, digits=2)) m) is " *
              "below the baseline threshold ($(round(baseline_threshold, digits=2)) m); " *
              "the scenario must be at least as high as present-day water.")
    end

    return (
        tide_zh = tide_zh,
        surge = surge,
        slr = slr,
        datum_offset = datum_offset,
        total_water_level = total_water_level,
        flood_threshold = flood_threshold,
        baseline_tide_zh = baseline_tide,
        baseline_surge = baseline_surge,
        baseline_slr = baseline_slr,
        baseline_water_level = baseline_water_level,
        baseline_threshold = baseline_threshold,
    )
end


"""
    pixel_dimensions_m(geotransform, center_lat)

Pixel size in metres for a raster in geographic coordinates.

1 degree of latitude is ~111,320 m; 1 degree of longitude is that times
cos(latitude). Returns `(width_m, height_m, area_m2)`.
"""
function pixel_dimensions_m(geotransform::Vector{Float64}, center_lat::Real)
    x_step_deg = abs(geotransform[2])
    y_step_deg = abs(geotransform[6])

    meters_per_deg_lon = METERS_PER_DEG_LAT * cos(deg2rad(center_lat))

    width_m = x_step_deg * meters_per_deg_lon
    height_m = y_step_deg * METERS_PER_DEG_LAT
    return width_m, height_m, width_m * height_m
end


"""
    summarize_mask(mask, geotransform, bounds; nodata_mask=nothing)

Area statistics for a classified flood mask, as a `Dict` with the same keys the
Python implementation uses.
"""
function summarize_mask(mask::AbstractMatrix{UInt8}, geotransform::Vector{Float64},
                        bounds::Tuple; nodata_mask=nothing)
    center_lat = (bounds[2] + bounds[4]) / 2
    width_m, height_m, pixel_area_m2 = pixel_dimensions_m(geotransform, center_lat)

    pixels_new = count(==(CLASS_NEW), mask)
    pixels_baseline = count(==(CLASS_BASELINE), mask)
    pixels_gross = pixels_new + pixels_baseline

    stats = Dict{String,Any}(
        "pixels_total" => length(mask),
        "pixels_new" => pixels_new,
        "pixels_baseline" => pixels_baseline,
        "pixels_gross" => pixels_gross,
        "flooded_area_new_m2" => pixels_new * pixel_area_m2,
        "flooded_area_new_km2" => pixels_new * pixel_area_m2 / 1_000_000,
        "baseline_area_m2" => pixels_baseline * pixel_area_m2,
        "baseline_area_km2" => pixels_baseline * pixel_area_m2 / 1_000_000,
        "flooded_area_gross_m2" => pixels_gross * pixel_area_m2,
        "flooded_area_gross_km2" => pixels_gross * pixel_area_m2 / 1_000_000,
        "pixel_area_m2" => pixel_area_m2,
        "pixel_size_m" => (width_m, height_m),
        "center_latitude" => center_lat,
        "bounds" => bounds,
    )

    if nodata_mask !== nothing
        stats["nodata_pixels"] = count(nodata_mask)
        stats["nodata_fraction"] = mean(nodata_mask)
    end

    return stats
end


"""
    classified_raster(mask, geotransform; crs=EPSG(4326))

Wrap a classified mask in a georeferenced `Raster`.

The dimension values are the *upper-left corner* of each pixel, the GDAL
geotransform convention, with `Points` sampling. That is what makes
`write(file, raster)` emit exactly this geotransform.
"""
function classified_raster(mask::AbstractMatrix{UInt8}, geotransform::Vector{Float64};
                           crs=EPSG(4326))
    nx, ny = size(mask)
    lons = range(geotransform[1], step=geotransform[2], length=nx)
    lats = range(geotransform[4], step=geotransform[6], length=ny)

    x = X(Rasters.Projected(lons; sampling=Points(), crs=crs))
    y = Y(Rasters.Projected(lats; sampling=Points(), crs=crs))

    return Raster(collect(mask), (x, y); missingval=UInt8(255))
end


# ============================================================================
# SIMULATION
# ============================================================================

"""
    run_simulation_on_vrt(vrt_path, tide_zh, surge, slr, bounds; kwargs...)

Run a coastal flood simulation and separate new inundation from water that is
already there.

Two connected-flooding passes are run over the same DEM:

- the *scenario* pass at `(tide_zh + surge + slr) - datum_offset`;
- the *baseline* pass at `baseline_tide_zh - datum_offset`, which by default is
  today's highest astronomical tide with no surge and no sea-level rise.

Newly inundated land is scenario AND NOT baseline. Without this the sea and the
Ria de Aveiro are inside the DEM's coverage and get counted as "flooded", which
inflates the figure by an order of magnitude.

# Arguments
- `vrt_path::String`: path to the VRT, e.g. `"portugal_coast_wgs84.vrt"`.
- `tide_zh::Real`: tide level relative to Hydrographic Zero (ZH), in metres.
- `surge::Real`: storm surge height in metres.
- `slr::Real`: sea level rise scenario in metres.
- `bounds::Tuple`: `(min_lon, min_lat, max_lon, max_lat)`.

# Keywords
- `datum_offset::Real=2.00`: ZH to NMM offset (2.00 m for the Viana/Aveiro zone).
- `baseline_tide_zh=nothing`: tide level (ZH) defining present-day water;
  defaults to `tide_zh`, i.e. today's HAT.
- `baseline_surge=0.0`, `baseline_slr=0.0`: normally zero, since the baseline is
  an astronomical tide, not a storm.
- `water_mask_path=nothing`: GeoPackage/shapefile to use as the baseline instead
  of the DEM-derived mask. Optional; no polygon is required.
- `water_polygon_is_land::Bool=false`: true if the polygon delineates land.
- `downsample::Integer=1`: integer decimation factor applied when reading.
- `global_seed=nothing`: a [`GlobalSeedMask`](@ref) restricting where this
  window's border may let water in. Pass it when `bounds` is a tile of a larger
  region; `process_tiles` builds and passes it for you.
- `verbose::Bool=true`

# Returns
`(result_raster, geotransform, metadata)` where `result_raster` is a classified
`Raster{UInt8}` (0 dry, 1 newly inundated land, 2 baseline water) and
`metadata` carries `flooded_area_new_km2` (headline), `flooded_area_gross_km2`
and `baseline_area_km2`.

# Example
```julia
result, gt, meta = run_simulation_on_vrt(
    "portugal_coast_wgs84.vrt",
    3.8,   # HAT
    0.6,   # 50-year surge
    1.13,  # 2100 SLR
    (-8.70, 40.95, -8.60, 41.03),
)
meta["flooded_area_new_km2"]
```
"""
function run_simulation_on_vrt(vrt_path::String, tide_zh::Real, surge::Real,
                               slr::Real, bounds::Tuple;
                               datum_offset::Real=2.00,
                               baseline_tide_zh=nothing,
                               baseline_surge::Real=0.0,
                               baseline_slr::Real=0.0,
                               water_mask_path=nothing,
                               water_polygon_is_land::Bool=false,
                               downsample::Integer=1,
                               global_seed=nothing,
                               verbose::Bool=true)

    levels = compute_thresholds(tide_zh, surge, slr;
                                datum_offset=datum_offset,
                                baseline_tide_zh=baseline_tide_zh,
                                baseline_surge=baseline_surge,
                                baseline_slr=baseline_slr)

    if verbose
        println("Scenario TWL: $(round(levels.total_water_level, digits=2))m (ZH) -> " *
                "threshold $(round(levels.flood_threshold, digits=2))m (NMM)")
        println("Baseline TWL: $(round(levels.baseline_water_level, digits=2))m (ZH) -> " *
                "threshold $(round(levels.baseline_threshold, digits=2))m (NMM)")
    end

    # --- 1. LOAD & CLIP DATA -------------------------------------------
    window = read_dem_window(vrt_path, bounds; downsample=downsample)
    dem = window.dem

    if verbose
        println("DEM window: $(size(dem, 1)) x $(size(dem, 2)) px " *
                "(downsample=$downsample), " *
                "$(round(mean(window.nodata_mask) * 100, digits=1))% NoData")
    end

    # --- 2. SCENARIO FLOODING ------------------------------------------
    scenario_border = global_seed === nothing ? nothing :
        border_allowed(global_seed, :scenario, window.geotransform, size(dem))
    baseline_border = global_seed === nothing ? nothing :
        border_allowed(global_seed, :baseline, window.geotransform, size(dem))

    verbose && println("Calculating hydrological connectivity (scenario)...")
    scenario = connected_flood(dem, levels.flood_threshold;
                               nodata_mask=window.nodata_mask,
                               border_allowed=scenario_border)

    # --- 3. BASELINE WATER ---------------------------------------------
    local baseline, baseline_source
    if water_mask_path !== nothing
        verbose && println("Baseline water from polygon: $water_mask_path")
        baseline = baseline_from_polygon(water_mask_path, size(dem),
                                         window.geotransform;
                                         polygon_is_land=water_polygon_is_land)
        baseline_source = "polygon:" * basename(water_mask_path)
    else
        verbose && println("Calculating hydrological connectivity (baseline)...")
        baseline = connected_flood(dem, levels.baseline_threshold;
                                   nodata_mask=window.nodata_mask,
                                   border_allowed=baseline_border)
        baseline_source = "morphological"
    end

    # --- 4. CLASSIFY ----------------------------------------------------
    # Baseline wins over scenario: a pixel that is water today is baseline
    # water, not new inundation. With a morphological baseline the baseline is
    # a subset of the scenario, so gross == scenario; with a polygon baseline
    # it need not be, and gross is then the union of the two.
    flood_mask = fill(CLASS_DRY, size(dem))
    flood_mask[baseline] .= CLASS_BASELINE
    flood_mask[scenario .& .!baseline] .= CLASS_NEW

    # --- 5. STATISTICS ---------------------------------------------------
    metadata = summarize_mask(flood_mask, window.geotransform, window.bounds;
                              nodata_mask=window.nodata_mask)

    for (k, v) in pairs(levels)
        metadata[String(k)] = v
    end
    metadata["baseline_source"] = baseline_source
    metadata["downsample"] = Int(downsample)
    metadata["global_seed_downsample"] =
        global_seed === nothing ? nothing : global_seed.downsample
    metadata["bounds_requested"] = bounds
    metadata["geotransform"] = window.geotransform
    metadata["crs"] = window.crs

    verbose && print_summary(metadata)

    result_raster = classified_raster(flood_mask, window.geotransform;
                                      crs=window.crs)

    return result_raster, window.geotransform, metadata
end


"""
    print_summary(metadata; indent="")

Print the headline figures, net first.
"""
function print_summary(metadata::Dict; indent::String="")
    w, h = metadata["pixel_size_m"]
    println("$(indent)Pixel size: $(round(w, digits=2))m × $(round(h, digits=2))m")
    println("$(indent)NEWLY INUNDATED LAND: " *
            "$(round(metadata["flooded_area_new_km2"], digits=3)) km² " *
            "($(round(Int, metadata["flooded_area_new_m2"])) m², " *
            "$(metadata["pixels_new"]) px)")
    println("$(indent)  baseline water (already water): " *
            "$(round(metadata["baseline_area_km2"], digits=3)) km²")
    println("$(indent)  gross below water level (net + baseline): " *
            "$(round(metadata["flooded_area_gross_km2"], digits=3)) km²")
end


"""
    baseline_from_polygon(path, size, geotransform; polygon_is_land=false)

Rasterise a land/water polygon (GeoPackage or shapefile) into a baseline water
mask. Set `polygon_is_land=true` when the polygon delineates land; the baseline
water mask is then its complement.
"""
function baseline_from_polygon(path::String, sz::Tuple{Int,Int},
                               geotransform::Vector{Float64};
                               polygon_is_land::Bool=false)
    isfile(path) || error("Water-mask polygon not found: $path")

    nx, ny = sz
    burned = falses(nx, ny)

    # Target extent, from the grid the simulation is working on.
    xmin = geotransform[1]
    xmax = geotransform[1] + nx * geotransform[2]
    ymax = geotransform[4]
    ymin = geotransform[4] + ny * geotransform[6]

    temp_tif = tempname() * ".tif"

    try
        ArchGDAL.read(path) do source
            ArchGDAL.nlayer(source) > 0 ||
                error("No vector layers found in $path")

            options = ["-burn", "1", "-init", "0", "-ot", "Byte",
                       "-of", "GTiff",
                       "-te", string(min(xmin, xmax)), string(min(ymin, ymax)),
                              string(max(xmin, xmax)), string(max(ymin, ymax)),
                       "-ts", string(nx), string(ny)]

            ArchGDAL.gdalrasterize(source, options; dest=temp_tif) do target
                buffer = Array{UInt8}(undef, nx, ny)
                ArchGDAL.read!(ArchGDAL.getband(target, 1), buffer, 0, 0, nx, ny)
                burned .= buffer .> 0
            end
        end
    finally
        isfile(temp_tif) && rm(temp_tif; force=true)
    end

    # gdal_rasterize writes north-up rows; the simulation grid is north-up too
    # (geotransform[6] < 0), so the orientations already match.
    return polygon_is_land ? .!burned : burned
end


"""
    crop_to_core(mask, geotransform, core_bounds)

Crop a tile result to its non-overlapping core extent.

Tiles are computed with an overlap so flooding can propagate across their
boundaries; counting the padded result would count the overlap strips twice.
Cropping to the core makes every pixel of the region belong to exactly one
tile.

Returns `(mask_core, geotransform_core, bounds_core)`.
"""
function crop_to_core(mask::AbstractMatrix{UInt8}, geotransform::Vector{Float64},
                      core_bounds::Tuple)
    nx, ny = size(mask)
    c_min_lon, c_min_lat, c_max_lon, c_max_lat = core_bounds

    col_a = (c_min_lon - geotransform[1]) / geotransform[2]
    col_b = (c_max_lon - geotransform[1]) / geotransform[2]
    row_a = (c_max_lat - geotransform[4]) / geotransform[6]
    row_b = (c_min_lat - geotransform[4]) / geotransform[6]

    col_off = max(0, round(Int, min(col_a, col_b)))
    col_end = min(nx, round(Int, max(col_a, col_b)))
    row_off = max(0, round(Int, min(row_a, row_b)))
    row_end = min(ny, round(Int, max(row_a, row_b)))

    if col_end <= col_off || row_end <= row_off
        error("Core bounds $core_bounds fall outside the tile")
    end

    sliced = mask[(col_off + 1):col_end, (row_off + 1):row_end]

    gt_core = [
        geotransform[1] + col_off * geotransform[2],
        geotransform[2],
        0.0,
        geotransform[4] + row_off * geotransform[6],
        0.0,
        geotransform[6],
    ]

    bounds_core = (
        gt_core[1],
        geotransform[4] + row_end * geotransform[6],
        geotransform[1] + col_end * geotransform[2],
        gt_core[4],
    )

    return sliced, gt_core, bounds_core
end


# ============================================================================
# OUTPUT
# ============================================================================

"""
    save_flood_geotiff(raster_mask, output_file; compress=true)

Save the classified flood mask as a GeoTIFF.

Band values: 0 dry land, 1 newly inundated land, 2 baseline water.
"""
function save_flood_geotiff(raster_mask, output_file::String; compress::Bool=true)
    try
        isfile(output_file) && rm(output_file)
        if compress
            write(output_file, raster_mask; force=true,
                  options=Dict("COMPRESS" => "LZW"))
        else
            write(output_file, raster_mask; force=true)
        end
        println("✓ Saved to: $output_file")
    catch e
        error("Failed to save GeoTIFF: $e")
    end
    return output_file
end


"""
    flood_overlay_png(mask)

Encode the classified mask as a base64 PNG data URL, or `nothing` if the image
packages are unavailable.
"""
function flood_overlay_png(mask::AbstractMatrix{UInt8})
    if !HAS_IMAGEIO
        @info "  Note: Install FileIO and ImageIO for pixel-perfect overlay"
        @info "  Run: using Pkg; Pkg.add([\"FileIO\", \"ImageIO\"])"
        println("  → Using rectangle approximation overlay")
        return nothing
    end

    try
        # mask is (x, y); the PNG wants (row, col) with row 1 at the north,
        # which is y index 1 because the latitude step is negative.
        nx, ny = size(mask)
        img_data = Matrix{Main.RGBA{Main.N0f8}}(undef, ny, nx)

        # Newly inundated land is the subject of the map, so it gets the strong
        # colour; baseline water is context.
        new_colour = Main.RGBA{Main.N0f8}(0.890, 0.102, 0.110, 0.843)
        baseline_colour = Main.RGBA{Main.N0f8}(0.0, 0.353, 0.784, 0.431)
        clear = Main.RGBA{Main.N0f8}(0.0, 0.0, 0.0, 0.0)

        @inbounds for j in 1:ny, i in 1:nx
            v = mask[i, j]
            img_data[j, i] = v == CLASS_NEW ? new_colour :
                             v == CLASS_BASELINE ? baseline_colour : clear
        end

        temp_png = tempname() * ".png"
        Main.save(temp_png, img_data)
        png_bytes = read(temp_png)
        rm(temp_png)

        println("  ✓ Encoded flood mask as PNG ($(length(png_bytes)) bytes)")
        return "data:image/png;base64," * base64encode(png_bytes)

    catch e
        @warn "Failed to encode PNG: $e"
        @warn "Falling back to rectangle overlay"
        return nothing
    end
end


"""
    save_html_map(raster_mask, output_file, metadata; map_center=nothing, zoom=12)

Write an interactive Leaflet map of the flood classes.

The overlay is placed on `metadata["bounds"]`, the extent actually read, which
is what keeps it registered with the basemap when the requested bounds ran past
the edge of the DEM.

Needs FileIO.jl and ImageIO.jl for the pixel-perfect overlay; without them the
map falls back to a rectangle covering the bounds.
"""
function save_html_map(raster_mask, output_file::String, metadata::Dict;
                       map_center=nothing, zoom::Int=12)
    println("Generating HTML map with pixel-perfect overlay...")

    min_lon, min_lat, max_lon, max_lat = metadata["bounds"]

    if map_center === nothing
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2
    else
        center_lat, center_lon = map_center
    end

    mask = UInt8.(Array(raster_mask))
    flood_overlay_url = flood_overlay_png(mask)

    area_new = round(metadata["flooded_area_new_km2"], digits=3)
    area_baseline = round(metadata["baseline_area_km2"], digits=3)
    area_gross = round(metadata["flooded_area_gross_km2"], digits=3)
    popup = "<b>Newly inundated land</b><br>$(area_new) km²"

    overlay_code = if flood_overlay_url !== nothing
        """
            // Pixel-perfect flood overlay from embedded PNG
            var floodBounds = [[$(min_lat), $(min_lon)], [$(max_lat), $(max_lon)]];
            var floodOverlay = L.imageOverlay(
                '$(flood_overlay_url)',
                floodBounds,
                {opacity: 1.0, interactive: true}
            ).addTo(map);

            floodOverlay.bindPopup("$(popup)");
        """
    else
        """
            // Flood overlay (rectangle approximation - install ImageIO for detail)
            var floodBounds = [[$(min_lat), $(min_lon)], [$(max_lat), $(max_lon)]];
            var floodOverlay = L.rectangle(floodBounds, {
                color: '#e31a1c',
                weight: 2,
                fillColor: '#e31a1c',
                fillOpacity: 0.4
            }).addTo(map);

            floodOverlay.bindPopup("$(popup)");
        """
    end

    pixel_w = round(metadata["pixel_size_m"][1], digits=2)
    pixel_h = round(metadata["pixel_size_m"][2], digits=2)

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
                max-width: 320px;
                font: 13px/1.4 system-ui, sans-serif;
            }
            .info h4 { margin: 0 0 5px; color: #777; }
            .info .headline { font-size: 16px; color: #b2171a; font-weight: 700; }
            .info .secondary { color: #555; }
            .legend {
                line-height: 18px;
                color: #555;
                background: white;
                padding: 10px;
                border-radius: 5px;
                box-shadow: 0 0 15px rgba(0,0,0,0.2);
                font: 13px/1.5 system-ui, sans-serif;
            }
            .legend i {
                width: 18px;
                height: 18px;
                float: left;
                margin-right: 8px;
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
                    '<div class="headline">Newly inundated land: $(area_new) km²</div>' +
                    '<div class="secondary">land dry today that floods under this scenario</div>' +
                    '<hr>' +
                    '<div class="secondary">' +
                    '<b>Baseline water today:</b> $(area_baseline) km²<br>' +
                    '<b>Gross below water level:</b> $(area_gross) km²<br>' +
                    '<i>(gross = new + baseline; it includes the sea and estuaries, so it is not land at risk)</i><br>' +
                    '<hr>' +
                    '<b>Scenario TWL:</b> $(round(metadata["total_water_level"], digits=2)) m (ZH) → $(round(metadata["flood_threshold"], digits=2)) m (NMM)<br>' +
                    '<b>Baseline TWL:</b> $(round(metadata["baseline_water_level"], digits=2)) m (ZH) → $(round(metadata["baseline_threshold"], digits=2)) m (NMM)<br>' +
                    '<b>New / baseline pixels:</b> $(metadata["pixels_new"]) / $(metadata["pixels_baseline"])<br>' +
                    '<small>Pixel size: $(pixel_w)m × $(pixel_h)m' +
                    ' (downsample $(metadata["downsample"]))</small>' +
                    '</div>';
            };
            info.addTo(map);

            // Add legend
            var legend = L.control({position: 'bottomright'});
            legend.onAdd = function (map) {
                var div = L.DomUtil.create('div', 'legend');
                div.innerHTML =
                    '<i style="background: rgba(227, 26, 28, 0.85)"></i> Newly inundated land<br>' +
                    '<i style="background: rgba(0, 90, 200, 0.45)"></i> Already water today<br>';
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
            map.fitBounds(floodBounds);
        </script>
        <div style="position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); z-index: 1000; background: white; padding: 5px; border-radius: 3px; font-size: 10px;">
            Generated with Julia + Rasters.jl | Tide: $(metadata["tide_zh"])m + Surge: $(metadata["surge"])m + SLR: $(metadata["slr"])m
            | Baseline: $(metadata["baseline_tide_zh"])m (ZH), $(metadata["baseline_source"])
        </div>
    </body>
    </html>
    """

    # Julia strings are UTF-8 and `write` emits their bytes unchanged, so the
    # "km²" and "×" in this document match the charset it declares.
    open(output_file, "w") do f
        write(f, html_content)
    end

    println("✓ HTML map saved to: $output_file")
    return output_file
end


"""
    plot_results(raster_mask; title="Flood Extent", interactive=true, background_map=false)

Visualise the flood classes using GLMakie. Requires GLMakie to be loaded.

Preserves the spatial referencing from the `Raster`: the dimension values are
pixel corners, so the heatmap lines up with the geographic coordinates. For map
backgrounds install Tyler.jl.
"""
function plot_results(raster_mask; title::String="Flood Extent",
                      interactive::Bool=true, background_map::Bool=false)
    if !isdefined(@__MODULE__, :GLMakie)
        @warn "GLMakie not loaded. Call 'using GLMakie' first."
        return nothing
    end

    try
        fig = Figure(size=(1000, 700))

        data_matrix = permutedims(UInt8.(Array(raster_mask)), (2, 1))
        x_coords = Array(dims(raster_mask, X))
        y_coords = Array(dims(raster_mask, Y))

        if background_map
            if isdefined(@__MODULE__, :Tyler)
                println("Using Tyler.jl for map background...")

                ga = GeoAxis(fig[1, 1], title=title,
                             dest="+proj=longlat +datum=WGS84")
                Tyler.Map(ga)

                rgba_overlay = similar(data_matrix, RGBA{Float32})
                for i in eachindex(data_matrix)
                    rgba_overlay[i] =
                        data_matrix[i] == CLASS_NEW ?
                            RGBA{Float32}(0.89, 0.10, 0.11, 0.85) :
                        data_matrix[i] == CLASS_BASELINE ?
                            RGBA{Float32}(0.0, 0.35, 0.78, 0.45) :
                            RGBA{Float32}(0.0, 0.0, 0.0, 0.0)
                end

                heatmap!(ga, x_coords, y_coords, rgba_overlay, interpolate=false)
            else
                @warn "Tyler.jl not loaded. Install with: using Pkg; Pkg.add(\"Tyler\")"
                println("Falling back to basic plot...")
                background_map = false
            end
        end

        if !background_map
            ax = Axis(fig[1, 1], title=title,
                      xlabel="Longitude (°E)", ylabel="Latitude (°N)",
                      aspect=DataAspect())

            hm = heatmap!(ax, x_coords, y_coords, Float64.(data_matrix),
                          colormap=[:white, :firebrick3, :dodgerblue3],
                          colorrange=(0, 2),
                          interpolate=false)

            Colorbar(fig[1, 2], hm,
                     label="0 dry / 1 newly inundated / 2 baseline water")

            ax.xgridvisible = true
            ax.ygridvisible = true
            ax.xgridstyle = :dash
            ax.ygridstyle = :dash
        end

        interactive && display(fig)
        return fig

    catch e
        @warn "Plotting failed: $e"
        println("Make sure GLMakie is loaded: using GLMakie")
        return nothing
    end
end


# --- EXAMPLE USAGE ---
if abspath(PROGRAM_FILE) == @__FILE__
    println("="^70)
    println("Coastal Flood Simulation - Julia Implementation")
    println("="^70)

    vrt_file = "portugal_coast_wgs84.vrt"
    output_file = "espinho_flood_result_julia.tif"

    # Predefined bounding boxes
    espinho_bounds = (-8.70, 40.95, -8.60, 41.03)
    aveiro_bounds = (-8.75, 40.55, -8.60, 40.75)
    espinho_aveiro_bounds = (-8.75, 40.55, -8.60, 41.03)

    selected_bounds = espinho_bounds

    if !isfile(vrt_file)
        error("VRT file '$vrt_file' not found. Run makeVRT.py first.")
    end

    println("\n1. Running simulation...")
    println("   Region: $(selected_bounds)")
    println("   Scenario: HAT + 50yr surge + 2100 SLR")
    println("   Baseline: present-day HAT, no surge, no SLR")

    result, gt, metadata = run_simulation_on_vrt(
        vrt_file,
        3.8,   # HAT (Highest Astronomical Tide)
        0.6,   # 50-year storm surge
        1.13,  # Sea level rise scenario for 2100
        selected_bounds,
    )

    println("\n2. Simulation Results:")
    println("   Scenario TWL: $(round(metadata["total_water_level"], digits=2))m (ZH) " *
            "→ $(round(metadata["flood_threshold"], digits=2))m (NMM)")
    println("   Baseline TWL: $(round(metadata["baseline_water_level"], digits=2))m (ZH) " *
            "→ $(round(metadata["baseline_threshold"], digits=2))m (NMM)")
    print_summary(metadata; indent="   ")

    println("\n3. Saving results...")
    save_flood_geotiff(result, output_file)

    html_file = replace(output_file, ".tif" => ".html")
    save_html_map(result, html_file, metadata)

    println("\n4. Visualization options:")
    println("   • HTML map: Open $html_file in browser")
    println("   • GeoTIFF: Open $output_file in QGIS/ArcGIS " *
            "(0=dry, 1=new, 2=baseline water)")
    println("   • GLMakie plot: using GLMakie; plot_results(result)")
    println("   • With map background: using GLMakie, Tyler; plot_results(result, background_map=true)")

    println("\n" * "="^70)
    println("Simulation complete!")
    println("="^70)
end
