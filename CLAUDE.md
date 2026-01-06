# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a coastal flood simulation system for Portuguese coastal zones using high-resolution Digital Elevation Models (DEMs) from DGT (Direção-Geral do Território). The project implements connected morphological flooding algorithms to simulate coastal inundation under various sea level scenarios.

## Core Architecture

### Data Processing Pipeline

1. **DEM Preprocessing** (`makeVRT.py`):
   - Mosaics multiple 50cm resolution DGT DEM tiles (.tif files)
   - Creates Virtual Raster (VRT) files for efficient memory usage
   - Reprojects from Portuguese grid to WGS84 (EPSG:4326) for web visualization

2. **Flood Simulation** (Multiple implementations):
   - **Python**: `Simul_corrected.py` - Main production version
   - **Julia**: `simul_flood.jl` - High-performance alternative
   - Uses morphological reconstruction (erosion method) for hydrologically-connected flooding

### Critical Domain Knowledge

**Vertical Datum Conversion:**
- DGT DEMs use Cascais 1938 datum (referenced to NMM - Mean Sea Level)
- Tidal data uses Hydrographic Zero (ZH)
- **DATUM_OFFSET = 2.00m** for Viana/Aveiro coastal zone
- Formula: `flood_threshold = (tide_zh + surge + slr) - DATUM_OFFSET`

**Flooding Algorithm:**
- Not simple bathtub flooding - uses connected morphological reconstruction
- Seeds flood from image boundaries (assumes ocean at edges)
- Interior pixels set to maximum elevation initially
- Morphological erosion reconstructs only hydrologically-connected areas below threshold
- Prevents isolated depressions from incorrectly appearing as flooded

### Data Structure

- `DEM/` - Contains 50cm resolution DGT tiles (MDT-50cm-*.tif format)
- `DEM2m/` - Alternative 2m resolution data
- `MDS05m/` - Digital Surface Model data (includes vegetation/buildings)
- VRT files created in root directory for efficient tile access

## Running Simulations

### Small to Medium Areas (< 50 km coastline)

**Python Version:**
```bash
python Simul_corrected.py
```

**Julia Version:**
```bash
julia simul_flood.jl
```

Outputs:
- GeoTIFF for QGIS/ArcGIS
- Interactive HTML map with basemap
- Console statistics

### Large Areas (> 50 km coastline)

For large regions like Caminha to Aveiro (~150 km), use the tiled approach:

**Julia Tiled Version:**
```bash
julia simul_flood_tiled.jl
```

This automatically:
1. Divides region into manageable tiles (0.15° ≈ 16.5 km each)
2. Processes each tile with proper overlap for flood connectivity
3. Generates individual GeoTIFFs and HTML maps per tile
4. Creates merged VRT for QGIS viewing
5. Calculates total flooded area across all tiles

**Key Feature**: 500m overlap between tiles ensures hydrological connectivity for coastal flooding.

See `TILING_GUIDE.md` for detailed recommendations on tile sizes and overlap.

### Building VRT Files

If VRT files are missing or DEM tiles are updated:

```bash
python makeVRT.py
```

This creates:
- `portugal_coast_mosaic.vrt` - Native projection mosaic
- `portugal_coast_wgs84.vrt` - WGS84 reprojected for web use

## Key Implementation Details

### Bounding Box Format

All bounds use format: `(min_lon, min_lat, max_lon, max_lat)`

Example regions:
- Espinho: `(-8.70, 40.95, -8.60, 41.03)`
- Ria de Aveiro: `(-8.75, 40.55, -8.60, 40.75)`

### NoData Handling

- DGT DEMs use -9999 or metadata nodata values
- Replaced with 9999 (high elevation) to prevent false flooding
- Values < -100m treated as nodata (Portugal has no such elevations)

### Area Calculation

**IMPORTANT**: Area is calculated in real-world units (m² and km²), not deg².

At Portugal's latitude (~40-41°N), coordinate conversion is:
- **1° latitude** ≈ 111,320 m (constant)
- **1° longitude** ≈ 111,320 × cos(latitude) m (latitude-dependent)

Both implementations automatically:
1. Calculate center latitude of the region
2. Convert pixel dimensions from degrees to meters
3. Report flooded area in both km² and m²

Example output:
```
Pixel size: 0.43m × 0.56m
Flooded area: 2.145 km² (2,145,367 m²)
```

### Python vs Julia Differences

