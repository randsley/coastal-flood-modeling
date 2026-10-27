# Tiling Strategy for Large Coastal Areas

## When to Use Tiling

Use tiling when your region meets any of these criteria:

1. **Geographic extent**: > 50 km coastline
2. **Memory concerns**: DEM would exceed 2-4 GB in memory
3. **HTML file size**: Embedded PNG would be > 10 MB
4. **Processing time**: Single simulation takes > 5 minutes

## Northern Portugal Example

**Caminha to Aveiro**: ~150 km coastline, ~132 km north-south

```julia
# Single region (NOT RECOMMENDED - too large!)
large_bounds = (-8.90, 40.55, -8.60, 41.87)  # Will cause memory issues

# Tiled approach (RECOMMENDED)
tiles = create_tiles(large_bounds, 0.15, overlap=0.005)
# Results in ~12 tiles of manageable size
```

## Tile Size Recommendations

| Tile Size | Approx. Area | Memory Usage | Recommended For |
|-----------|--------------|--------------|-----------------|
| 0.05° (~5.5 km) | ~30 km² | ~100-500 MB | Very high resolution, small RAM |
| 0.10° (~11 km) | ~120 km² | ~500 MB - 2 GB | Standard processing |
| 0.15° (~16.5 km) | ~270 km² | ~1-3 GB | Large tiles, good RAM |
| 0.20° (~22 km) | ~480 km² | ~2-5 GB | Maximum recommended |

**Note**: Memory usage depends on DEM resolution (50cm vs 2m)

## Critical: Tile Overlap for Coastal Flooding

**WHY OVERLAP IS ESSENTIAL**:

Coastal flooding is **hydrologically connected**. Water needs to flow from the ocean through tile boundaries. Without overlap:

```
❌ NO OVERLAP:
┌─────┐┌─────┐
│ Tile││ Tile│
│  1  ││  2  │  ← Gap prevents flood connectivity!
└─────┘└─────┘
        ↑ Water cannot cross this boundary

✓ WITH OVERLAP:
┌─────┐
│ Tile│───┐
│  1  │ O │
└─────┤ v │
    ┌─│ e │───┐
    │ │ r │   │
    │ └───┤ 2 │  ← Flood can propagate across tiles
    │     │   │
    └─────┴───┘
```

**Recommended Overlap Values**:
- **Minimum**: 0.001° (~100 m)
- **Standard**: 0.005° (~500 m) ← RECOMMENDED
- **Conservative**: 0.01° (~1 km)

For 50cm DEM data with coastal flooding, **0.005°** (500m) is optimal:
- Ensures hydrological connectivity
- Covers ~1000 pixels of overlap (enough for morphological reconstruction)
- Minimal redundant processing

## Processing Workflow

### 1. Create Tile Grid

```julia
using simul_flood_tiled

# Define large region
bounds = (-8.90, 40.55, -8.60, 41.87)  # Caminha to Aveiro

# Create tiles
tiles = create_tiles(bounds, 0.15, overlap=0.005)

# Visualize the grid
create_index_map(tiles, "tile_index.html")
```

### 2. Process Tiles

```julia
# Process all tiles with same scenario
results = process_tiles(
    "portugal_coast_wgs84.vrt",
    tiles,
    3.8,   # Tide
    0.6,   # Surge
    1.13,  # SLR
    output_dir="tiles_output",
    save_individual_maps=true  # false for faster processing
)
```

**Output Structure**:
```
tiles_output/
├── tile_001.tif    # GeoTIFF
├── tile_001.html   # Interactive map
├── tile_002.tif
├── tile_002.html
├── ...
└── tile_012.html
```

### 3. Merge Results (Optional)

For GIS analysis, merge tiles into a single VRT:

```julia
# In Julia (requires GDAL command-line tools)
tile_files = glob("tiles_output/tile_*.tif")
merge_tiles_to_vrt(tile_files, "merged_flood.vrt")
```

Or use GDAL directly:
```bash
gdalbuildvrt merged_flood.vrt tiles_output/tile_*.tif
```

Open `merged_flood.vrt` in QGIS to view the complete mosaic.

### 4. Calculate Total Statistics

`process_tiles` returns `(results, totals)`. Use `totals` — it is computed from
each tile's non-overlapping core, so every pixel is counted exactly once:

```julia
results, totals = process_tiles(vrt_path, tiles, 3.8, 0.6, 1.13;
                                output_dir="tiles_output_julia", downsample=4)

println("Newly inundated land: $(round(totals["new_km2"], digits=3)) km²")
println("Baseline water today: $(round(totals["baseline_km2"], digits=3)) km²")
println("Gross below water level: $(round(totals["gross_km2"], digits=3)) km²")
```

