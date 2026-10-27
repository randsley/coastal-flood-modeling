#=
Tests for the coastal flood simulation (Julia implementation).

Runs against a small synthetic DEM so it needs no DGT data:

    (a) a pond not connected to the sea is not flooded;
    (b) sea pixels are excluded from the net figure;
    (c) net + baseline <= gross;
    (d) the generated HTML files decode as UTF-8;
    (e) the tiled total counts each pixel once.

Run with `julia test_flood_simulation.jl`.

The layout mirrors test_flood_simulation.py, including the synthetic DEM, so
the two implementations are checked against the same expectations.
=#

using Test
using ArchGDAL

include("simul_flood_tiled.jl")

# Scenario used throughout: datum offset 0 keeps thresholds equal to the tide
# values, so the synthetic elevations can be read directly.
const DATUM_OFFSET = 0.0
const BASELINE_TIDE = 0.5     # present-day water line
const SCENARIO_TIDE = 1.5     # scenario water line

# Synthetic DEM layout. Arrays here are (x, y) = (lon, lat):
#   x 1..40     sea            -5.0 m   (touches the west edge)
#   x 41..60    low coast strip  1.0 m  (dry today, floods in the scenario)
#   x 61..160   upland          10.0 m
#   a pond at -3.0 m sits inside the upland, ringed by 10 m, so it is below
#   both water levels but connected to nothing.
const NX = 160
const NY = 120
const SEA_END = 40
const STRIP_END = 60
const POND_X = 101:130
const POND_Y = 71:90

const PIXEL_DEG = 0.0001
const ORIGIN_LON = -8.70
const ORIGIN_LAT = 41.00

const SYNTHETIC_BOUNDS = (
    ORIGIN_LON,
    ORIGIN_LAT - NY * PIXEL_DEG,
    ORIGIN_LON + NX * PIXEL_DEG,
    ORIGIN_LAT,
)


"True when `haystack` contains the byte sequence `needle`."
function contains_bytes(haystack::Vector{UInt8}, needle::Vector{UInt8})
    n = length(needle)
    n == 0 && return true
    for i in 1:(length(haystack) - n + 1)
        @views haystack[i:(i + n - 1)] == needle && return true
    end
    return false
end


"Write the synthetic DEM to `path` and return the elevation array."
function make_synthetic_dem(path::String)
    dem = fill(10.0f0, NX, NY)
    dem[1:SEA_END, :] .= -5.0f0
    dem[(SEA_END + 1):STRIP_END, :] .= 1.0f0
    dem[POND_X, POND_Y] .= -3.0f0

    # Keep the north, south and east edges as upland so the sea is the only
    # thing the flood can be seeded from.
    dem[(STRIP_END + 1):end, 1] .= 10.0f0
    dem[(STRIP_END + 1):end, end] .= 10.0f0
    dem[end, :] .= 10.0f0

    gt = [ORIGIN_LON, PIXEL_DEG, 0.0, ORIGIN_LAT, 0.0, -PIXEL_DEG]

    ArchGDAL.create(path; driver=ArchGDAL.getdriver("GTiff"),
                    width=NX, height=NY, nbands=1, dtype=Float32) do ds
        ArchGDAL.setgeotransform!(ds, gt)
        ArchGDAL.setproj!(ds, ArchGDAL.toWKT(ArchGDAL.importEPSG(4326)))
        band = ArchGDAL.getband(ds, 1)
        ArchGDAL.setnodatavalue!(band, -9999.0)
        ArchGDAL.write!(band, dem)
    end

    return dem
end


function run_on_synthetic(path::String; kwargs...)
    defaults = Dict{Symbol,Any}(
        :datum_offset => DATUM_OFFSET,
        :baseline_tide_zh => BASELINE_TIDE,
        :verbose => false,
    )
    merge!(defaults, Dict{Symbol,Any}(kwargs))
    return run_simulation_on_vrt(path, SCENARIO_TIDE, 0.0, 0.0,
                                 SYNTHETIC_BOUNDS; defaults...)
end


