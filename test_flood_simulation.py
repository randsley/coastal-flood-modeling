"""
Tests for the coastal flood simulation (Python implementation).

Runs against a small synthetic DEM so it needs no DGT data:

    (a) a pond not connected to the sea is not flooded;
    (b) sea pixels are excluded from the net figure;
    (c) net + baseline <= gross;
    (d) the generated HTML files decode as UTF-8;
    (e) the tiled total counts each pixel once.

Run with `python test_flood_simulation.py` or `pytest test_flood_simulation.py`.
"""

import os
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from Simul_corrected import (
    CLASS_BASELINE,
    CLASS_DRY,
    CLASS_NEW,
    connected_flood,
    create_tiles,
    crop_to_core,
    process_tiles,
    run_simulation_on_vrt,
    save_html_map,
    summarize_mask,
)

# Scenario used throughout: datum offset 0 keeps thresholds equal to the tide
# values, so the synthetic elevations can be read directly.
DATUM_OFFSET = 0.0
BASELINE_TIDE = 0.5     # present-day water line
SCENARIO_TIDE = 1.5     # scenario water line

# Synthetic DEM layout (rows = latitude, cols = longitude), 120 x 160 px:
#   cols   0..39   sea            -5.0 m   (touches the west edge)
#   cols  40..59   low coast strip  1.0 m  (dry today, floods in the scenario)
#   cols  60..159  upland          10.0 m
#   a pond at -3.0 m sits inside the upland, ringed by 10 m, so it is below
#   both water levels but connected to nothing.
SEA_END = 40
STRIP_END = 60
POND = (slice(70, 90), slice(100, 130))

PIXEL_DEG = 0.0001
ORIGIN_LON = -8.70
ORIGIN_LAT = 41.00


def make_synthetic_dem(path):
    """Write the synthetic DEM to `path` and return the elevation array."""
    height, width = 120, 160
    dem = np.full((height, width), 10.0, dtype=np.float32)
    dem[:, :SEA_END] = -5.0
    dem[:, SEA_END:STRIP_END] = 1.0
    dem[POND] = -3.0

    # Keep the north, south and east edges as upland so the sea is the only
    # thing the flood can be seeded from.
    dem[0, STRIP_END:] = 10.0
    dem[-1, STRIP_END:] = 10.0
    dem[:, -1] = 10.0

    transform = from_origin(ORIGIN_LON, ORIGIN_LAT, PIXEL_DEG, PIXEL_DEG)

    with rasterio.open(
        path, 'w', driver='GTiff', height=height, width=width, count=1,
        dtype='float32', crs='EPSG:4326', transform=transform, nodata=-9999.0,
    ) as dst:
        dst.write(dem, 1)

    return dem


def run_on_synthetic(path, **kwargs):
    bounds = (
        ORIGIN_LON,
        ORIGIN_LAT - 120 * PIXEL_DEG,
        ORIGIN_LON + 160 * PIXEL_DEG,
        ORIGIN_LAT,
    )
    params = dict(
        datum_offset=DATUM_OFFSET,
        baseline_tide_zh=BASELINE_TIDE,
        verbose=False,
    )
    params.update(kwargs)
    return run_simulation_on_vrt(path, SCENARIO_TIDE, 0.0, 0.0, bounds, **params)


# ---------------------------------------------------------------------------
# (a) a pond not connected to the sea is not flooded
# ---------------------------------------------------------------------------

def test_disconnected_pond_is_not_flooded():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "dem.tif")
        make_synthetic_dem(path)
        mask, _, meta = run_on_synthetic(path)

        pond = mask[POND]
        assert np.all(pond == CLASS_DRY), (
            "The pond is below both water levels but is not connected to the "
            f"sea, so it must stay dry; found classes {np.unique(pond)}"
        )

        # A bathtub fill would have flooded it, so prove the test can fail:
        dem_values = np.full(mask.shape, 10.0, dtype=np.float32)
        dem_values[POND] = -3.0
        bathtub = dem_values < meta["flood_threshold"]
        assert bathtub[POND].all(), "sanity check: pond is below the threshold"

    print("PASS (a) disconnected pond is not flooded")


