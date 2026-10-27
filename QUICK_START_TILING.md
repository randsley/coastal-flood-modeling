# Quick Start: Tiling for Large Areas

## Use Case: Northern Portugal Coast (Caminha to Aveiro)

### Step 1: Run the Tiled Simulation

```bash
julia simul_flood_tiled.jl     # writes tiles_output_julia/
python Simul_tiled.py          # writes tiles_output/
```

That's it! The script will automatically:
- ✅ Split the region into manageable tiles (18 at the default 0.15°)
- ✅ Run one coarse whole-region connectivity pass, so tile borders only admit water where water really reaches
- ✅ Process each tile with flood simulation, then crop it to its non-overlapping core
- ✅ Save classified GeoTIFFs (0 dry, 1 newly inundated land, 2 baseline water) and HTML maps
- ✅ Create a merged VRT for QGIS
- ✅ Report totals with every pixel counted once

The headline number is **newly inundated land**: the scenario extent minus the
water that is already there today. The gross extent includes the Atlantic and
the Ria de Aveiro and is not land at risk.

### Step 2: View Results

**Option A: Individual HTML Maps**
```bash
# Open in browser - great for presentations
start tiles_output/tile_001.html
start tiles_output/tile_002.html
# etc.
```

**Option B: Tile Index Map**
```bash
# See where each tile is located
start tile_index.html
```

**Option C: Merged View in QGIS**
```
1. Open QGIS
2. Layer → Add Layer → Add Raster Layer
3. Select: merged_flood_north_portugal.vrt
4. View entire coast as one seamless layer
```

### Step 3: Customize for Your Region

Edit `simul_flood_tiled.jl` to change:

```julia
# Define your bounding box
my_bounds = (min_lon, min_lat, max_lon, max_lat)

# Adjust tile size if needed (default: 0.15° ≈ 16.5 km)
tiles = create_tiles(my_bounds, 0.15, overlap=0.005)

# Change scenario parameters. `results, totals` - use `totals`, not a sum
# over the per-tile figures.
results, totals = process_tiles(vrt_file, tiles,
    4.2,   # Different tide level
    0.8,   # Different surge
    1.5;   # Different SLR
    downsample=4,            # ~2 m from the 50 cm VRT
    baseline_tide_zh=3.8,    # defaults to the scenario tide
)
println(totals["new_km2"])   # newly inundated land
```

## Quick Reference Table

At `downsample=4` (~2 m from the 50 cm VRT):

| Region Size | Tile Size | Number of Tiles | Memory/Tile | Total Time |
|-------------|-----------|-----------------|-------------|------------|
| 50 km coast | 0.15° | ~6 tiles | ~1 GB | ~6 min |
| 100 km coast | 0.15° | ~12 tiles | ~1 GB | ~12 min |
| 150 km coast | 0.15° | 18 tiles | ~1 GB | ~17 min |
| 200 km coast | 0.15° | ~24 tiles | ~1 GB | ~25 min |

Add a few minutes for the one-off coarse whole-region connectivity pass. At
native 50 cm (`downsample=1`) a 0.15° tile is ~1.1 × 10⁹ pixels and needs well
over 10 GB, so plan on a coarser grid or smaller tiles.

## Common Regions (Pre-configured)

Copy these bounding boxes into your script:

```julia
# Northern Portugal Coast (Caminha to Aveiro) - ~150 km
caminha_to_aveiro = (-8.90, 40.55, -8.60, 41.87)

# Central Coast (Aveiro to Figueira da Foz) - ~70 km
aveiro_to_figueira = (-8.90, 40.10, -8.75, 40.70)

# Porto Metropolitan Area - ~40 km
porto_metro = (-8.75, 41.00, -8.60, 41.25)

# Entire Northwest Coast (Viana do Castelo to Peniche) - ~250 km
northwest_coast = (-9.40, 39.35, -8.60, 41.90)
```

## Troubleshooting

**Problem**: "Out of memory" error
```julia
# Solution: Use smaller tiles
tiles = create_tiles(bounds, 0.10, overlap=0.005)  # 11 km instead of 16.5 km
```

**Problem**: "Out of memory" even with small tiles
```julia
# Solution: read a coarser grid. 4 means every 4th pixel, so 1/16 the memory.
process_tiles(..., downsample=4)
```

**Problem**: Linear artifacts at tile boundaries
```julia
# Solution: increase overlap, and keep the coarse whole-region seeding pass on
tiles = create_tiles(bounds, 0.15, overlap=0.01)  # 1 km instead of 500m
process_tiles(..., global_seed_downsample=16)     # the default; `nothing` disables
```

**Problem**: Rectangular patches of "flood" inland
```julia
# Cause: tile borders seeding closed basins they cut through.
# Solution: leave global_seed_downsample at its default (16), or lower it for
# a finer connectivity pass.
process_tiles(..., global_seed_downsample=8)
```

**Problem**: Takes too long
```julia
# Solution: Disable individual HTML maps
process_tiles(..., save_individual_maps=false)  # Only save GeoTIFFs
```

**Problem**: GDAL VRT merge fails
```
# Solution: Manual merge with GDAL command line
gdalbuildvrt output.vrt tiles_output/tile_*.tif
```

## Output File Structure

After running the tiled simulation:

```
.
├── simul_flood_tiled.jl          # Main script
├── tile_index.html                # Tile grid visualization
├── merged_flood_north_portugal.vrt # Merged mosaic (no overlapping pixels)
└── tiles_output/
    ├── tile_001.tif               # GeoTIFF, cropped to its core
    ├── tile_001.html              # Interactive map
    ├── tile_002.tif
    ├── tile_002.html
    ├── ...
    ├── tile_018.tif
    └── tile_018.html
```

Tiles are numbered from the south-west corner of the bounding box, west to east
within a row, then south to north.

## Performance Tips

1. **Start small**: Test with 1-2 tiles first before processing all
2. **Monitor memory**: Watch Task Manager during first tile
3. **Use SSD**: Store DEMs and outputs on fast storage
4. **Close applications**: Free up RAM before large runs
5. **Parallel processing**: Add `using Distributed; addprocs(4)` for multi-core

## When NOT to Use Tiling

✅ **Use tiling for:**
- Caminha to Aveiro (150 km)
- Porto to Lisbon (250 km)
- Entire coastline (>500 km)

❌ **Don't use tiling for:**
- Single municipality (Espinho, Matosinhos)
- Small bays (Ria de Aveiro only)
- Test runs (<20 km coast)

For small areas, use `simul_flood.jl` directly - it's simpler!