> **Do not sum the per-tile figures of the padded extents.** Tiles are padded by
> `overlap` on each interior side, so neighbours share a strip twice the overlap
> wide; summing them counts every strip twice. `totals["naive_gross_km2"]` is
> kept only to show how large that error is.

The headline figure is `new_km2`: land that is dry today and floods under the
scenario. `gross_km2` includes the sea and the estuaries and is not land at
risk.

## Parallel Processing (Advanced)

For faster processing, use Julia's parallel processing:

```julia
using Distributed

# Add worker processes
addprocs(4)  # Use 4 CPU cores

@everywhere include("simul_flood_tiled.jl")

# Process tiles in parallel
results = @distributed (vcat) for tile in tiles
    process_single_tile(vrt_path, tile, tide_zh, surge, slr)
end
```

## Best Practices

### ✅ DO:
- Use 0.005° overlap for coastal flooding
- Process tiles sequentially first (easier debugging)
- Save individual HTML maps for presentations
- Create merged VRT for GIS analysis
- Keep tile sizes between 0.10° - 0.15°

### ❌ DON'T:
- Use zero overlap (breaks flood connectivity)
- Make tiles too small (< 0.05°) - overhead increases
- Make tiles too large (> 0.20°) - memory issues
- Process without checking tile_index.html first
- Forget to account for overlap when calculating total area

## Memory Optimization Tips

If you still run out of memory:

1. **Reduce tile size**: Use 0.05° instead of 0.15°
2. **Process sequentially**: Set `save_individual_maps=false`
3. **Use 2m DEM**: If 50cm is too detailed for your analysis
4. **Increase swap space**: System-level solution
5. **Close other applications**: Free up RAM

## Handling Edge Cases

### Ocean Tiles (No Land)
Tiles over open ocean will have zero flooded pixels:
```
Tile 5: 0 flooded pixels (ocean only) ← Expected!
```

### Boundary Artifacts
If you see linear artifacts at tile boundaries:
- Increase overlap from 0.005° to 0.01°
- Ensure tiles are processed with same datum_offset
- Check that `global_seed_downsample` is not `nothing`/`None`. Without the
  coarse whole-region pass, every tile border seeds water, which floods closed
  basins the border cuts through and leaves a rectangular stain on the map.

### Inconsistent Statistics
Use the `totals` returned by `process_tiles`:
- Don't multiply (tiles × area) - that is meaningless
- Don't sum the padded tiles either - neighbours share a strip twice the
  overlap wide, so every strip is counted twice. `totals` is computed from the
  non-overlapping cores and counts each pixel once.
- Compare `totals["gross_km2"]` with `totals["naive_gross_km2"]` to see how
  large the double-counting error would have been for your tiling.

## Example: Northern Portugal Coast

```julia
# Full workflow
bounds = (-8.90, 40.55, -8.60, 41.87)  # 150 km coastline
tiles = create_tiles(bounds, 0.15, overlap=0.005)  # ~12 tiles

results, totals = process_tiles(
    "portugal_coast_wgs84.vrt",
    tiles, 3.8, 0.6, 1.13;
    output_dir="north_portugal_tiles",
    downsample=4,   # ~2 m; the 50 cm VRT does not fit in RAM over this region
)

# Expected output:
# - one GeoTIFF per tile, cropped to its non-overlapping core
# - one HTML map per tile
# - Processing time: ~30-60 minutes
# - Total size: ~100-500 MB
# - totals["new_km2"]: newly inundated land, the headline figure
# - totals["gross_km2"]: includes the sea, not land at risk
```

## Comparison: Single vs Tiled

| Aspect | Single Region | Tiled Approach |
|--------|---------------|----------------|
| Memory | 10-20 GB | 1-3 GB per tile |
| Processing | May crash | Stable |
| HTML size | 50+ MB | 2-5 MB per tile |
| Visualization | One huge map | Multiple focused maps |
| Debugging | Difficult | Easy (per tile) |
| Parallelization | Not possible | Easy |

## When NOT to Tile

For small regions (< 20 km coastline), use single simulation:
- Espinho municipality: `(-8.70, 40.95, -8.60, 41.03)` - OK as single tile
- Ria de Aveiro only: `(-8.75, 40.55, -8.60, 40.75)` - OK as single tile

Tiling adds overhead for small areas.