def test_connected_flood_reaches_only_the_coast():
    dem = np.full((40, 40), 10.0, dtype=np.float32)
    dem[:, :10] = -5.0          # sea, touching the west edge
    dem[:, 10:15] = 1.0         # low strip
    dem[20:25, 30:35] = -3.0    # isolated pond

    flooded = connected_flood(dem, SCENARIO_TIDE)

    assert flooded[:, :10].all(), "sea must flood"
    assert flooded[:, 10:15].all(), "low strip must flood at 1.5 m"
    assert not flooded[20:25, 30:35].any(), "isolated pond must not flood"
    print("PASS     connected_flood floods only what the sea reaches")


# ---------------------------------------------------------------------------
# (b) sea pixels are excluded from the net figure
# ---------------------------------------------------------------------------

def test_sea_is_excluded_from_net():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "dem.tif")
        make_synthetic_dem(path)
        mask, _, meta = run_on_synthetic(path)

        sea = mask[:, :SEA_END]
        assert np.all(sea == CLASS_BASELINE), (
            "the sea is already water, so it belongs to the baseline class; "
            f"found {np.unique(sea)}"
        )
        assert not np.any(sea == CLASS_NEW), "no sea pixel may count as new land"

        strip = mask[1:-1, SEA_END:STRIP_END]
        assert np.all(strip == CLASS_NEW), (
            "the 1 m coastal strip is dry at the 0.5 m baseline and wet at the "
            f"1.5 m scenario, so it is new inundation; found {np.unique(strip)}"
        )

        # The net figure must be a small fraction of the gross one here,
        # because the sea dominates the window.
        assert meta["flooded_area_new_km2"] < meta["flooded_area_gross_km2"]
        assert meta["pixels_baseline"] >= SEA_END * 118
    print("PASS (b) sea pixels are excluded from the net figure")


# ---------------------------------------------------------------------------
# (c) net + baseline <= gross
# ---------------------------------------------------------------------------

def test_net_plus_baseline_not_more_than_gross():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "dem.tif")
        make_synthetic_dem(path)
        mask, _, meta = run_on_synthetic(path)

        total = meta["flooded_area_new_km2"] + meta["baseline_area_km2"]
        assert total <= meta["flooded_area_gross_km2"] + 1e-9, (
            f"net ({meta['flooded_area_new_km2']}) + baseline "
            f"({meta['baseline_area_km2']}) exceeds gross "
            f"({meta['flooded_area_gross_km2']})"
        )
        assert meta["pixels_new"] + meta["pixels_baseline"] == meta["pixels_gross"]
        assert set(np.unique(mask)) <= {CLASS_DRY, CLASS_NEW, CLASS_BASELINE}
    print("PASS (c) net + baseline <= gross")


def test_areas_are_in_real_world_units():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "dem.tif")
        make_synthetic_dem(path)
        _, _, meta = run_on_synthetic(path)

        # 0.0001 deg of latitude is 11.132 m; longitude is that times cos(lat).
        width_m, height_m = meta["pixel_size_m"]
        assert abs(height_m - 11.132) < 0.01, height_m
        expected_width = 11.132 * np.cos(np.radians(meta["center_latitude"]))
        assert abs(width_m - expected_width) < 0.01, width_m

        expected_new = meta["pixels_new"] * width_m * height_m / 1e6
        assert abs(meta["flooded_area_new_km2"] - expected_new) < 1e-9
    print("PASS     areas are computed in m² / km², not deg²")


def write_water_polygon(path):
    """A GeoJSON polygon covering the sea columns of the synthetic DEM."""
    import json

    west = ORIGIN_LON
    east = ORIGIN_LON + SEA_END * PIXEL_DEG
    south = ORIGIN_LAT - 120 * PIXEL_DEG
    north = ORIGIN_LAT

    with open(path, 'w', encoding='utf-8') as f:
        json.dump({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"name": "sea"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [west, south], [east, south],
                        [east, north], [west, north], [west, south],
                    ]],
                },
            }],
        }, f)
    return path


