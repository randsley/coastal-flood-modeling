---
name: Bug Report
about: Report a bug or unexpected behavior
title: '[BUG] '
labels: bug
assignees: ''
---

## Bug Description

A clear and concise description of what the bug is.

## Steps to Reproduce

1. Load DEM with '...'
2. Run simulation with '...'
3. See error

## Expected Behavior

What you expected to happen.

## Actual Behavior

What actually happened.

## Environment

**Operating System:** [e.g., macOS 14.0, Ubuntu 22.04, Windows 11]

**Language & Version:**
- [ ] Julia [version: e.g., 1.10.0]
- [ ] Python [version: e.g., 3.11.5]

**Key Package Versions:**
- Rasters.jl: [if Julia, from `Pkg.status()`]
- rasterio: [if Python, from `pip list`]
- ArchGDAL: [version]

## Code Sample

```julia
# Minimal reproducible example
bounds = (-8.70, 40.95, -8.60, 41.03)
result = run_simulation_on_vrt("test.vrt", 3.8, 0.6, 1.13, bounds)
# Error occurs here...
```

## Error Message

```
Paste full error traceback here
```

## Data Information

- **DEM Source:** [e.g., DGT 50cm tiles, custom DEM]
- **Bounding Box:** [coordinates]
- **Region Size:** [approximate area or extent]
- **File Size:** [if relevant]

## Additional Context

Add any other context about the problem here (screenshots, maps, etc.).

## Possible Solution

If you have ideas about what might be causing this or how to fix it.
