# Installing Julia Packages for DGT Flood Simulation

## Required Packages

Install these packages for basic functionality:

```julia
using Pkg

# Core dependencies (required)
Pkg.add(["Rasters", "ArchGDAL", "ImageMorphology"])
```

## Optional Packages for Enhanced Features

### For Pixel-Perfect HTML Maps

Install these to get exact pixel-level flood visualization in HTML maps:

```julia
using Pkg
Pkg.add(["FileIO", "ImageIO", "ColorTypes"])
```

**Without these packages:**
- HTML maps will use a semi-transparent blue rectangle approximation
- Still shows bounds and statistics correctly
- Good for quick visualization

**With these packages:**
- HTML maps will show the exact flood mask pixel-by-pixel
- PNG image embedded directly in HTML
- Identical to Python/Folium output quality

### For Interactive GLMakie Plotting

```julia
using Pkg
Pkg.add("GLMakie")
```

Enables desktop visualization with `plot_results(result)`.

### For Map Tile Backgrounds in GLMakie

```julia
using Pkg
Pkg.add("Tyler")
```

Enables `plot_results(result, background_map=true)` with OpenStreetMap tiles.

## Quick Setup (All Features)

To install everything at once:

```julia
using Pkg
Pkg.add([
    "Rasters",
    "ArchGDAL",
    "ImageMorphology",
    "FileIO",
    "ImageIO",
    "ColorTypes",
    "GLMakie",
    "Tyler"
])
```

## Testing Installation

After installing, test with:

```julia
# Test basic functionality
using Rasters, ArchGDAL, ImageMorphology

# Test HTML map encoding
using FileIO, ImageIO, ColorTypes
println("✓ Pixel-perfect HTML maps: Available")

# Test visualization
using GLMakie
println("✓ Interactive plotting: Available")

# Test map backgrounds
using Tyler
println("✓ Map tile backgrounds: Available")
```

## Troubleshooting

### GDAL Errors
If you get GDAL-related errors:
```julia
using Pkg
Pkg.build("ArchGDAL")
```

### ImageIO Not Found
If ImageIO doesn't work:
```julia
using Pkg
Pkg.add("PNGFiles")  # Alternative PNG library
```

### GLMakie Display Issues
On Windows, if GLMakie doesn't display:
```julia
ENV["JULIA_DEBUG"] = "GLMakie"
using GLMakie
# Check for OpenGL driver issues
```