mktempdir() do tmp
    dem_path = joinpath(tmp, "dem.tif")
    make_synthetic_dem(dem_path)

    result, gt, meta = run_on_synthetic(dem_path)
    mask = UInt8.(Array(result))

    @testset "flood simulation" begin

        @testset "(a) a disconnected pond is not flooded" begin
            pond = mask[POND_X, POND_Y]
            @test all(pond .== CLASS_DRY)

            # A bathtub fill would have flooded it, so the test can fail.
            @test -3.0 < meta["flood_threshold"]
        end

        @testset "connected_flood floods only what the sea reaches" begin
            dem = fill(10.0f0, 40, 40)
            dem[1:10, :] .= -5.0f0        # sea, touching the west edge
            dem[11:15, :] .= 1.0f0        # low strip
            dem[31:35, 21:25] .= -3.0f0   # isolated pond

            flooded = connected_flood(dem, SCENARIO_TIDE)

            @test all(flooded[1:10, :])
            @test all(flooded[11:15, :])
            @test !any(flooded[31:35, 21:25])
        end

        @testset "(f) the sea seeds through the edge of the DEM coverage" begin
            # The DGT mosaic is a coastal strip whose seaward limit is a
            # stair-step of 1 km tiles, so for most of the region the sea is
            # inside the window and simply stops where the survey stops.
            # Nothing below water level need touch the edge of the array.
            dem = fill(10.0f0, 40, 40)
            dem[1:15, 2:end-1] .= -5.0f0    # sea...
            dem[16:20, 2:end-1] .= 1.0f0    # ...and the low coast behind it

            # No coverage over the western quarter; the upland first and last
            # rows keep any low ground off the array edge.
            nodata = falses(size(dem))
            nodata[1:10, :] .= true
            dem[nodata] .= 9999.0f0

            without = connected_flood(dem, SCENARIO_TIDE; seed_from_nodata=false)
            @test !any(without)   # edge-only seeding finds nothing: the bug

            flooded = connected_flood(dem, SCENARIO_TIDE; nodata_mask=nodata)
            @test all(flooded[11:15, 2:end-1])   # covered sea
            @test all(flooded[16:20, 2:end-1])   # low coast behind it
            @test !any(flooded[21:end, :])       # upland stays dry
            @test !any(flooded[nodata])          # NoData is unknown, not wet
        end

        @testset "(f) an enclosed NoData hole is not a water source" begin
            # A missing tile inside the coverage is an unknown, not an ocean.
            dem = fill(10.0f0, 40, 40)
            dem[1:10, :] .= -5.0f0            # sea on the west edge
            dem[26:35, 21:30] .= -3.0f0       # closed basin, far inland

            nodata = falses(size(dem))
            nodata[29:32, 23:26] .= true      # a hole punched in the basin
            dem[nodata] .= 9999.0f0

            flooded = connected_flood(dem, SCENARIO_TIDE; nodata_mask=nodata)

            @test all(flooded[1:10, :])
            @test !any(flooded[26:35, 21:30])
        end

        @testset "(b) sea pixels are excluded from the net figure" begin
            sea = mask[1:SEA_END, :]
            @test all(sea .== CLASS_BASELINE)
            @test !any(sea .== CLASS_NEW)

            strip = mask[(SEA_END + 1):STRIP_END, 2:(end - 1)]
            @test all(strip .== CLASS_NEW)

            @test meta["flooded_area_new_km2"] < meta["flooded_area_gross_km2"]
            @test meta["pixels_baseline"] >= SEA_END * (NY - 2)
        end

        @testset "(c) net + baseline <= gross" begin
            total = meta["flooded_area_new_km2"] + meta["baseline_area_km2"]
            @test total <= meta["flooded_area_gross_km2"] + 1e-9
            @test meta["pixels_new"] + meta["pixels_baseline"] == meta["pixels_gross"]
            @test issubset(Set(unique(mask)), Set([CLASS_DRY, CLASS_NEW, CLASS_BASELINE]))
        end

        @testset "areas are in real-world units" begin
            width_m, height_m = meta["pixel_size_m"]
            @test abs(height_m - 11.132) < 0.01
            expected_width = 11.132 * cos(deg2rad(meta["center_latitude"]))
            @test abs(width_m - expected_width) < 0.01

            expected_new = meta["pixels_new"] * width_m * height_m / 1e6
            @test abs(meta["flooded_area_new_km2"] - expected_new) < 1e-9
        end

        @testset "the baseline definition is a parameter" begin
            _, _, low = run_on_synthetic(dem_path; baseline_tide_zh=0.5)
            _, _, high = run_on_synthetic(dem_path; baseline_tide_zh=1.2)

            @test high["baseline_area_km2"] > low["baseline_area_km2"]
            @test high["flooded_area_new_km2"] < low["flooded_area_new_km2"]
            # Gross depends only on the scenario, so it must not move.
            @test abs(high["flooded_area_gross_km2"]
                      - low["flooded_area_gross_km2"]) < 1e-9
        end

        @testset "a polygon baseline works and stays optional" begin
            # A GeoJSON polygon covering exactly the sea columns.
            west = ORIGIN_LON
            east = ORIGIN_LON + SEA_END * PIXEL_DEG
            south = ORIGIN_LAT - NY * PIXEL_DEG
            north = ORIGIN_LAT

            polygon = joinpath(tmp, "water.geojson")
            open(polygon, "w") do f
                write(f, """
                {"type":"FeatureCollection","features":[{"type":"Feature",
                 "properties":{"name":"sea"},
                 "geometry":{"type":"Polygon","coordinates":[[
                   [$west,$south],[$east,$south],[$east,$north],
                   [$west,$north],[$west,$south]]]}}]}
                """)
            end

            poly_result, _, poly_meta = run_on_synthetic(
                dem_path; water_mask_path=polygon)
            poly_mask = UInt8.(Array(poly_result))

            @test startswith(poly_meta["baseline_source"], "polygon:")
            @test all(poly_mask[1:SEA_END, :] .== CLASS_BASELINE)
            @test all(poly_mask[(SEA_END + 1):STRIP_END, 2:(end - 1)] .== CLASS_NEW)

            # And it agrees with the DEM-derived baseline on this geometry.
            @test poly_meta["pixels_baseline"] == meta["pixels_baseline"]
        end

        @testset "(d) HTML files decode as UTF-8" begin
            html_path = joinpath(tmp, "map.html")
            save_html_map(result, html_path, meta)

            raw = read(html_path)
            # String(::Vector{UInt8}) takes ownership of its argument, so copy.
            text = String(copy(raw))

            @test isvalid(String, text)
            @test !occursin('�', text)
            @test occursin("charset=\"utf-8\"", text)
            @test occursin("km²", text)
            @test occursin("×", text)
            @test occursin("→", text)

            # And the bytes really are UTF-8, not cp1252: "km²" is 6b 6d c2 b2.
            @test contains_bytes(raw, UInt8[0x6b, 0x6d, 0xc2, 0xb2])
            # A cp1252 "km²" would be 6b 6d b2, with no lead byte.
            @test !contains_bytes(raw, UInt8[0x6b, 0x6d, 0xb2])
        end

        @testset "(d) HTML in the working tree decodes as UTF-8" begin
            bad = String[]
            checked = 0
            for dir in (".", "tiles_output", "tiles_output_julia")
                isdir(dir) || continue
                for name in sort(readdir(dir))
                    (endswith(name, ".html") && !startswith(name, "._")) || continue
                    checked += 1
                    path = joinpath(dir, name)
                    isvalid(String, String(read(path))) || push!(bad, path)
                end
            end
            @test isempty(bad)
            isempty(bad) || @warn "Not valid UTF-8" bad
            @info "Checked $checked HTML file(s) in the working tree"
        end

        @testset "(e) tile cores tile the region exactly" begin
            bounds = (-8.90, 40.55, -8.60, 41.87)
            tiles = create_tiles(bounds, 0.15, overlap=0.005)

            core_area = sum((t.core[3] - t.core[1]) * (t.core[4] - t.core[2])
                            for t in tiles)
            whole = (bounds[3] - bounds[1]) * (bounds[4] - bounds[2])
            @test abs(core_area - whole) < 1e-9

            for a in tiles, b in tiles
                a.index >= b.index && continue
                overlap_lon = min(a.core[3], b.core[3]) - max(a.core[1], b.core[1])
                overlap_lat = min(a.core[4], b.core[4]) - max(a.core[2], b.core[2])
                @test overlap_lon <= 1e-12 || overlap_lat <= 1e-12
            end

            # Padded extents do overlap, which is what connectivity needs.
            @test any(t.bounds != t.core for t in tiles)

            # No degenerate tile survives, and the indices are contiguous.
            @test all(t.core[3] > t.core[1] && t.core[4] > t.core[2] for t in tiles)
            @test [t.index for t in tiles] == collect(1:length(tiles))
        end

        @testset "(e) the tiled total counts each pixel once" begin
            tiles = create_tiles(SYNTHETIC_BOUNDS, 0.004, overlap=0.0005)
            results, totals = process_tiles(
                dem_path, tiles, SCENARIO_TIDE, 0.0, 0.0;
                output_dir=joinpath(tmp, "tiles"),
                datum_offset=DATUM_OFFSET,
                baseline_tide_zh=BASELINE_TIDE,
                save_individual_maps=false,
                # The synthetic DEM is 160x120 px, so the coarse connectivity
                # pass runs at full resolution here.
                global_seed_downsample=1,
            )

            @test totals["tiles_failed"] == 0

            # Pixel counts are exact: the cores partition the raster.
            @test totals["pixels_new"] + totals["pixels_baseline"] ==
                  meta["pixels_new"] + meta["pixels_baseline"]

            # The pond straddles tile boundaries. Seeding from every tile
            # border would flood it; the coarse global pass must keep it dry.
            @test totals["pixels_baseline"] == meta["pixels_baseline"]

            # Areas agree to better than 1%, the remainder being the latitude
            # used for the degree-to-metre conversion differing per tile.
            @test abs(totals["gross_km2"] - meta["flooded_area_gross_km2"]) <
                  0.01 * meta["flooded_area_gross_km2"]

            # The old, uncropped way really does inflate the total.
            @test totals["naive_gross_km2"] > totals["gross_km2"]
        end

        @testset "crop_to_core selects the core window" begin
            m = fill(CLASS_DRY, 100, 100)
            m[41:60, 41:60] .= CLASS_NEW
            gt = [0.0, 0.01, 0.0, 1.0, 0.0, -0.01]
            bounds = (0.0, 0.0, 1.0, 1.0)

            core = (0.4, 0.4, 0.6, 0.6)
            cropped, gt_core, bounds_core = crop_to_core(m, gt, core)

            @test size(cropped) == (20, 20)
            @test all(cropped .== CLASS_NEW)
            @test all(isapprox.(bounds_core, core; atol=1e-12))

            stats = summarize_mask(cropped, gt_core, bounds_core)
            @test stats["pixels_new"] == 400
            @test summarize_mask(m, gt, bounds)["pixels_new"] == 400
        end
    end
end