def test_polygon_baseline_is_optional_and_works():
    """A land/water polygon may replace the DEM-derived baseline."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "dem.tif")
        make_synthetic_dem(path)
        polygon = write_water_polygon(os.path.join(tmp, "water.geojson"))

        mask, _, meta = run_on_synthetic(path, water_mask_path=polygon)

        assert meta["baseline_source"].startswith("polygon:")
        # The polygon covers exactly the sea columns.
        assert np.all(mask[:, :SEA_END] == CLASS_BASELINE)
        assert np.all(mask[1:-1, SEA_END:STRIP_END] == CLASS_NEW)
        assert meta["pixels_new"] + meta["pixels_baseline"] == meta["pixels_gross"]

        # And it agrees with the DEM-derived baseline on this geometry.
        _, _, dem_based = run_on_synthetic(path)
        assert meta["pixels_baseline"] == dem_based["pixels_baseline"]
    print("PASS     polygon baseline works and stays optional")


def test_baseline_parameter_changes_the_split():
    """The baseline definition is a parameter, and raising it moves land from
    the net figure into the baseline."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "dem.tif")
        make_synthetic_dem(path)

        _, _, low = run_on_synthetic(path, baseline_tide_zh=0.5)
        _, _, high = run_on_synthetic(path, baseline_tide_zh=1.2)

        assert high["baseline_area_km2"] > low["baseline_area_km2"]
        assert high["flooded_area_new_km2"] < low["flooded_area_new_km2"]
        # Gross depends only on the scenario, so it must not move.
        assert abs(high["flooded_area_gross_km2"]
                   - low["flooded_area_gross_km2"]) < 1e-9
    print("PASS     baseline definition is a parameter")


# ---------------------------------------------------------------------------
# (d) the HTML files decode as UTF-8
# ---------------------------------------------------------------------------

def test_html_is_utf8():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "dem.tif")
        make_synthetic_dem(path)
        mask, _, meta = run_on_synthetic(path)

        html_path = os.path.join(tmp, "map.html")
        save_html_map(mask, meta, html_path)

        raw = open(html_path, 'rb').read()
        text = raw.decode('utf-8')          # raises if it is not valid UTF-8

        assert '�' not in text, "replacement characters in the HTML"
        assert 'charset="utf-8"' in text
        assert 'km²' in text, "the squared sign must survive the round trip"
        assert '×' in text, "the multiplication sign must survive the round trip"
        assert '→' in text

        # And the bytes really are UTF-8, not cp1252: 'km²' is 6b 6d c2 b2.
        assert b'km\xc2\xb2' in raw
        assert b'km\xb2' not in raw.replace(b'km\xc2\xb2', b'')
    print("PASS (d) HTML files decode as UTF-8")


def test_repository_html_is_utf8():
    """Any HTML already in the working tree must decode as UTF-8 too."""
    checked = 0
    bad = []
    for directory in ('.', 'tiles_output'):
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.endswith('.html') or name.startswith('._'):
                continue
            path = os.path.join(directory, name)
            checked += 1
            try:
                open(path, 'rb').read().decode('utf-8')
            except UnicodeDecodeError as e:
                bad.append(f"{path}: {e}")
    assert not bad, "HTML files that are not valid UTF-8:\n" + "\n".join(bad)
    print(f"PASS (d) {checked} HTML file(s) in the working tree decode as UTF-8")


# ---------------------------------------------------------------------------
# (e) the tiled total counts each pixel once
# ---------------------------------------------------------------------------

