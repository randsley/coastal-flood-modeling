# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Basemaps in the HTML maps showed "Access blocked" tiles.** The maps
  requested `{s}.tile.openstreetmap.org`, a deprecated form that OpenStreetMap's
  volunteer-run servers treat as non-compliant with their tile usage policy.
  They answer such a client with HTTP 200 and an "Access blocked" graphic
  rendered *into the tile*, so the map filled with identical warning squares
  rather than failing visibly. The street basemap is now Esri World Street Map
  and the satellite basemap Esri World Imagery, both keyless and published for
  this use. (CARTO's basemaps now require an API key, so they are not an
  alternative.) The satellite layer previously used an undocumented Google
  `mt1.google.com/vt` endpoint that is not licensed for this; the legacy
  `Simul.py` used it too and has been changed as well.

### Planned
- Example Jupyter/Pluto notebooks with sample data
- Performance benchmarks documentation
- Additional vertical datum conversions for other Portuguese regions
- Docker container for reproducible environment

## [2.0.0] - 2026-10-27

### Breaking
- The headline area figure changed meaning. `flooded_area_km2` is gone;
  use `flooded_area_new_km2` (newly inundated land), with
  `baseline_area_km2` and `flooded_area_gross_km2` alongside it. Figures
  published from 1.0.0 are gross extents and are not comparable.
- Output GeoTIFFs are classified, not binary: `0` dry land, `1` newly
  inundated land, `2` baseline water. Code that treated any non-zero pixel
  as "flooded" now counts existing water as well.
- `process_tiles` returns `(results, totals)` rather than `results`. Use
  `totals`; summing the per-tile figures double-counts the overlaps.

### Fixed
- **Flooded area counted water that was already water.** The DGT DEM includes
  the sea surface, so edge-seeded reconstruction classified the Atlantic and the
  Ria de Aveiro as "flooded". A second pass at the present-day highest
  astronomical tide now establishes a baseline water mask, and the headline
  figure is `newly inundated land = scenario AND NOT baseline`. Both
  implementations report `flooded_area_new_km2`, `baseline_area_km2` and
  `flooded_area_gross_km2`; the ambiguous `flooded_area_km2` key is gone.
  Previously published totals for the Caminha–Aveiro region were gross figures
  and overstated land at risk by roughly a factor of seven.
- **Double counting in tiled totals.** Tiles are padded by `overlap` on each
  interior side, so neighbours shared a strip twice the overlap wide, and
  `process_tiles` summed the padded tiles. Tiles now carry a non-overlapping
  `core`; outputs are cropped to it and totals are computed from it, so each
  pixel is counted exactly once. `process_tiles` returns `(results, totals)`.
- **False flooding from tile edges.** A tile border is not coastline, but it
  was seeded as though it were, flooding closed basins it happened to cut
  through. A coarse whole-region connectivity pass
  (`global_seed_downsample`, default 16) now decides where a tile border may
  admit water. A tiled run reproduces a single-pass run pixel for pixel.
- **Nothing flooded where the sea does not reach the edge of the window.**
  Water was only ever seeded from the border ring of the array, but the DGT
  mosaic is a coastal strip whose seaward limit is a stair-step of 1 km tiles,
  so over most of the region the sea lies *inside* the window and simply stops
  where the survey stops. Seventeen of the eighteen regional tiles came back
  empty. Low ground meeting the outside of the DEM coverage is now a water
  source as well (`seed_from_nodata`, on by default). NoData enclosed by
  coverage — a missing tile — is still not a source, since nothing is known to
  connect through it.
- **HTML written in the platform encoding.** Python opened the map files
  without `encoding='utf-8'`, which on Windows is cp1252, so `km²` and `×`
  were mangled in documents declaring UTF-8.
- **Zero-width trailing tiles.** Rounding in `create_tiles` could ask for one
  row or column more than the extent needed; such slivers are now dropped.
- **Image overlays misplaced when the window ran past the DEM.** The HTML map
  was positioned on the requested bounds rather than the extent actually read.

### Added
- `downsample` parameter on the read path, issuing the same windowed,
  decimated GDAL call in both languages, so Python and Julia read identical
  pixels (verified byte-identical on Espinho at 50 cm).
- Optional land/water polygon baseline via `water_mask_path` (GeoPackage or
  shapefile); never required.
- Classified output: GeoTIFF band values `0` dry land, `1` newly inundated
  land, `2` baseline water, with the areas written as raster tags. HTML maps
  draw the two classes separately with a matching legend.
