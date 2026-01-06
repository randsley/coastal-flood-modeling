# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Example Jupyter/Pluto notebooks with sample data
- Performance benchmarks documentation
- Additional vertical datum conversions for other Portuguese regions
- Docker container for reproducible environment

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