def test_tiles_cover_the_region_without_overlap():
    bounds = (-8.90, 40.55, -8.60, 41.87)
    tiles = create_tiles(bounds, 0.15, overlap=0.005)

    # Cores tile the region exactly: their areas sum to the whole box.
    core_area = sum((t.core[2] - t.core[0]) * (t.core[3] - t.core[1])
                    for t in tiles)
    whole = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
    assert abs(core_area - whole) < 1e-9, (core_area, whole)

    # Cores do not overlap each other.
    for a in tiles:
        for b in tiles:
            if a.index >= b.index:
                continue
            overlap_lon = min(a.core[2], b.core[2]) - max(a.core[0], b.core[0])
            overlap_lat = min(a.core[3], b.core[3]) - max(a.core[1], b.core[1])
            assert overlap_lon <= 1e-12 or overlap_lat <= 1e-12, (
                f"cores of tiles {a.index} and {b.index} overlap"
            )

    # Padded extents do overlap, which is what connectivity needs.
    assert any(t.bounds != t.core for t in tiles)

    # No degenerate tile survives, and the indices are contiguous.
    for t in tiles:
        assert t.core[2] > t.core[0] and t.core[3] > t.core[1], t
    assert [t.index for t in tiles] == list(range(1, len(tiles) + 1))
    print("PASS (e) tile cores tile the region exactly, padded extents overlap")


def test_tiled_total_matches_single_pass():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "dem.tif")
        make_synthetic_dem(path)

        bounds = (
            ORIGIN_LON,
            ORIGIN_LAT - 120 * PIXEL_DEG,
            ORIGIN_LON + 160 * PIXEL_DEG,
            ORIGIN_LAT,
        )

        single_mask, _, single = run_on_synthetic(path)

        tiles = create_tiles(bounds, 0.004, overlap=0.0005)
        results, totals = process_tiles(
            path, tiles, SCENARIO_TIDE, 0.0, 0.0,
            output_dir=os.path.join(tmp, "tiles"),
            datum_offset=DATUM_OFFSET,
            baseline_tide_zh=BASELINE_TIDE,
            save_individual_maps=False,
            # The synthetic DEM is 120x160 px, so the coarse connectivity pass
            # runs at full resolution here.
            global_seed_downsample=1,
        )

        assert totals["tiles_failed"] == 0, "every tile must process"

        # The pond straddles tile boundaries. Seeding from every tile border
        # would flood it; the coarse global pass must keep it dry.
        for mask_core, meta_core, tile in results:
            assert mask_core is not None
        assert totals["pixels_baseline"] == single["pixels_baseline"], (
            "a closed basin cut by a tile edge must not be flooded from that "
            f"edge: tiled baseline {totals['pixels_baseline']} vs single "
            f"{single['pixels_baseline']}"
        )

        # Pixel counts are exact: the cores partition the raster.
        assert totals["pixels_new"] + totals["pixels_baseline"] == \
            single["pixels_new"] + single["pixels_baseline"], (
                f"tiled {totals['pixels_new']}+{totals['pixels_baseline']} vs "
                f"single {single['pixels_new']}+{single['pixels_baseline']}"
            )

        # Areas agree to better than 1%, the remainder being the latitude used
        # for the degree-to-metre conversion differing per tile.
        assert abs(totals["gross_km2"] - single["flooded_area_gross_km2"]) \
            < 0.01 * single["flooded_area_gross_km2"]

        # The old, uncropped way really does inflate the total.
        assert totals["naive_gross_km2"] > totals["gross_km2"], (
            "summing the padded tiles should over-count the overlap strips"
        )
    print("PASS (e) tiled total counts each pixel once")


def test_crop_to_core_selects_the_right_window():
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[40:60, 40:60] = CLASS_NEW
    transform = from_origin(0.0, 1.0, 0.01, 0.01)
    bounds = (0.0, 0.0, 1.0, 1.0)

    core = (0.4, 0.4, 0.6, 0.6)
    cropped, cropped_transform, cropped_bounds, _ = crop_to_core(
        mask, transform, core
    )

    assert cropped.shape == (20, 20), cropped.shape
    assert np.all(cropped == CLASS_NEW)
    assert np.allclose(cropped_bounds, core)

    stats = summarize_mask(cropped, cropped_transform, cropped_bounds)
    assert stats["pixels_new"] == 400
    assert summarize_mask(mask, transform, bounds)["pixels_new"] == 400
    print("PASS     crop_to_core selects the core window")


