"""
Coastal flood simulation for Portuguese coastal zones (Python implementation).

Connected morphological flooding on DGT high-resolution DEMs, with a
present-day baseline water mask so that the headline figure is *newly
inundated land* rather than "every pixel below the water level", which
includes the sea itself.

Output classes (see CLASS_* constants):
    0  dry land
    1  newly inundated land   <- the headline figure
    2  baseline water (sea, estuaries, permanent water bodies)

gross = (mask > 0), net = (mask == 1), baseline = (mask == 2).
"""

import os
import base64
from collections import namedtuple
from datetime import datetime
from io import BytesIO

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.windows import Window, from_bounds
from rasterio.windows import bounds as window_bounds
from skimage.morphology import reconstruction

# Optional: PIL for pixel-perfect HTML maps
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL not available. Install with: pip install Pillow")
    print("  → HTML maps will use rectangle approximation")


# --- Output classes -------------------------------------------------------
CLASS_DRY = 0
CLASS_NEW = 1
CLASS_BASELINE = 2

# Elevation used to stand in for NoData so it can never be flooded.
NODATA_FILL = 9999.0

# Portugal has no land below this elevation; anything lower is bad data.
MIN_PLAUSIBLE_ELEVATION = -100.0

#: Metres per degree of latitude (and of longitude at the equator).
METERS_PER_DEG_LAT = 111320.0

Tile = namedtuple("Tile", "index bounds core")
Tile.__doc__ = """A tile of a large region.

bounds : tuple
    Padded extent the simulation is *computed* on. The padding (overlap with
    the neighbouring tiles) exists so flooding can propagate across tile
    boundaries.
core : tuple
    Nominal, non-overlapping extent. Outputs are cropped to this and areas are
    only counted here, so no pixel is counted twice in the regional total.
"""


# ============================================================================
# LOW-LEVEL HELPERS
# ============================================================================