**Python (Simul_corrected.py):**
- Uses `rasterio` for GDAL access
- `skimage.morphology.reconstruction` for flooding
- `folium` for web-based visualization
- Returns HTML maps directly viewable in browser

**Julia (simul_flood.jl):**
- Uses `Rasters.jl` with `ArchGDAL` backend
- `ImageMorphology.mreconstruct` for flooding
- `GLMakie` for interactive visualization (preserves spatial context)
- Outputs GeoTIFF for GIS software integration
- Plotting properly handles Raster coordinates (pixel centers)

### Array Dimension Handling

**Critical difference:**
- Python: Rasterio returns `(bands, height, width)` - extract `[0]` for first band
- Julia: Rasters.jl uses named dimensions `(X, Y, Band)` - use `Band(1)` selector

### Index Boundaries

Edge seeding requires interior masking:
- Python: `seed[1:-1, 1:-1]` (0-indexed, negative indexing)
- Julia: `seed[2:end-1, 2:end-1]` (1-indexed, end keyword)

## Dependencies

**Python:**
- rasterio, numpy, folium
- shapely, scikit-image
- GDAL/osgeo (for VRT building)

**Julia:**
- **Required**: Rasters.jl, ArchGDAL.jl, ImageMorphology.jl, Statistics, Base64
- **Optional** (for pixel-perfect HTML maps): FileIO.jl, ImageIO.jl, ColorTypes.jl
  - Without these: HTML maps use rectangle approximation
  - With these: HTML maps show exact pixel-level flood data
- **Optional** (for interactive plotting): GLMakie.jl
- **Optional** (for map tile backgrounds): Tyler.jl

## Workflow for New Scenarios

1. Define bounding box for region of interest
2. Set scenario parameters: `tide_zh`, `surge`, `slr`
3. Run simulation with `run_simulation_on_vrt()`
4. Analyze output (HTML map or GeoTIFF)
5. Review flooded area in km² (properly calculated for latitude)
6. Adjust threshold or bounds as needed

### Visualization Notes

**Python**: Generates HTML with Folium (interactive web map)
- Overlay on Google Satellite imagery
- Viewable directly in browser

**Julia**: Generates multiple output formats
- **HTML Map**: `save_html_map(result, "output.html", metadata)`
  - Interactive Leaflet.js map with OpenStreetMap/Satellite basemap
  - **Pixel-perfect flood overlay** (if FileIO/ImageIO installed)
  - PNG image embedded as base64 data URL
  - Falls back to rectangle approximation if packages missing
  - Info panel with simulation statistics
  - Layer control for basemap switching
  - Legend showing flooded areas
- **GeoTIFF**: `save_flood_geotiff(result, "output.tif")`
  - Open in QGIS/ArcGIS for professional GIS analysis
- **GLMakie Plot**: `plot_results(result, background_map=true)`
  - Interactive plot preserving spatial coordinates
  - Optional map tile background with Tyler.jl
  - Coordinates represent pixel centers (proper spatial alignment)

## Tiling for Large Regions

**When to use tiling**: Regions > 50 km coastline or > 100 km² area

**Recommended tile sizes**:
- Standard: 0.15° (~16.5 km) - good balance
- High detail: 0.10° (~11 km) - more tiles, slower
- Low RAM: 0.05° (~5.5 km) - smallest tiles

**Critical: Tile Overlap**
- **Must use overlap** (default: 0.005° = 500m) for hydrological connectivity
- Without overlap: flood cannot propagate across tile boundaries
- Coastal flooding uses morphological reconstruction from edges

**Example: Northern Portugal (Caminha to Aveiro)**
```julia
# 150 km coastline split into ~12 tiles
bounds = (-8.90, 40.55, -8.60, 41.87)
tiles = create_tiles(bounds, 0.15, overlap=0.005)
process_tiles("portugal_coast_wgs84.vrt", tiles, 3.8, 0.6, 1.13)
```

**Outputs**:
- `tiles_output/tile_001.tif` through `tile_012.tif` (individual GeoTIFFs)
- `tiles_output/tile_001.html` through `tile_012.html` (individual maps)
- `merged_flood_north_portugal.vrt` (unified mosaic for QGIS)
- `tile_index.html` (reference map showing tile grid)

**Performance**:
- Memory per tile: 1-3 GB (vs 10-20 GB for single region)
- Processing time: ~30-60 min for 12 tiles
- Can be parallelized across CPU cores

See `TILING_GUIDE.md` for comprehensive documentation.