# ---------------------------------------------------------------------------
# (f) seeding across the edge of the DEM coverage
# ---------------------------------------------------------------------------

def test_sea_seeds_through_the_coverage_boundary():
    """
    The DGT mosaic is a coastal strip whose seaward limit is a stair-step of
    1 km tiles, so for most of the region the sea is *inside* the window and
    simply stops where the survey stops. Nothing below water level need touch
    the edge of the array at all.
    """
    dem = np.full((40, 40), 10.0, dtype=np.float32)
    dem[1:-1, :15] = -5.0       # sea...
    dem[1:-1, 15:20] = 1.0      # ...and the low coast behind it

    # No coverage over the western quarter: the sea now ends at NoData, and the
    # upland rows north and south mean no low ground touches any array edge.
    nodata = np.zeros(dem.shape, dtype=bool)
    nodata[:, :10] = True
    dem[nodata] = 9999.0

    without = connected_flood(dem, SCENARIO_TIDE, seed_from_nodata=False)
    assert not without.any(), (
        "edge-only seeding should find nothing here - that is the bug this "
        "guards against"
    )

    flooded = connected_flood(dem, SCENARIO_TIDE, nodata)
    assert flooded[1:-1, 10:15].all(), "covered sea must flood"
    assert flooded[1:-1, 15:20].all(), "the low coast behind it must flood"
    assert not flooded[:, 20:].any(), "upland must stay dry"
    assert not flooded[nodata].any(), "NoData is not flooded, it is unknown"
    print("PASS (f) sea seeds through the edge of the DEM coverage")


def test_enclosed_nodata_hole_does_not_seed():
    """
    A missing tile *inside* the coverage is an unknown, not an ocean. Seeding
    from it would flood whatever closed basin it happens to sit in.
    """
    dem = np.full((40, 40), 10.0, dtype=np.float32)
    dem[:, :10] = -5.0              # sea on the west edge
    basin = (slice(20, 30), slice(25, 35))
    dem[basin] = -3.0               # closed basin, far inland

    nodata = np.zeros(dem.shape, dtype=bool)
    nodata[22:26, 28:32] = True     # a hole punched in the middle of it
    dem[nodata] = 9999.0

    flooded = connected_flood(dem, SCENARIO_TIDE, nodata)

    assert flooded[:, :10].all(), "sea must still flood"
    assert not flooded[basin].any(), (
        "an enclosed NoData hole must not act as a water source; "
        f"{flooded[basin].sum()} basin pixels flooded"
    )
    print("PASS (f) an enclosed NoData hole is not a water source")


TESTS = [
    test_disconnected_pond_is_not_flooded,
    test_connected_flood_reaches_only_the_coast,
    test_sea_seeds_through_the_coverage_boundary,
    test_enclosed_nodata_hole_does_not_seed,
    test_sea_is_excluded_from_net,
    test_net_plus_baseline_not_more_than_gross,
    test_areas_are_in_real_world_units,
    test_baseline_parameter_changes_the_split,
    test_polygon_baseline_is_optional_and_works,
    test_html_is_utf8,
    test_repository_html_is_utf8,
    test_tiles_cover_the_region_without_overlap,
    test_tiled_total_matches_single_pass,
    test_crop_to_core_selects_the_right_window,
]


if __name__ == "__main__":
    import sys
    import io
    import contextlib

    failures = 0
    for test in TESTS:
        # The simulation functions are chatty; keep the test output readable.
        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(captured):
                test()
            print(captured.getvalue().strip().splitlines()[-1])
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {test.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {test.__name__}: {type(e).__name__}: {e}")

    print()
    if failures:
        print(f"{failures} of {len(TESTS)} tests failed")
        sys.exit(1)
    print(f"All {len(TESTS)} tests passed")