def read_dem_window(vrt_path, bounds, downsample=1):
    """
    Read a DEM subset, optionally decimated, and clean its NoData.

    Parameters
    ----------
    vrt_path : str
        Path to the VRT (or any GDAL-readable raster).
    bounds : tuple
        (min_lon, min_lat, max_lon, max_lat). Clipped to the raster extent.
    downsample : int, optional
        Integer decimation factor. 1 reads at native resolution; 4 reads every
        4th pixel (GDAL nearest-neighbour), which is how large regions are kept
        within RAM. The Julia implementation issues the identical GDAL call, so
        both read exactly the same pixels.

    Returns
    -------
    dem : numpy.ndarray (float32)
        Elevation with NoData replaced by NODATA_FILL.
    nodata_mask : numpy.ndarray (bool)
        True where the source had no data.
    transform : rasterio.Affine
        Transform of the returned array.
    bounds_read : tuple
        The extent actually read, which may be smaller than `bounds` where the
        request falls outside the raster. Use this (not the request) to place
        image overlays, or they will be stretched into the wrong position.
    crs : rasterio.crs.CRS
    """
    downsample = max(1, int(downsample))

    with rasterio.open(vrt_path) as src:
        win = from_bounds(*bounds, transform=src.transform)

        # Snap outwards to whole pixels, then clip to the raster.
        col_off = max(0, int(np.floor(win.col_off)))
        row_off = max(0, int(np.floor(win.row_off)))
        col_end = min(src.width, int(np.ceil(win.col_off + win.width)))
        row_end = min(src.height, int(np.ceil(win.row_off + win.height)))

        if col_end <= col_off or row_end <= row_off:
            raise ValueError(
                f"Requested bounds {bounds} do not overlap the raster extent "
                f"{tuple(src.bounds)}"
            )

        # Trim to a whole multiple of `downsample` so the output pixel size is
        # exactly downsample x the source pixel size.
        width = col_end - col_off
        height = row_end - row_off
        if downsample > 1:
            width = max(downsample, (width // downsample) * downsample)
            height = max(downsample, (height // downsample) * downsample)
            width = min(width, src.width - col_off)
            height = min(height, src.height - row_off)

        win = Window(col_off, row_off, width, height)
        out_w = max(1, width // downsample)
        out_h = max(1, height // downsample)

        arr = src.read(
            1,
            window=win,
            out_shape=(out_h, out_w),
            resampling=Resampling.nearest,
        )

        transform = src.window_transform(win) * Affine.scale(
            width / out_w, height / out_h
        )
        bounds_read = tuple(window_bounds(win, src.transform))
        nodata_value = src.nodata if src.nodata is not None else -9999.0
        crs = src.crs

    arr = arr.astype(np.float32, copy=False)
    nodata_mask = np.isnan(arr) | (arr == nodata_value) | (arr < MIN_PLAUSIBLE_ELEVATION)
    dem = np.where(nodata_mask, np.float32(NODATA_FILL), arr)

    return dem, nodata_mask, transform, bounds_read, crs


def exterior_nodata_mask(nodata_mask):
    """
    The NoData that lies *outside* the DEM's coverage, as opposed to enclosed
    holes within it.

    NoData touching the edge of the array is taken to be outside the surveyed
    area. NoData that does not touch the edge is an enclosed hole — a missing
    DGT tile surrounded by present ones — and is not outside anything.

    Parameters
    ----------
    nodata_mask : numpy.ndarray (bool)

    Returns
    -------
    numpy.ndarray (bool)
    """
    from scipy import ndimage

    if not nodata_mask.any():
        return np.zeros_like(nodata_mask)

    labels, n = ndimage.label(nodata_mask)
    if n == 0:
        return np.zeros_like(nodata_mask)

    edge_labels = np.unique(np.concatenate([
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1],
    ]))
    edge_labels = edge_labels[edge_labels != 0]

    if edge_labels.size == 0:
        return np.zeros_like(nodata_mask)

    return np.isin(labels, edge_labels)


def flood_sources(dem, threshold, nodata_mask=None, border_allowed=None,
                  seed_from_nodata=True):
    """
    Where water may enter the window.

    Two kinds of source, both of which must be below `threshold`:

    * **the edge of the array** — the usual "ocean is off the side of the map"
      assumption;
    * **ground that meets the outside of the DEM coverage** — the DGT mosaic is
      a coastal strip with a stair-stepped seaward limit, so for most of the
      region the sea is *inside* the window and simply stops where the survey
      stops. Without this, a window whose edges happen to miss covered water
      seeds nothing at all and the whole region comes back dry.

    Enclosed NoData (a missing tile surrounded by present ones) is not a
    source: nothing is known to connect through it.

    Parameters
    ----------
    dem : numpy.ndarray
    threshold : float
    nodata_mask : numpy.ndarray, optional
    border_allowed : numpy.ndarray, optional
        Restricts the *array edge* sources only; see `connected_flood`. The
        coverage-boundary sources are physical and are never restricted, since
        they do not depend on where the window was drawn.
    seed_from_nodata : bool, optional

    Returns
    -------
    numpy.ndarray (bool)
    """
    below = dem < threshold
    sources = np.zeros_like(below)

    # 1. The edge of the array.
    sources[0, :] = below[0, :]
    sources[-1, :] = below[-1, :]
    sources[:, 0] = below[:, 0]
    sources[:, -1] = below[:, -1]

    if border_allowed is not None:
        if border_allowed.shape != dem.shape:
            raise ValueError("border_allowed must have the same shape as dem")
        sources &= border_allowed

    # 2. Low ground meeting the outside of the DEM coverage.
    if seed_from_nodata and nodata_mask is not None and nodata_mask.any():
        exterior = exterior_nodata_mask(nodata_mask)
        if exterior.any():
            sources |= below & _dilate_one_pixel(exterior) & ~nodata_mask

    return sources


def connected_flood(dem, threshold, nodata_mask=None, border_allowed=None,
                    seed_from_nodata=True):
    """
    Connected morphological flooding: which pixels below `threshold` are
    hydrologically connected to a water source.

    Isolated depressions below the threshold stay dry, which is the whole point
    of using reconstruction rather than a bathtub fill.

    Parameters
    ----------
    dem : numpy.ndarray
        Elevation, NoData already replaced by a high value.
    threshold : float
        Water level in the DEM's vertical datum (NMM for DGT data).
    nodata_mask : numpy.ndarray, optional
        Where the source had no data. Used to find the coverage boundary; see
        `flood_sources`.
    border_allowed : numpy.ndarray, optional
        Boolean array the shape of `dem`. When given, only array-edge pixels
        where it is True may act as a water source. This matters when `dem` is
        a tile of a larger region: the tile's interior edges are not really
        coastline, and seeding from them floods any closed depression they
        happen to cut through.
    seed_from_nodata : bool, optional
        Set False to use the edge of the array as the only water source.

    Returns
    -------
    numpy.ndarray (bool)
    """
    if dem.ndim != 2 or min(dem.shape) < 3:
        raise ValueError("DEM must be 2D and at least 3x3 pixels")

    sources = flood_sources(dem, threshold, nodata_mask, border_allowed,
                            seed_from_nodata)

    # Marker: water level at the sources, maximum elevation everywhere else, so
    # the reconstruction can only erode down through a connected path. Ground
    # at or above the threshold keeps its own elevation and acts as a wall.
    max_val = dem.max()
    seed = np.full(dem.shape, max_val, dtype=dem.dtype)
    seed[sources] = dem[sources]
    seed = np.where(dem < threshold, seed, dem)

    flooded_surface = reconstruction(seed, dem, method='erosion')
    return flooded_surface < threshold


class GlobalSeedMask:
    """
    Coarse whole-region connectivity, used to decide where a tile's border may
    let water in.

    A tile's border is mostly an artefact of tiling, not coastline. Seeding
    from all of it floods every closed basin the border cuts through — around
    Aveiro that means salt pans and drainage basins. This runs one cheap
    connected-flooding pass over the *entire* region at a coarse resolution and
    uses it to allow seeding only where water really does reach.

    The coarse masks are dilated by one coarse pixel so that a connection
    narrower than the coarse grid is not lost.
    """

    def __init__(self, scenario, baseline, transform, bounds, downsample):
        self.scenario = scenario
        self.baseline = baseline
        self.transform = transform
        self.bounds = bounds
        self.downsample = downsample

    def border_allowed(self, which, transform, shape):
        """
        Boolean array of `shape` whose border ring marks the pixels that may
        act as a water source. The interior is left False; it is never read.
        """
        coarse = self.scenario if which == 'scenario' else self.baseline
        height, width = shape
        coarse_h, coarse_w = coarse.shape

        lons = transform.c + (np.arange(width) + 0.5) * transform.a
        lats = transform.f + (np.arange(height) + 0.5) * transform.e

        cols = np.clip(
            np.round((lons - self.transform.c) / self.transform.a - 0.5
                     ).astype(np.int64), 0, coarse_w - 1)
        rows = np.clip(
            np.round((lats - self.transform.f) / self.transform.e - 0.5
                     ).astype(np.int64), 0, coarse_h - 1)

        allowed = np.zeros(shape, dtype=bool)
        allowed[0, :] = coarse[rows[0], cols]
        allowed[-1, :] = coarse[rows[-1], cols]
        allowed[:, 0] = coarse[rows, cols[0]]
        allowed[:, -1] = coarse[rows, cols[-1]]
        return allowed


def _dilate_one_pixel(mask):
    """Grow a boolean mask by one pixel in all 8 directions (3x3 box)."""
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    shifted = out.copy()
    out[:, 1:] |= shifted[:, :-1]
    out[:, :-1] |= shifted[:, 1:]
    return out


def build_global_seed_mask(vrt_path, bounds, flood_threshold, baseline_threshold,
                           downsample=16, verbose=True):
    """
    Run the coarse whole-region connectivity pass behind `GlobalSeedMask`.

    Parameters
    ----------
    vrt_path : str
    bounds : tuple
        The whole region, not a tile.
    flood_threshold, baseline_threshold : float
        Thresholds in the DEM datum (NMM).
    downsample : int, optional
        Decimation for the coarse pass (default 16). At 50 cm source data that
        is an 8 m grid, which costs seconds for a 150 km coastline.
    verbose : bool, optional

    Returns
    -------
    GlobalSeedMask
    """
    if verbose:
        print(f"Coarse whole-region connectivity pass (downsample={downsample})...")

    dem, nodata_mask, transform, bounds_read, _ = read_dem_window(
        vrt_path, bounds, downsample=downsample
    )

    if verbose:
        print(f"  Coarse grid: {dem.shape[1]} x {dem.shape[0]} px, "
              f"{nodata_mask.mean() * 100:.1f}% NoData")

    scenario = _dilate_one_pixel(
        connected_flood(dem, flood_threshold, nodata_mask))
    baseline = _dilate_one_pixel(
        connected_flood(dem, baseline_threshold, nodata_mask))

    if verbose:
        print(f"  Coarse connected fraction: scenario {scenario.mean() * 100:.1f}%, "
              f"baseline {baseline.mean() * 100:.1f}%")

    return GlobalSeedMask(scenario, baseline, transform, bounds_read, downsample)


def compute_thresholds(tide_zh, surge, slr, datum_offset=2.00,
                       baseline_tide_zh=None, baseline_surge=0.0,
                       baseline_slr=0.0):
    """
    Scenario and baseline water levels and thresholds.

    The baseline defaults to today's highest astronomical tide: the same tide,
    with no surge and no sea-level rise.

    Returns
    -------
    dict with total_water_level, flood_threshold, baseline_water_level,
    baseline_threshold and the inputs used.
    """
    if baseline_tide_zh is None:
        baseline_tide_zh = tide_zh

    total_water_level = tide_zh + surge + slr
    baseline_water_level = baseline_tide_zh + baseline_surge + baseline_slr

    flood_threshold = total_water_level - datum_offset
    baseline_threshold = baseline_water_level - datum_offset

    if flood_threshold < baseline_threshold:
        raise ValueError(
            f"Scenario threshold ({flood_threshold:.2f} m) is below the baseline "
            f"threshold ({baseline_threshold:.2f} m); the scenario must be at "
            "least as high as present-day water."
        )

    return {
        "tide_zh": tide_zh,
        "surge": surge,
        "slr": slr,
        "datum_offset": datum_offset,
        "total_water_level": total_water_level,
        "flood_threshold": flood_threshold,
        "baseline_tide_zh": baseline_tide_zh,
        "baseline_surge": baseline_surge,
        "baseline_slr": baseline_slr,
        "baseline_water_level": baseline_water_level,
        "baseline_threshold": baseline_threshold,
    }


def load_water_polygons(path):
    """
    Read polygon geometries from a vector file.

    GeoJSON is read with the standard library, so it needs nothing extra. Other
    formats (GeoPackage, shapefile) try geopandas, then fiona, then the
    GDAL/OGR bindings, and raise with an actionable message if none is
    installed. Only needed when a land/water polygon is supplied, which is
    always optional.
    """
    if path.lower().endswith(('.geojson', '.json')):
        import json
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        kind = data.get("type")
        if kind == "FeatureCollection":
            return [feat["geometry"] for feat in data.get("features", [])
                    if feat.get("geometry") is not None]
        if kind == "Feature":
            return [data["geometry"]] if data.get("geometry") else []
        if kind in ("Polygon", "MultiPolygon", "GeometryCollection"):
            return [data]
        raise ValueError(f"Unsupported GeoJSON type {kind!r} in {path}")

    try:
        import geopandas as gpd
        return [geom.__geo_interface__ for geom in gpd.read_file(path).geometry
                if geom is not None]
    except ImportError:
        pass

    try:
        import fiona
        with fiona.open(path) as layer:
            return [feat["geometry"] for feat in layer
                    if feat["geometry"] is not None]
    except ImportError:
        pass

    try:
        from osgeo import ogr
        import json
        ds = ogr.Open(path)
        if ds is None:
            raise ValueError(f"Could not open vector file: {path}")
        geoms = []
        for i in range(ds.GetLayerCount()):
            layer = ds.GetLayer(i)
            for feature in layer:
                geom = feature.GetGeometryRef()
                if geom is not None:
                    geoms.append(json.loads(geom.ExportToJson()))
        return geoms
    except ImportError:
        pass

    raise ImportError(
        f"Reading {os.path.basename(path)} needs one of geopandas, fiona or "
        "the GDAL Python bindings. Install one (e.g. pip install fiona), "
        "convert the layer to GeoJSON (which needs nothing extra), or omit "
        "water_mask_path to derive the baseline from the DEM instead."
    )


def baseline_from_polygon(path, shape, transform, polygon_is_land=False):
    """
    Rasterise a land/water polygon into a baseline water mask.

    Parameters
    ----------
    path : str
        GeoPackage or shapefile.
    shape : tuple
        (height, width) of the target grid.
    transform : rasterio.Affine
    polygon_is_land : bool, optional
        Set True when the polygon delineates *land*; the baseline water mask is
        then its complement.

    Returns
    -------
    numpy.ndarray (bool)
    """
    from rasterio.features import rasterize

    geoms = load_water_polygons(path)
    if not geoms:
        raise ValueError(f"No geometries found in {path}")

    burned = rasterize(
        [(geom, 1) for geom in geoms],
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype='uint8',
        all_touched=False,
    ).astype(bool)

    return ~burned if polygon_is_land else burned


def pixel_dimensions_m(transform, center_lat):
    """
    Pixel size in metres for a raster in geographic coordinates.

    1 degree of latitude is ~111,320 m; 1 degree of longitude is that times
    cos(latitude). Returns (width_m, height_m, area_m2).
    """
    x_step_deg = abs(transform[0])
    y_step_deg = abs(transform[4])

    meters_per_deg_lon = METERS_PER_DEG_LAT * np.cos(np.radians(center_lat))

    width_m = x_step_deg * meters_per_deg_lon
    height_m = y_step_deg * METERS_PER_DEG_LAT
    return width_m, height_m, width_m * height_m


def summarize_mask(mask, transform, bounds, nodata_mask=None):
    """
    Area statistics for a classified flood mask.

    Parameters
    ----------
    mask : numpy.ndarray (uint8)
        Values CLASS_DRY / CLASS_NEW / CLASS_BASELINE.
    transform : rasterio.Affine
    bounds : tuple
        Extent of `mask`, used for the latitude-dependent area conversion.
    nodata_mask : numpy.ndarray, optional

    Returns
    -------
    dict
    """
    center_lat = (bounds[1] + bounds[3]) / 2
    width_m, height_m, pixel_area_m2 = pixel_dimensions_m(transform, center_lat)

    pixels_new = int(np.count_nonzero(mask == CLASS_NEW))
    pixels_baseline = int(np.count_nonzero(mask == CLASS_BASELINE))
    pixels_gross = pixels_new + pixels_baseline

    stats = {
        "pixels_total": int(mask.size),
        "pixels_new": pixels_new,
        "pixels_baseline": pixels_baseline,
        "pixels_gross": pixels_gross,
        "flooded_area_new_m2": pixels_new * pixel_area_m2,
        "flooded_area_new_km2": pixels_new * pixel_area_m2 / 1_000_000,
        "baseline_area_m2": pixels_baseline * pixel_area_m2,
        "baseline_area_km2": pixels_baseline * pixel_area_m2 / 1_000_000,
        "flooded_area_gross_m2": pixels_gross * pixel_area_m2,
        "flooded_area_gross_km2": pixels_gross * pixel_area_m2 / 1_000_000,
        "pixel_area_m2": pixel_area_m2,
        "pixel_size_m": (width_m, height_m),
        "center_latitude": center_lat,
        "bounds": tuple(bounds),
    }

    if nodata_mask is not None:
        stats["nodata_pixels"] = int(np.count_nonzero(nodata_mask))
        stats["nodata_fraction"] = float(np.mean(nodata_mask))

    return stats


# ============================================================================
# SIMULATION
# ============================================================================

def run_simulation_on_vrt(vrt_path, tide_zh, surge, slr, bounds,
                          datum_offset=2.00,
                          baseline_tide_zh=None,
                          baseline_surge=0.0,
                          baseline_slr=0.0,
                          water_mask_path=None,
                          water_polygon_is_land=False,
                          downsample=1,
                          global_seed=None,
                          verbose=True):
    """
    Run a coastal flood simulation and separate new inundation from water that
    is already there.

    Two connected-flooding passes are run over the same DEM:

    * the *scenario* pass at ``(tide_zh + surge + slr) - datum_offset``;
    * the *baseline* pass at ``baseline_tide_zh - datum_offset``, which by
      default is today's highest astronomical tide with no surge and no
      sea-level rise.

    Newly inundated land is scenario AND NOT baseline. Without this the sea and
    the Ria de Aveiro are inside the DEM's coverage and get counted as
    "flooded", which inflates the figure by an order of magnitude.

    Parameters
    ----------
    vrt_path : str
        Path to the VRT, e.g. 'portugal_coast_wgs84.vrt'.
    tide_zh : float
        Tide level relative to Hydrographic Zero (ZH), in metres.
    surge : float
        Storm surge height in metres.
    slr : float
        Sea level rise scenario in metres.
    bounds : tuple
        (min_lon, min_lat, max_lon, max_lat).
    datum_offset : float, optional
        ZH to NMM offset (default 2.00 m for the Viana/Aveiro zone).
    baseline_tide_zh : float, optional
        Tide level (ZH) defining present-day water. Defaults to `tide_zh`,
        i.e. today's HAT.
    baseline_surge, baseline_slr : float, optional
        Normally 0.0: the baseline is an astronomical tide, not a storm.
    water_mask_path : str, optional
        GeoPackage/shapefile to use as the baseline instead of the DEM-derived
        mask. Optional; no polygon is required.
    water_polygon_is_land : bool, optional
        True if `water_mask_path` delineates land rather than water.
    downsample : int, optional
        Integer decimation factor applied when reading (default 1 = native).
    global_seed : GlobalSeedMask, optional
        Coarse whole-region connectivity restricting where this window's border
        may let water in. Pass this when `bounds` is a tile of a larger region;
        without it the tile's artificial edges flood closed basins they cut
        through. `process_tiles` builds and passes it for you.
    verbose : bool, optional

    Returns
    -------
    flood_mask : numpy.ndarray (uint8)
        Classified: 0 dry, 1 newly inundated land, 2 baseline water.
    transform : rasterio.Affine
    metadata : dict
        Includes `flooded_area_new_km2` (headline), `flooded_area_gross_km2`
        and `baseline_area_km2`.

    Example
    -------
    >>> mask, transform, meta = run_simulation_on_vrt(
    ...     "portugal_coast_wgs84.vrt",
    ...     3.8,   # HAT
    ...     0.6,   # 50-year surge
    ...     1.13,  # 2100 SLR
    ...     (-8.70, 40.95, -8.60, 41.03),
    ... )
    >>> meta["flooded_area_new_km2"]        # doctest: +SKIP
    """
    levels = compute_thresholds(
        tide_zh, surge, slr, datum_offset,
        baseline_tide_zh, baseline_surge, baseline_slr,
    )
    baseline_tide_zh = levels["baseline_tide_zh"]
    total_water_level = levels["total_water_level"]
    flood_threshold = levels["flood_threshold"]
    baseline_water_level = levels["baseline_water_level"]
    baseline_threshold = levels["baseline_threshold"]

    if verbose:
        print(f"Scenario TWL: {total_water_level:.2f}m (ZH) -> "
              f"threshold {flood_threshold:.2f}m (NMM)")
        print(f"Baseline TWL: {baseline_water_level:.2f}m (ZH) -> "
              f"threshold {baseline_threshold:.2f}m (NMM)")

    # --- 1. LOAD & CLIP DATA -------------------------------------------
    dem, nodata_mask, transform, bounds_read, crs = read_dem_window(
        vrt_path, bounds, downsample=downsample
    )

    if verbose:
        print(f"DEM window: {dem.shape[1]} x {dem.shape[0]} px "
              f"(downsample={downsample}), "
              f"{np.mean(nodata_mask) * 100:.1f}% NoData")

    # --- 2. SCENARIO FLOODING ------------------------------------------
    if global_seed is None:
        scenario_border = None
        baseline_border = None
    else:
        scenario_border = global_seed.border_allowed(
            'scenario', transform, dem.shape)
        baseline_border = global_seed.border_allowed(
            'baseline', transform, dem.shape)

    if verbose:
        print("Calculating hydrological connectivity (scenario)...")
    scenario = connected_flood(dem, flood_threshold, nodata_mask,
                               scenario_border)

    # --- 3. BASELINE WATER ---------------------------------------------
    if water_mask_path:
        if verbose:
            print(f"Baseline water from polygon: {water_mask_path}")
        baseline = baseline_from_polygon(
            water_mask_path, dem.shape, transform,
            polygon_is_land=water_polygon_is_land,
        )
        baseline_source = f"polygon:{os.path.basename(water_mask_path)}"
    else:
        if verbose:
            print("Calculating hydrological connectivity (baseline)...")
        baseline = connected_flood(dem, baseline_threshold, nodata_mask,
                                   baseline_border)
        baseline_source = "morphological"

    # --- 4. CLASSIFY ----------------------------------------------------
    # Baseline wins over scenario: a pixel that is water today is baseline
    # water, not new inundation. With a morphological baseline the baseline is
    # a subset of the scenario, so gross == scenario; with a polygon baseline
    # it need not be, and gross is then the union of the two.
    flood_mask = np.full(dem.shape, CLASS_DRY, dtype=np.uint8)
    flood_mask[baseline] = CLASS_BASELINE
    flood_mask[scenario & ~baseline] = CLASS_NEW

    # --- 5. STATISTICS ---------------------------------------------------
    metadata = summarize_mask(flood_mask, transform, bounds_read, nodata_mask)
    metadata.update({
        "tide_zh": tide_zh,
        "surge": surge,
        "slr": slr,
        "datum_offset": datum_offset,
        "total_water_level": total_water_level,
        "flood_threshold": flood_threshold,
        "baseline_tide_zh": baseline_tide_zh,
        "baseline_surge": baseline_surge,
        "baseline_slr": baseline_slr,
        "baseline_water_level": baseline_water_level,
        "baseline_threshold": baseline_threshold,
        "baseline_source": baseline_source,
        "downsample": downsample,
        "global_seed_downsample": (None if global_seed is None
                                   else global_seed.downsample),
        "bounds_requested": tuple(bounds),
        "crs": crs,
        "transform": transform,
    })

    if verbose:
        print_summary(metadata)

    return flood_mask, transform, metadata


def print_summary(metadata, indent=""):
    """Print the headline figures, net first."""
    w, h = metadata["pixel_size_m"]
    print(f"{indent}Pixel size: {w:.2f}m × {h:.2f}m")
    print(f"{indent}NEWLY INUNDATED LAND: "
          f"{metadata['flooded_area_new_km2']:.3f} km² "
          f"({metadata['flooded_area_new_m2']:,.0f} m², "
          f"{metadata['pixels_new']:,} px)")
    print(f"{indent}  baseline water (already water): "
          f"{metadata['baseline_area_km2']:.3f} km²")
    print(f"{indent}  gross below water level (net + baseline): "
          f"{metadata['flooded_area_gross_km2']:.3f} km²")


def crop_to_core(mask, transform, core_bounds, nodata_mask=None):
    """
    Crop a tile result to its non-overlapping core extent.

    Tiles are computed with an overlap so flooding can propagate across their
    boundaries; counting the padded result would count the overlap strips
    twice. Cropping to the core makes every pixel of the region belong to
    exactly one tile.

    Returns
    -------
    (mask_core, transform_core, bounds_core, nodata_core)
    """
    height, width = mask.shape
    win = from_bounds(*core_bounds, transform=transform)

    col_off = max(0, int(round(win.col_off)))
    row_off = max(0, int(round(win.row_off)))
    col_end = min(width, int(round(win.col_off + win.width)))
    row_end = min(height, int(round(win.row_off + win.height)))

    if col_end <= col_off or row_end <= row_off:
        raise ValueError(f"Core bounds {core_bounds} fall outside the tile")

    sliced = mask[row_off:row_end, col_off:col_end]
    transform_core = transform * Affine.translation(col_off, row_off)
    bounds_core = tuple(window_bounds(
        Window(col_off, row_off, col_end - col_off, row_end - row_off),
        transform,
    ))
    nodata_core = (None if nodata_mask is None
                   else nodata_mask[row_off:row_end, col_off:col_end])

    return sliced, transform_core, bounds_core, nodata_core


# ============================================================================
# OUTPUT
# ============================================================================

def save_flood_geotiff(flood_mask, transform, metadata, output_file, compress=True):
    """
    Save the classified flood mask as a GeoTIFF.

    Band values: 0 dry land, 1 newly inundated land, 2 baseline water.

    Parameters
    ----------
    flood_mask : numpy.ndarray
    transform : rasterio.Affine
    metadata : dict
        Simulation metadata (used for the CRS and for raster tags).
    output_file : str
    compress : bool, optional
    """
    save_array = flood_mask.astype(np.uint8)

    profile = {
        'driver': 'GTiff',
        'height': save_array.shape[0],
        'width': save_array.shape[1],
        'count': 1,
        'dtype': save_array.dtype,
        'crs': metadata['crs'],
        'transform': transform,
        'nodata': 255,
    }

    if compress:
        profile['compress'] = 'lzw'

    try:
        with rasterio.open(output_file, 'w', **profile) as dst:
            dst.write(save_array, 1)
            dst.update_tags(
                CLASS_0='dry land',
                CLASS_1='newly inundated land',
                CLASS_2='baseline water',
                FLOOD_THRESHOLD_NMM=f"{metadata['flood_threshold']:.3f}",
                BASELINE_THRESHOLD_NMM=f"{metadata['baseline_threshold']:.3f}",
                AREA_NEW_KM2=f"{metadata['flooded_area_new_km2']:.6f}",
                AREA_BASELINE_KM2=f"{metadata['baseline_area_km2']:.6f}",
                AREA_GROSS_KM2=f"{metadata['flooded_area_gross_km2']:.6f}",
            )
            dst.set_band_description(1, 'flood class')
        print(f"✓ Saved to: {output_file}")
    except Exception as e:
        print(f"Failed to save GeoTIFF: {e}")
        raise


def _flood_overlay_png(flood_mask):
    """Encode the classified mask as a base64 PNG data URL, or None."""
    if not HAS_PIL:
        print("  Note: Install Pillow for pixel-perfect overlay")
        print("  Run: pip install Pillow")
        print("  → Using rectangle approximation overlay")
        return None

    try:
        height, width = flood_mask.shape
        img_data = np.zeros((height, width, 4), dtype=np.uint8)

        # Newly inundated land is the subject of the map, so it gets the
        # strong colour; baseline water is context.
        img_data[flood_mask == CLASS_BASELINE] = [0, 90, 200, 110]
        img_data[flood_mask == CLASS_NEW] = [227, 26, 28, 215]

        buffer = BytesIO()
        Image.fromarray(img_data, mode='RGBA').save(buffer, format='PNG')
        png_bytes = buffer.getvalue()

        print(f"  ✓ Encoded flood mask as PNG ({len(png_bytes)} bytes)")
        return "data:image/png;base64," + base64.b64encode(png_bytes).decode('ascii')

    except Exception as e:
        print(f"Warning: Failed to encode PNG: {e}")
        print("  → Falling back to rectangle overlay")
        return None


def save_html_map(flood_mask, metadata, output_file, map_center=None, zoom=12):
    """
    Write an interactive Leaflet map of the flood classes.

    The overlay is placed on `metadata["bounds"]`, the extent actually read,
    which is what keeps it registered with the basemap when the requested
    bounds ran past the edge of the DEM.

    Parameters
    ----------
    flood_mask : numpy.ndarray
        Classified mask.
    metadata : dict
    output_file : str
    map_center : tuple, optional
        (lat, lon); derived from the bounds if omitted.
    zoom : int, optional

    Notes
    -----
    Needs Pillow for the pixel-perfect overlay; without it the map falls back
    to a rectangle covering the bounds.
    """
    print("Generating HTML map with pixel-perfect overlay...")

    min_lon, min_lat, max_lon, max_lat = metadata["bounds"]

    if map_center is None:
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2
    else:
        center_lat, center_lon = map_center

    flood_overlay_url = _flood_overlay_png(flood_mask)

    popup = (f"<b>Newly inundated land</b><br>"
             f"{metadata['flooded_area_new_km2']:.3f} km²")

    if flood_overlay_url is not None:
        overlay_code = f"""
            // Pixel-perfect flood overlay from embedded PNG
            var floodBounds = [[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]];
            var floodOverlay = L.imageOverlay(
                '{flood_overlay_url}',
                floodBounds,
                {{opacity: 1.0, interactive: true}}
            ).addTo(map);

            floodOverlay.bindPopup("{popup}");
        """
    else:
        overlay_code = f"""
            // Flood overlay (rectangle approximation - install Pillow for detail)
            var floodBounds = [[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]];
            var floodOverlay = L.rectangle(floodBounds, {{
                color: '#e31a1c',
                weight: 2,
                fillColor: '#e31a1c',
                fillOpacity: 0.4
            }}).addTo(map);

            floodOverlay.bindPopup("{popup}");
        """

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Coastal Flood Simulation - Python</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; }}
        #map {{ height: 100vh; width: 100vw; }}
        .info {{
            padding: 10px;
            background: white;
            border-radius: 5px;
            box-shadow: 0 0 15px rgba(0,0,0,0.2);
            max-width: 320px;
            font: 13px/1.4 system-ui, sans-serif;
        }}
        .info h4 {{ margin: 0 0 5px; color: #777; }}
        .info .headline {{ font-size: 16px; color: #b2171a; font-weight: 700; }}
        .info .secondary {{ color: #555; }}
        .legend {{
            line-height: 18px;
            color: #555;
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 0 15px rgba(0,0,0,0.2);
            font: 13px/1.5 system-ui, sans-serif;
        }}
        .legend i {{
            width: 18px;
            height: 18px;
            float: left;
            margin-right: 8px;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        // Initialize map
        var map = L.map('map').setView([{center_lat}, {center_lon}], {zoom});

        // Street basemap (default). Esri's World Street Map is used rather
        // than tile.openstreetmap.org, whose volunteer-run servers enforce a
        // tile usage policy: to a client they consider non-compliant they
        // return HTTP 200 with an "Access blocked" image rendered into the
        // tile itself, so the map silently fills with warning squares. Esri
        // publishes these endpoints for general use and needs no API key.
        // (CARTO's basemaps now require one, so they are not an option.)
        var streets = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, &copy; OpenStreetMap contributors',
            maxZoom: 19
        }}).addTo(map);

        // Satellite basemap: Esri World Imagery, which publishes this endpoint
        // for exactly this use.
        var satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
            maxZoom: 19
        }});

        {overlay_code}

        // Add info box
        var info = L.control({{position: 'topright'}});
        info.onAdd = function (map) {{
            this._div = L.DomUtil.create('div', 'info');
            this.update();
            return this._div;
        }};
        info.update = function (props) {{
            this._div.innerHTML = '<h4>Flood Simulation Results</h4>' +
                '<div class="headline">Newly inundated land: {metadata["flooded_area_new_km2"]:.3f} km²</div>' +
                '<div class="secondary">land dry today that floods under this scenario</div>' +
                '<hr>' +
                '<div class="secondary">' +
                '<b>Baseline water today:</b> {metadata["baseline_area_km2"]:.3f} km²<br>' +
                '<b>Gross below water level:</b> {metadata["flooded_area_gross_km2"]:.3f} km²<br>' +
                '<i>(gross = new + baseline; it includes the sea and estuaries, so it is not land at risk)</i><br>' +
                '<hr>' +
                '<b>Scenario TWL:</b> {metadata["total_water_level"]:.2f} m (ZH) → {metadata["flood_threshold"]:.2f} m (NMM)<br>' +
                '<b>Baseline TWL:</b> {metadata["baseline_water_level"]:.2f} m (ZH) → {metadata["baseline_threshold"]:.2f} m (NMM)<br>' +
                '<b>New / baseline pixels:</b> {metadata["pixels_new"]:,} / {metadata["pixels_baseline"]:,}<br>' +
                '<small>Pixel size: {metadata["pixel_size_m"][0]:.2f}m × {metadata["pixel_size_m"][1]:.2f}m' +
                ' (downsample {metadata["downsample"]})</small>' +
                '</div>';
        }};
        info.addTo(map);

        // Add legend
        var legend = L.control({{position: 'bottomright'}});
        legend.onAdd = function (map) {{
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML =
                '<i style="background: rgba(227, 26, 28, 0.85)"></i> Newly inundated land<br>' +
                '<i style="background: rgba(0, 90, 200, 0.45)"></i> Already water today<br>';
            return div;
        }};
        legend.addTo(map);

        // Layer control
        var baseMaps = {{
            "Streets": streets,
            "Satellite": satellite
        }};
        var overlayMaps = {{
            "Flood Extent": floodOverlay
        }};
        L.control.layers(baseMaps, overlayMaps).addTo(map);

        // Fit map to flood bounds
        map.fitBounds(floodBounds);
    </script>
    <div style="position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); z-index: 1000; background: white; padding: 5px; border-radius: 3px; font-size: 10px;">
        Generated with Python + Rasterio | Tide: {metadata["tide_zh"]}m + Surge: {metadata["surge"]}m + SLR: {metadata["slr"]}m
        | Baseline: {metadata["baseline_tide_zh"]}m (ZH), {metadata["baseline_source"]}
    </div>
</body>
</html>
"""

    # UTF-8 explicitly: the document declares UTF-8, and Python would otherwise
    # use the Windows ANSI code page and mangle "km²" and "×".
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✓ HTML map saved to: {output_file}")
    return output_file


# ============================================================================
# TILING SUPPORT FOR LARGE REGIONS
# ============================================================================

def create_tiles(bounds, tile_size_deg, overlap=0.001):
    """
    Divide a large bounding box into tiles.

    Each tile carries two extents: `core`, the nominal non-overlapping extent,
    and `bounds`, the core padded by `overlap` on every interior side. The
    simulation runs on `bounds` so flooding can cross tile boundaries; results
    are cropped to `core` so every pixel belongs to exactly one tile.

    Parameters
    ----------
    bounds : tuple
        (min_lon, min_lat, max_lon, max_lat).
    tile_size_deg : float
        Core tile size in degrees (0.1 ≈ 11 km).
    overlap : float, optional
        Padding in degrees on each side (default 0.001 ≈ 100 m).

    Returns
    -------
    list of Tile

    Example
    -------
    >>> tiles = create_tiles((-8.90, 40.55, -8.60, 41.87), 0.15, overlap=0.005)
    >>> tiles[0].core, tiles[0].bounds            # doctest: +SKIP

    Notes
    -----
    Overlap matters for hydrological connectivity at tile boundaries; 500 m
    (0.005°) is a sensible minimum for coastal zones.
    """
    min_lon, min_lat, max_lon, max_lat = bounds

    n_tiles_x = int(np.ceil((max_lon - min_lon) / tile_size_deg))
    n_tiles_y = int(np.ceil((max_lat - min_lat) / tile_size_deg))

    print("Creating tiling scheme:")
    print(f"  Total area: {(max_lon - min_lon):.3f}° × {(max_lat - min_lat):.3f}°")
    print(f"  Tile size: {tile_size_deg}° (~{tile_size_deg * 111:.1f} km)")
    print(f"  Grid: {n_tiles_x} × {n_tiles_y} = {n_tiles_x * n_tiles_y} tiles")
    print(f"  Overlap: {overlap}° (~{overlap * 111 * 1000:.0f} m) on each interior side")

    # Rounding in the ceil above can ask for one row or column more than the
    # extent needs, which would yield zero-width cores. Drop any sliver.
    sliver = tile_size_deg * 1e-6

    tiles = []

    for j in range(n_tiles_y):
        for i in range(n_tiles_x):
            core_min_lon = min_lon + i * tile_size_deg
            core_max_lon = min(min_lon + (i + 1) * tile_size_deg, max_lon)
            core_min_lat = min_lat + j * tile_size_deg
            core_max_lat = min(min_lat + (j + 1) * tile_size_deg, max_lat)

            if (core_max_lon - core_min_lon <= sliver
                    or core_max_lat - core_min_lat <= sliver):
                continue

            padded = (
                max(core_min_lon - overlap, min_lon),
                max(core_min_lat - overlap, min_lat),
                min(core_max_lon + overlap, max_lon),
                min(core_max_lat + overlap, max_lat),
            )

            tiles.append(Tile(
                index=len(tiles) + 1,
                bounds=padded,
                core=(core_min_lon, core_min_lat, core_max_lon, core_max_lat),
            ))

    if len(tiles) != n_tiles_x * n_tiles_y:
        print(f"  Dropped {n_tiles_x * n_tiles_y - len(tiles)} empty edge "
              f"tile(s); {len(tiles)} tiles to process")

    return tiles


def process_tiles(vrt_path, tiles, tide_zh, surge, slr,
                  output_dir="tiles", datum_offset=2.00,
                  save_individual_maps=True,
                  downsample=1,
                  global_seed_downsample=16,
                  **simulation_kwargs):
    """
    Process a list of tiles and total their areas without double counting.

    Each tile is simulated on its padded extent and then cropped to its core
    before anything is saved or counted, so the overlap strips contribute to
    connectivity but not to the total.

    Parameters
    ----------
    vrt_path : str
    tiles : list of Tile
    tide_zh, surge, slr : float
    output_dir : str, optional
    datum_offset : float, optional
    save_individual_maps : bool, optional
    downsample : int, optional
    global_seed_downsample : int or None, optional
        Resolution of the coarse whole-region connectivity pass that stops tile
        borders from seeding closed basins (default 16). Set to None to seed
        from every tile border, which is faster but over-predicts inland
        flooding.
    **simulation_kwargs
        Forwarded to `run_simulation_on_vrt` (e.g. baseline_tide_zh,
        water_mask_path).

    Returns
    -------
    results : list
        (mask_core, metadata_core, tile) per tile; (None, None, tile) on
        failure.
    totals : dict
        Corrected regional totals plus `naive_*` figures showing what the
        uncropped sum would have been.
    """
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("TILED FLOOD SIMULATION")
    print("=" * 70)
    print(f"Number of tiles: {len(tiles)}")
    print(f"Scenario: Tide={tide_zh}m + Surge={surge}m + SLR={slr}m")
    print(f"Downsample: {downsample}")
    print(f"Output directory: {output_dir}")
    print("=" * 70 + "\n")

    global_seed = None
    if global_seed_downsample:
        levels = compute_thresholds(
            tide_zh, surge, slr, datum_offset,
            simulation_kwargs.get("baseline_tide_zh"),
            simulation_kwargs.get("baseline_surge", 0.0),
            simulation_kwargs.get("baseline_slr", 0.0),
        )
        region = (
            min(t.core[0] for t in tiles), min(t.core[1] for t in tiles),
            max(t.core[2] for t in tiles), max(t.core[3] for t in tiles),
        )
        global_seed = build_global_seed_mask(
            vrt_path, region,
            levels["flood_threshold"], levels["baseline_threshold"],
            downsample=global_seed_downsample,
        )
        print("")

    results = []
    totals = {
        "new_km2": 0.0, "baseline_km2": 0.0, "gross_km2": 0.0,
        "pixels_new": 0, "pixels_baseline": 0,
        # What the previous implementation reported: the padded tiles summed,
        # which counts every overlap strip twice.
        "naive_new_km2": 0.0, "naive_baseline_km2": 0.0, "naive_gross_km2": 0.0,
        "tiles_ok": 0, "tiles_failed": 0,
        "downsample": downsample,
        "global_seed_downsample": global_seed_downsample,
    }

    start_time = datetime.now()

    for tile in tiles:
        idx = tile.index
        print(f"\n[{idx}/{len(tiles)}] Processing tile {idx}...")
        print(f"  Computed on: {tuple(round(v, 4) for v in tile.bounds)}")
        print(f"  Counted on:  {tuple(round(v, 4) for v in tile.core)}")

        try:
            flood_mask, transform, metadata = run_simulation_on_vrt(
                vrt_path, tide_zh, surge, slr, tile.bounds,
                datum_offset=datum_offset,
                downsample=downsample,
                global_seed=global_seed,
                verbose=False,
                **simulation_kwargs
            )

            # The padded figures, for the double-counting comparison only.
            totals["naive_new_km2"] += metadata["flooded_area_new_km2"]
            totals["naive_baseline_km2"] += metadata["baseline_area_km2"]
            totals["naive_gross_km2"] += metadata["flooded_area_gross_km2"]

            # Crop to the core so no pixel is counted twice.
            mask_core, transform_core, bounds_core, _ = crop_to_core(
                flood_mask, transform, tile.core
            )
            meta_core = dict(metadata)
            meta_core.update(summarize_mask(mask_core, transform_core, bounds_core))
            meta_core["transform"] = transform_core
            # This count was for the padded window and no longer matches the
            # cropped array; the fraction stays, as a property of the tile.
            meta_core.pop("nodata_pixels", None)
            meta_core["core_bounds"] = tile.core
            meta_core["padded_bounds"] = tile.bounds

            tif_file = os.path.join(output_dir, f"tile_{idx:03d}.tif")
            save_flood_geotiff(mask_core, transform_core, meta_core, tif_file)

            if save_individual_maps:
                html_file = os.path.join(output_dir, f"tile_{idx:03d}.html")
                save_html_map(mask_core, meta_core, html_file)

            totals["new_km2"] += meta_core["flooded_area_new_km2"]
            totals["baseline_km2"] += meta_core["baseline_area_km2"]
            totals["gross_km2"] += meta_core["flooded_area_gross_km2"]
            totals["pixels_new"] += meta_core["pixels_new"]
            totals["pixels_baseline"] += meta_core["pixels_baseline"]
            totals["tiles_ok"] += 1

            results.append((mask_core, meta_core, tile))

            print(f"  ✓ Tile {idx}: {meta_core['flooded_area_new_km2']:.3f} km² new "
                  f"(gross {meta_core['flooded_area_gross_km2']:.3f} km²)")

        except Exception as e:
            print(f"Warning: Failed to process tile {idx}: {e}")
            import traceback
            traceback.print_exc()
            totals["tiles_failed"] += 1
            results.append((None, None, tile))

    elapsed = datetime.now() - start_time
    totals["elapsed"] = str(elapsed)

    print("\n" + "=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)
    print(f"NEWLY INUNDATED LAND (total): {totals['new_km2']:.3f} km²")
    print(f"  baseline water today:       {totals['baseline_km2']:.3f} km²")
    print(f"  gross below water level:    {totals['gross_km2']:.3f} km²")
    print(f"Tiles: {totals['tiles_ok']} ok, {totals['tiles_failed']} failed")
    print("")
    print("Sum over padded tiles (double counts the overlaps, for comparison):")
    print(f"  new {totals['naive_new_km2']:.3f} km², "
          f"gross {totals['naive_gross_km2']:.3f} km²")
    if totals["gross_km2"] > 0:
        inflation = totals["naive_gross_km2"] / totals["gross_km2"] - 1
        print(f"  overlap inflation of the gross figure: {inflation * 100:.1f}%")
    print(f"Processing time: {elapsed}")
    print(f"Output location: {output_dir}")
    print("=" * 70 + "\n")

    return results, totals


def merge_tiles_to_vrt(tile_files, output_vrt):
    """
    Create a VRT mosaic from the tile GeoTIFFs.

    The tiles are already cropped to their cores, so the mosaic has no
    overlapping pixels and can be counted directly in QGIS.

    Parameters
    ----------
    tile_files : list of str
    output_vrt : str
    """
    print(f"Creating merged VRT from {len(tile_files)} tiles...")

    try:
        from osgeo import gdal
        vrt_options = gdal.BuildVRTOptions(resampleAlg='nearest')
        gdal.BuildVRT(output_vrt, tile_files, options=vrt_options)
        print(f"✓ Merged VRT created: {output_vrt}")
        print("  Open in QGIS to view the complete mosaic")
        return output_vrt
    except ImportError:
        pass
    except Exception as e:
        print(f"Warning: GDAL BuildVRT failed: {e}")

    # Fall back to writing the VRT XML directly, so a merged mosaic is still
    # produced on installations without the GDAL Python bindings.
    try:
        _write_vrt_xml(tile_files, output_vrt)
        print(f"✓ Merged VRT created (built without osgeo): {output_vrt}")
        return output_vrt
    except Exception as e:
        print(f"Warning: Failed to create VRT: {e}")
        print("  Try the command line: gdalbuildvrt "
              + output_vrt + " " + " ".join(tile_files))
        return None


def _write_vrt_xml(tile_files, output_vrt):
    """Write a simple mosaic VRT without the GDAL Python bindings."""
    from xml.sax.saxutils import escape

    infos = []
    for path in tile_files:
        with rasterio.open(path) as src:
            infos.append({
                "path": path,
                "width": src.width,
                "height": src.height,
                "transform": src.transform,
                "bounds": src.bounds,
                "dtype": src.dtypes[0],
                "nodata": src.nodata,
                "crs": src.crs,
            })

    if not infos:
        raise ValueError("No tiles to merge")

    res_x = abs(infos[0]["transform"][0])
    res_y = abs(infos[0]["transform"][4])
    left = min(i["bounds"].left for i in infos)
    right = max(i["bounds"].right for i in infos)
    top = max(i["bounds"].top for i in infos)
    bottom = min(i["bounds"].bottom for i in infos)

    width = int(round((right - left) / res_x))
    height = int(round((top - bottom) / res_y))

    dtype_map = {'uint8': 'Byte', 'uint16': 'UInt16', 'int16': 'Int16',
                 'int32': 'Int32', 'float32': 'Float32', 'float64': 'Float64'}
    gdal_dtype = dtype_map.get(str(infos[0]["dtype"]), 'Float32')

    out_dir = os.path.dirname(os.path.abspath(output_vrt))
    lines = [
        f'<VRTDataset rasterXSize="{width}" rasterYSize="{height}">',
        f'  <SRS>{escape(infos[0]["crs"].to_wkt())}</SRS>',
        f'  <GeoTransform>{left:.17g}, {res_x:.17g}, 0, {top:.17g}, 0, {-res_y:.17g}</GeoTransform>',
        f'  <VRTRasterBand dataType="{gdal_dtype}" band="1">',
    ]
    if infos[0]["nodata"] is not None:
        lines.append(f'    <NoDataValue>{infos[0]["nodata"]:.17g}</NoDataValue>')

    for info in infos:
        col_off = int(round((info["bounds"].left - left) / res_x))
        row_off = int(round((top - info["bounds"].top) / res_y))
        absolute = os.path.abspath(info["path"])
        try:
            source = os.path.relpath(absolute, out_dir)
            relative_to_vrt = 1
        except ValueError:
            # Different drives on Windows: no relative path exists.
            source = absolute
            relative_to_vrt = 0
        lines += [
            '    <SimpleSource>',
            f'      <SourceFilename relativeToVRT="{relative_to_vrt}">'
            f'{escape(source)}</SourceFilename>',
            '      <SourceBand>1</SourceBand>',
            f'      <SrcRect xOff="0" yOff="0" xSize="{info["width"]}" ySize="{info["height"]}" />',
            f'      <DstRect xOff="{col_off}" yOff="{row_off}" xSize="{info["width"]}" ySize="{info["height"]}" />',
        ]
        if info["nodata"] is not None:
            lines.append(f'      <NODATA>{info["nodata"]:.17g}</NODATA>')
        lines.append('    </SimpleSource>')

    lines += ['  </VRTRasterBand>', '</VRTDataset>', '']

    with open(output_vrt, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    return output_vrt


def create_index_map(tiles, output_file):
    """
    Write an HTML map of the tile grid, showing core and padded extents.

    Parameters
    ----------
    tiles : list of Tile
    output_file : str
    """
    print("Creating tile index map...")

    all_lons = [t.bounds[0] for t in tiles] + [t.bounds[2] for t in tiles]
    all_lats = [t.bounds[1] for t in tiles] + [t.bounds[3] for t in tiles]

    center_lon = (min(all_lons) + max(all_lons)) / 2
    center_lat = (min(all_lats) + max(all_lats)) / 2

    tile_html = ""
    for tile in tiles:
        c_min_lon, c_min_lat, c_max_lon, c_max_lat = tile.core
        p_min_lon, p_min_lat, p_max_lon, p_max_lat = tile.bounds
        tile_html += f"""
            L.rectangle([[{p_min_lat}, {p_min_lon}], [{p_max_lat}, {p_max_lon}]], {{
                color: '#999999', weight: 1, dashArray: '4 3', fill: false
            }}).addTo(map);
            L.rectangle([[{c_min_lat}, {c_min_lon}], [{c_max_lat}, {c_max_lon}]], {{
                color: '#ff7800',
                weight: 2,
                fillColor: '#ffaa00',
                fillOpacity: 0.1
            }}).addTo(map).bindPopup('<b>Tile {tile.index}</b><br>Core: [{c_min_lon:.3f}, {c_min_lat:.3f}, {c_max_lon:.3f}, {c_max_lat:.3f}]<br>Computed: [{p_min_lon:.3f}, {p_min_lat:.3f}, {p_max_lon:.3f}, {p_max_lat:.3f}]');
        """

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Tile Index Map</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; }}
        #map {{ height: 100vh; width: 100vw; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([{center_lat}, {center_lon}], 10);
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, &copy; OpenStreetMap contributors',
            maxZoom: 19
        }}).addTo(map);

        {tile_html}
    </script>
    <div style="position: absolute; top: 10px; right: 10px; z-index: 1000; background: white; padding: 10px; border-radius: 5px; font: 13px/1.4 system-ui, sans-serif;">
        <h3>Tile Grid</h3>
        <p>Total tiles: {len(tiles)}</p>
        <p><span style="color:#ff7800">■</span> core (counted once)<br>
           <span style="color:#999">⬚</span> computed extent (with overlap)</p>
    </div>
</body>
</html>
"""

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✓ Tile index map saved: {output_file}")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import sys

    # Choose mode: 'single' for one region or 'tiled' for large areas
    mode = 'single'  # Change to 'tiled' for large area processing

    if mode == 'single':
        # =================================================================
        # SINGLE REGION MODE
        # =================================================================
        print("=" * 70)
        print("Coastal Flood Simulation - Python Implementation")
        print("=" * 70)

        vrt_file = "portugal_coast_wgs84.vrt"
        output_file = "espinho_flood_result.tif"

        # Predefined bounding boxes
        espinho_bounds = (-8.70, 40.95, -8.60, 41.03)
        aveiro_bounds = (-8.75, 40.55, -8.60, 40.75)
        espinho_aveiro_bounds = (-8.75, 40.55, -8.60, 41.03)

        selected_bounds = espinho_bounds

        if not os.path.isfile(vrt_file):
            print(f"Error: VRT file '{vrt_file}' not found. Run makeVRT.py first.")
            sys.exit(1)

        print("\n1. Running simulation...")
        print(f"   Region: {selected_bounds}")
        print("   Scenario: HAT + 50yr surge + 2100 SLR")
        print("   Baseline: present-day HAT, no surge, no SLR")

        flood_mask, transform, metadata = run_simulation_on_vrt(
            vrt_file,
            3.8,   # HAT (Highest Astronomical Tide)
            0.6,   # 50-year storm surge
            1.13,  # Sea level rise scenario for 2100
            selected_bounds,
        )

        print("\n2. Simulation Results:")
        print(f"   Scenario TWL: {metadata['total_water_level']:.2f}m (ZH) "
              f"→ {metadata['flood_threshold']:.2f}m (NMM)")
        print(f"   Baseline TWL: {metadata['baseline_water_level']:.2f}m (ZH) "
              f"→ {metadata['baseline_threshold']:.2f}m (NMM)")
        print_summary(metadata, indent="   ")

        print("\n3. Saving results...")
        save_flood_geotiff(flood_mask, transform, metadata, output_file)

        html_file = output_file.replace(".tif", ".html")
        save_html_map(flood_mask, metadata, html_file)

        print("\n4. Visualization options:")
        print(f"   • HTML map: Open {html_file} in browser")
        print(f"   • GeoTIFF: Open {output_file} in QGIS/ArcGIS "
              "(0=dry, 1=new, 2=baseline water)")

        print("\n" + "=" * 70)
        print("Simulation complete!")
        print("=" * 70)

    elif mode == 'tiled':
        # =================================================================
        # TILED MODE FOR LARGE AREAS
        # =================================================================
        print("=" * 70)
        print("LARGE AREA FLOOD SIMULATION - NORTHERN PORTUGAL COAST")
        print("=" * 70)

        # Caminha (north) to Aveiro (south), roughly 150 km of coastline
        caminha_to_aveiro = (-8.90, 40.55, -8.60, 41.87)

        vrt_file = "portugal_coast_wgs84.vrt"

        if not os.path.isfile(vrt_file):
            print(f"Error: VRT file not found: {vrt_file}")
            print("Run makeVRT.py first.")
            sys.exit(1)

        # 0.15° ≈ 16.5 km cores with 500 m of overlap for connectivity
        tiles = create_tiles(caminha_to_aveiro, 0.15, overlap=0.005)

        create_index_map(tiles, "tile_index.html")
        print("\n→ Open tile_index.html to see the tile grid\n")

        results, totals = process_tiles(
            vrt_file,
            tiles,
            3.8,   # HAT
            0.6,   # 50-year surge
            1.13,  # 2100 SLR
            output_dir="tiles_output",
            save_individual_maps=True,
            downsample=4,  # ~2 m; the 50 cm VRT does not fit in RAM at 1
        )

        print("\n4. Creating merged VRT...")
        import glob
        tile_files = sorted(glob.glob("tiles_output/tile_*.tif"))

        if tile_files:
            merge_tiles_to_vrt(tile_files, "merged_flood_north_portugal.vrt")

        print("\n" + "=" * 70)
        print("ALL PROCESSING COMPLETE")
        print("=" * 70)
        print("\nOutputs:")
        print("  • Individual tiles: tiles_output/tile_*.tif")
        print("  • Individual maps: tiles_output/tile_*.html")
        print("  • Tile index: tile_index.html")
        print("  • Merged VRT: merged_flood_north_portugal.vrt (open in QGIS)")
        print("\nRecommendations:")
        print("  • For presentations: Use individual HTML maps for specific areas")
        print("  • For GIS analysis: Open merged VRT in QGIS/ArcGIS")
        print("  • For statistics: use the totals returned by process_tiles; the "
              "tiles are cropped to their cores so nothing is counted twice")
        print("=" * 70)
