# Coastal Flood Simulation System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Julia](https://img.shields.io/badge/Julia-1.10+-purple.svg)](https://julialang.org/)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![GitHub Stars](https://img.shields.io/github/stars/randsley/coastal-flood-modeling?style=social)](https://github.com/randsley/coastal-flood-modeling/stargazers)
[![GitHub Issues](https://img.shields.io/github/issues/randsley/coastal-flood-modeling)](https://github.com/randsley/coastal-flood-modeling/issues)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.18186745-blue)](https://github.com/randsley/coastal-flood-modeling)

High-resolution coastal flood modeling for Portuguese coastal zones using 50cm Digital Elevation Models (DEMs) from DGT (Direção-Geral do Território).

## Overview

This system implements **connected morphological flooding algorithms** to simulate coastal inundation under various sea level scenarios. Unlike simple "bathtub" models, it uses morphological reconstruction to ensure only **hydrologically-connected** areas are identified as flooded.

### Key Features

- **High Resolution**: 50cm DEM resolution for detailed flood mapping
- **Hydrologically Connected**: Uses morphological erosion to prevent isolated depressions from incorrectly appearing flooded
- **Large Area Support**: Tiled processing for regions >150 km coastline
- **Multiple Outputs**: GeoTIFF for GIS analysis, interactive HTML maps for visualization
- **Dual Implementation**: Python and Julia versions for flexibility and performance

## Quick Start

### Small Areas (< 50 km coastline)

**Julia (Recommended):**
```bash
julia simul_flood.jl
```

**Python:**
```bash
python Simul_corrected.py
```

### Large Areas (> 50 km coastline)

For large regions like Caminha to Aveiro (~150 km):

```bash
julia simul_flood_tiled.jl
```

This automatically:
- Divides the region into manageable tiles (~16.5 km each)
- Processes each tile with proper overlap (500m) for flood connectivity
- Generates individual GeoTIFFs and HTML maps per tile
- Creates a merged VRT for QGIS viewing

## Installation

### Prerequisites

**Julia Dependencies:**
```julia
using Pkg
Pkg.add(["Rasters", "ArchGDAL", "ImageMorphology", "Statistics"])
Pkg.add(["FileIO", "ImageIO", "ColorTypes"])  # For HTML maps
Pkg.add("GLMakie")  # Optional: for interactive plotting
```

**Python Dependencies:**
```bash
pip install rasterio numpy folium shapely scikit-image gdal
```

### Data Setup

**Note**: DEM data files are not included in this repository due to size constraints.

1. **Obtain DEM data**:
   - Download 50cm resolution DEM tiles from [DGT (Direção-Geral do Território)](https://www.dgterritorio.gov.pt/)
   - Look for MDT-50cm-*.tif files covering your area of interest
   - Place tiles in the `DEM/` directory

2. **Build VRT files**:
   ```bash
   python makeVRT.py
   ```
   This creates:
   - `portugal_coast_mosaic.vrt` - Native projection
   - `portugal_coast_wgs84.vrt` - WGS84 for web visualization

## Usage

### Basic Simulation

```julia
using Rasters
include("simul_flood.jl")

# Define region and scenario
bounds = (-8.70, 40.95, -8.60, 41.03)  # (min_lon, min_lat, max_lon, max_lat)
tide_zh = 3.8    # Highest Astronomical Tide (m, relative to ZH)
surge = 0.6      # Storm surge (m)
slr = 1.13       # Sea level rise (m)

# Run simulation
result, transform, metadata = run_simulation_on_vrt(
    "portugal_coast_wgs84.vrt",
    tide_zh, surge, slr, bounds
)

# Save outputs
save_flood_geotiff(result, "flood_output.tif")
save_html_map(result, "flood_map.html", metadata)
```

### Tiled Processing for Large Regions

```julia
include("simul_flood_tiled.jl")

# Define large region
bounds = (-8.90, 40.55, -8.60, 41.87)  # Caminha to Aveiro

# Create tiles
tiles = create_tiles(bounds, 0.15, overlap=0.005)

# Process all tiles
results = process_tiles(
    "portugal_coast_wgs84.vrt",
    tiles,
    3.8,   # HAT
    0.6,   # 50-year surge
    1.13,  # 2100 SLR
    output_dir="tiles_output"
)
```

## Vertical Datum Information

**Critical for accurate results:**

- **DGT DEMs**: Use Cascais 1938 datum (referenced to NMM - Mean Sea Level)
- **Tidal data**: Uses Hydrographic Zero (ZH)
- **DATUM_OFFSET**: 2.00m for Viana/Aveiro coastal zone

**Formula:**
```
flood_threshold = (tide_zh + surge + slr) - DATUM_OFFSET
```

## Algorithm Details

### Connected Morphological Flooding

1. **Seed Creation**: Interior pixels set to maximum elevation, boundaries at actual elevation
2. **Threshold Application**: Pixels below flood threshold remain as max elevation in seed
3. **Morphological Erosion**: Reconstructs only hydrologically-connected areas below threshold
4. **Result**: Binary flood mask showing connected flooded areas

This ensures flooding propagates from the ocean boundaries only, preventing isolated depressions from appearing flooded.

### Area Calculation

Areas are calculated in **real-world units** (m² and km²), not degrees:

At Portugal's latitude (~40-41°N):
- **1° latitude** ≈ 111,320 m (constant)
- **1° longitude** ≈ 111,320 × cos(latitude) m (varies with latitude)

The system automatically converts pixel dimensions from degrees to meters for accurate area reporting.

## Output Files

### GeoTIFF Files
- **Format**: Single-band raster (1=flooded, 0=dry)
- **Projection**: WGS84 (EPSG:4326)
- **Use**: Professional GIS analysis in QGIS/ArcGIS

### Interactive HTML Maps
- **Features**:
  - Pixel-accurate flood overlay
  - OpenStreetMap/Satellite basemap
  - Interactive zoom/pan
  - Layer control
  - Simulation statistics panel
- **Technology**: Leaflet.js with embedded PNG overlay
- **Use**: Presentations, web sharing, quick visualization

### VRT Mosaics
- **Merged tiles**: Single virtual dataset from all tiles
- **Efficient**: No data duplication, instant access
- **Use**: View entire simulation region in QGIS

## Example Results

**Northern Portugal Coast (Caminha to Aveiro)**

Scenario: HAT (3.8m) + 50-year surge (0.6m) + 2100 SLR (1.13m)

- **Total flooded area**: 363.854 km²
- **Processing time**: ~3 minutes (27 tiles)
- **Resolution**: 1.5m × 2.0m pixels
- **Largest flooding**: Ria de Aveiro (88-111 km² per tile)

## File Structure

```
.
├── simul_flood.jl              # Main Julia implementation
├── simul_flood_tiled.jl        # Tiled processing for large areas
├── Simul_corrected.py          # Python implementation
├── makeVRT.py                  # VRT file builder
├── regenerate_html_maps.jl     # Utility to regenerate HTML from GeoTIFFs
├── DEM/                        # 50cm resolution DEM tiles
├── tiles_output/               # Tiled simulation outputs
│   ├── tile_001.tif           # Individual tile GeoTIFFs
│   ├── tile_001.html          # Individual tile HTML maps
│   └── ...
├── merged_flood_*.vrt          # Merged VRT mosaics
├── tile_index.html            # Tile grid reference map
├── CLAUDE.md                  # Project guidance for AI assistants
└── README.md                  # This file
```

## Performance Tips

### Memory Management
- **Small regions** (<50 km): Load entire region at once
- **Large regions** (>50 km): Use tiled approach
- **Tile size**: 0.15° (~16.5 km) is recommended
- **Overlap**: 500m minimum for hydrological connectivity

### Recommended Tile Sizes
- **Standard**: 0.15° (~16.5 km) - good balance
- **High detail**: 0.10° (~11 km) - more tiles, slower
- **Low RAM**: 0.05° (~5.5 km) - smallest tiles

## Troubleshooting

### Memory Errors
If you encounter "required memory greater than system memory" errors:
- The system automatically disables memory checking (`Rasters.checkmem!(false)`)
- Uses lazy loading with `view()` for efficient subsetting
- If issues persist, reduce tile size

### Missing Data Handling
- DGT DEMs use -9999 or metadata nodata values
- Replaced with 9999 (high elevation) to prevent false flooding
- Values < -100m treated as nodata (Portugal has no such elevations)

### HTML Map Issues
- Requires `FileIO`, `ImageIO`, `ColorTypes` packages for pixel-perfect overlays
- Falls back to rectangle overlay if packages missing
- Install with: `using Pkg; Pkg.add(["FileIO", "ImageIO", "ColorTypes"])`

## Citation

If using this system for research, please cite:

```bibtex
@software{randsley2026coastal,
  author       = {Randsley, Nigel},
  title        = {Coastal Flood Simulation System for Portuguese Coastal Zones},
  year         = 2026,
  publisher    = {Zenodo},
  version      = {1.0.0},
  doi          = {10.5281/zenodo.XXXXX},
  url          = {https://doi.org/10.5281/zenodo.XXXXX}
}
```

**Note**: Replace `XXXXX` with the actual Zenodo DOI after creating your first release.

### Setting up Zenodo DOI

This repository is configured for Zenodo archiving. To get a permanent DOI:

1. See the comprehensive guide: [`docs/ZENODO_SETUP.md`](docs/ZENODO_SETUP.md)
2. Quick checklist: [`docs/ZENODO_CHECKLIST.md`](docs/ZENODO_CHECKLIST.md)
3. Once published, update the DOI badge at the top of this README

### Additional Citations

- **DEM Data**: DGT (Direção-Geral do Território) - 50cm resolution Digital Elevation Models
- **Morphological Flooding Algorithm**: Based on scikit-image morphological reconstruction (Python) and ImageMorphology.jl (Julia)

## License

MIT License

Copyright (c) 2026 Nigel Randsley

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Contact

**Nigel Randsley, PhD**
Email: nigel.randsley@protonmail.com

## Acknowledgments

- DGT for providing high-resolution DEM data
- Portuguese coastal authorities for tidal datum information
- Rasters.jl and scikit-image communities

---

**Last Updated**: January 2026
**Tested with**: Julia 1.10+, Python 3.8+