- Test suites on a synthetic DEM: `test_flood_simulation.py` and
  `test_flood_simulation.jl`.
- `check_dem_coverage.py`, which shows that the rectangular blocks along the
  coast are the limit of DGT tile coverage rather than a NoData-handling bug.
- `merge_tiles_to_vrt` now writes the mosaic VRT itself when the GDAL Python
  bindings are unavailable; the Julia side uses ArchGDAL rather than requiring
  `gdalbuildvrt` on PATH.

## [1.0.0] - 2026-01-06

### Initial Release

#### Added
- **Core Flood Simulation Algorithm**
  - Connected morphological flooding using erosion-based reconstruction
  - Hydrologically-connected flood propagation from boundaries
  - Support for tide, storm surge, and sea level rise scenarios
  - Proper vertical datum conversion (Cascais 1938 to Hydrographic Zero)

- **Julia Implementation** (`simul_flood.jl`)
  - High-performance flood modeling using Rasters.jl and ArchGDAL
  - Morphological reconstruction via ImageMorphology.jl
  - GeoTIFF output for GIS software integration
  - Interactive HTML maps with pixel-perfect flood overlays
  - Optional GLMakie visualization with map tile backgrounds

- **Julia Tiled Processing** (`simul_flood_tiled.jl`)
  - Automatic region subdivision for large coastal areas (>150 km)
  - Configurable tile size and overlap for hydrological connectivity
  - Parallel-ready tile processing
  - Merged VRT creation for unified viewing in QGIS
  - Tile index HTML map generation
  - Total flooded area calculation across all tiles

- **Python Implementation** (`Simul_corrected.py`)
  - Flood modeling using rasterio and scikit-image
  - Morphological reconstruction for connected flooding
  - Folium-based interactive HTML maps
  - Google Satellite basemap integration

- **Data Processing** (`makeVRT.py`)
  - Virtual raster (VRT) mosaic creation from DGT DEM tiles
  - Automatic reprojection to WGS84 for web visualization
  - Support for 50cm and 2m resolution DEMs

- **Utilities** (`regenerate_html_maps.jl`)
  - Batch regeneration of HTML maps from existing GeoTIFF outputs
  - Preserves simulation metadata and statistics

- **Documentation**
  - Comprehensive README with installation and usage examples
  - CLAUDE.md for AI assistant integration
  - INSTALL_PACKAGES.md for dependency installation
  - TILING_GUIDE.md for large region processing
  - QUICK_START_TILING.md for rapid reference
  - CONTRIBUTING.md with code style and PR guidelines
  - CITATION.cff for academic citation
  - MIT License

- **Area Calculation**
  - Real-world area computation in m² and km²
  - Latitude-dependent longitude scaling
  - Automatic pixel dimension conversion from degrees to meters

- **Visualization Features**
  - Interactive Leaflet.js maps with OpenStreetMap/Satellite basemaps
  - Pixel-accurate flood extent overlays (PNG embedded as base64)
  - Layer control and legend
  - Simulation metadata display panel
  - GeoTIFF outputs compatible with QGIS/ArcGIS

#### Performance
- Memory-efficient lazy loading for large rasters
- Automatic memory constraint handling
- Typical processing: ~2-4 minutes for 50 km coastline at 50cm resolution
- Tiled approach: ~30-60 minutes for 150 km coastline (12 tiles)

#### Validated Regions
- Espinho coastal zone
- Ria de Aveiro
- Northern Portugal (Caminha to Aveiro, ~150 km)

#### Scientific Basis
- Morphological erosion-based flood reconstruction
- Prevents isolated depression false positives
- Ocean boundary seeding for realistic propagation
- Datum offset: 2.00m for Viana/Aveiro coastal zone (Cascais 1938 to ZH)

### Technical Details
- **Languages**: Julia 1.10+, Python 3.8+
- **Key Dependencies**:
  - Julia: Rasters.jl, ArchGDAL.jl, ImageMorphology.jl
  - Python: rasterio, scikit-image, folium
- **Input**: DGT 50cm resolution DEM tiles (MDT format)
- **Output**: GeoTIFF (EPSG:4326), interactive HTML maps, VRT mosaics
- **Coordinate System**: WGS84 (EPSG:4326) for outputs
- **DEM Datum**: Cascais 1938 (Mean Sea Level)

---

**Note**: This changelog will be updated with each release. See [GitHub Releases](https://github.com/randsley/coastal-flood-modeling/releases) for downloadable versions.
