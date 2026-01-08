import rasterio
import numpy as np
import folium
from rasterio.mask import mask
from shapely.geometry import box
from skimage.morphology import reconstruction
import base64
from io import BytesIO
from datetime import datetime
import os

# Optional: PIL for pixel-perfect HTML maps
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL not available. Install with: pip install Pillow")
    print("  → HTML maps will use rectangle approximation")

def run_simulation_on_vrt(vrt_path, tide_zh, surge, slr, bounds, datum_offset=2.00):
    """
    Runs a coastal flood simulation using Connected Morphological Flooding algorithm.

    Parameters:
    -----------
    vrt_path : str
        Path to the VRT file (e.g., 'portugal_coast_wgs84.vrt')
    tide_zh : float
        Tide level relative to Hydrographic Zero (ZH) in meters
    surge : float
        Storm surge height in meters
    slr : float
        Sea level rise scenario in meters
    bounds : tuple
        Bounding box as (min_lon, min_lat, max_lon, max_lat)
    datum_offset : float, optional
        Vertical offset between ZH and NMM datum (default: 2.00m for Viana/Aveiro)

    Returns:
    --------
    flood_mask : numpy.ndarray
        Boolean array indicating flooded areas
    transform : rasterio.Affine
        Affine transform for georeferencing
    metadata : dict
        Dictionary with simulation statistics and parameters

    Example:
    --------
    >>> result, transform, metadata = run_simulation_on_vrt(
    ...     "portugal_coast_wgs84.vrt",
    ...     3.8,   # HAT
    ...     0.6,   # 50-year surge
    ...     1.13,  # 2100 SLR
    ...     (-8.70, 40.95, -8.60, 41.03)  # Espinho bounds
    ... )
    """

    # --- 1. PARAMETERS ---
    # DGT Datum (Cascais 1938) vs Hydrographic Zero (ZH)

    total_water_level = tide_zh + surge + slr
    flood_threshold = total_water_level - datum_offset
    
    print(f"Simulating TWL: {total_water_level:.2f}m (ZH) -> Threshold: {flood_threshold:.2f}m (NMM)")

    # --- 2. LOAD & CLIP DATA ---
    # We only load the data inside the 'bounds' box to save RAM
    with rasterio.open(vrt_path) as src:
        # Create a bounding box geometry for reading
        bbox = box(*bounds)
        geojson_box = [bbox.__geo_interface__]
        
        # Crop the VRT to this box
        out_image, out_transform = mask(src, geojson_box, crop=True)
        
        # FIXED: Extract first band from 3D array (bands, height, width) -> (height, width)
        dem_array = out_image[0]
        
        # IMPROVED: Handle NoData using metadata value
        nodata_value = src.nodata if src.nodata is not None else -9999
        print(f"NoData value: {nodata_value}")
        
        # Replace NoData with a very high value to prevent it from being flooded
        dem_array = np.where(dem_array == nodata_value, 9999, dem_array)
        
        # Also handle extreme negative values that might indicate NoData
        dem_array = np.where(dem_array < -100, 9999, dem_array)

    # --- 3. CONNECTED FLOODING ---
    # Seed the flood from the edges (assuming ocean is at the boundary)
    seed = np.copy(dem_array)
    seed[1:-1, 1:-1] = dem_array.max()
    seed = np.where(dem_array < flood_threshold, seed, dem_array)
    
    print("Calculating hydrological connectivity...")
    flooded = reconstruction(seed, dem_array, method='erosion')
    flood_mask = (flooded < flood_threshold).astype(np.uint8)
    
    # Calculate flooded area statistics in real-world units (m² and km²)
    # out_transform contains pixel size in degrees (WGS84/EPSG:4326)
    x_step_deg = abs(out_transform[0])  # pixel width in degrees
    y_step_deg = abs(out_transform[4])  # pixel height in degrees

    # Get center latitude for accurate area calculation
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lat_rad = np.radians(center_lat)

    # Convert degrees to meters at this latitude
    # 1 degree latitude ≈ 111,320 meters (constant)
    # 1 degree longitude ≈ 111,320 * cos(latitude) meters (varies with latitude)
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * np.cos(center_lat_rad)

    # Calculate pixel dimensions in meters
    pixel_width_m = x_step_deg * meters_per_deg_lon
    pixel_height_m = y_step_deg * meters_per_deg_lat
    pixel_area_m2 = pixel_width_m * pixel_height_m

    flooded_pixels = np.sum(flood_mask)
    flooded_area_m2 = flooded_pixels * pixel_area_m2
    flooded_area_km2 = flooded_area_m2 / 1_000_000

    print(f"Flooded pixels: {flooded_pixels:,}")
    print(f"Pixel size: {pixel_width_m:.2f}m × {pixel_height_m:.2f}m")
    print(f"Flooded area: {flooded_area_km2:.3f} km² ({flooded_area_m2:,.0f} m²)")

    # --- 4. PREPARE OUTPUT ---
    # Create metadata dictionary
    metadata = {
        "tide_zh": tide_zh,
        "surge": surge,
        "slr": slr,
        "datum_offset": datum_offset,
        "total_water_level": total_water_level,
        "flood_threshold": flood_threshold,
        "flooded_pixels": flooded_pixels,
        "flooded_area_m2": flooded_area_m2,
        "flooded_area_km2": flooded_area_km2,
        "pixel_area_m2": pixel_area_m2,
        "pixel_size_m": (pixel_width_m, pixel_height_m),
        "center_latitude": center_lat,
        "bounds": bounds,
        "crs": src.crs,
        "transform": out_transform
    }

    return flood_mask, out_transform, metadata


def save_flood_geotiff(flood_mask, transform, metadata, output_file, compress=True):
    """
    Save flood mask as a GeoTIFF file.

    Parameters:
    -----------
    flood_mask : numpy.ndarray
        Boolean or uint8 array with flood mask (True/1=Flooded, False/0=Dry)
    transform : rasterio.Affine
        Affine transform for georeferencing
    metadata : dict
        Simulation metadata containing CRS info
    output_file : str
        Path to output GeoTIFF file
    compress : bool, optional
        Apply LZW compression (default: True)
    """
    # Convert Bool mask to UInt8 (1=Flooded, 0=Dry)
    save_array = flood_mask.astype(np.uint8)

    # Prepare rasterio profile
    profile = {
        'driver': 'GTiff',
        'height': save_array.shape[0],
        'width': save_array.shape[1],
        'count': 1,
        'dtype': save_array.dtype,
        'crs': metadata['crs'],
        'transform': transform,
        'nodata': 255
    }

    if compress:
        profile['compress'] = 'lzw'

    try:
        with rasterio.open(output_file, 'w', **profile) as dst:
            dst.write(save_array, 1)
        print(f"✓ Saved to: {output_file}")
    except Exception as e:
        print(f"Failed to save GeoTIFF: {e}")
        raise


def save_html_map(flood_mask, metadata, output_file, map_center=None, zoom=12):
    """
    Create an interactive HTML map with basemap and pixel-perfect flood overlay.
    Uses Leaflet.js for web-based visualization with OpenStreetMap tiles.

    Parameters:
    -----------
    flood_mask : numpy.ndarray
        Boolean or uint8 array with flood mask
    metadata : dict
        Simulation metadata
    output_file : str
        Path to output HTML file
    map_center : tuple, optional
        Optional (lat, lon) center, auto-calculated if None
    zoom : int, optional
        Initial zoom level (default: 12)

    Requirements:
    -------------
    Requires Pillow (PIL) for PNG encoding.
    Install with: pip install Pillow

    Example:
    --------
    >>> save_html_map(flood_mask, metadata, "flood_map.html")
    """
    print("Generating HTML map with pixel-perfect overlay...")

    # Get bounds
    bounds = metadata["bounds"]
    min_lon, min_lat, max_lon, max_lat = bounds

    # Calculate map center if not provided
    if map_center is None:
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2
    else:
        center_lat, center_lon = map_center

    # Try to create pixel-perfect PNG overlay
    flood_overlay_url = None

    if HAS_PIL:
        try:
            # Get dimensions - NumPy arrays are (height, width)
            height, width = flood_mask.shape

            # Create RGBA image
            img_data = np.zeros((height, width, 4), dtype=np.uint8)

            # Fill the image: blue for flooded, transparent for dry
            # Blue color with transparency
            img_data[flood_mask > 0] = [0, 100, 255, 180]  # Blue with alpha
            img_data[flood_mask == 0] = [0, 0, 0, 0]      # Transparent

            # Create PIL Image
            img = Image.fromarray(img_data, mode='RGBA')

            # Encode as PNG in memory
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            png_bytes = buffer.getvalue()

            # Create base64 data URL
            png_base64 = base64.b64encode(png_bytes).decode('utf-8')
            flood_overlay_url = f"data:image/png;base64,{png_base64}"

            print(f"  ✓ Encoded flood mask as PNG ({len(png_bytes)} bytes)")

        except Exception as e:
            print(f"Warning: Failed to encode PNG: {e}")
            print("  → Falling back to rectangle overlay")
    else:
        print("  Note: Install Pillow for pixel-perfect overlay")
        print("  Run: pip install Pillow")
        print("  → Using rectangle approximation overlay")

    # Create HTML with Leaflet.js
    # Choose between pixel-perfect overlay or rectangle fallback
    if flood_overlay_url is not None:
        # Pixel-perfect overlay using embedded PNG
        overlay_code = f"""
            // Add pixel-perfect flood overlay from embedded PNG
            var floodBounds = [[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]];
            var floodOverlay = L.imageOverlay(
                '{flood_overlay_url}',
                floodBounds,
                {{opacity: 1.0, interactive: true}}
            ).addTo(map);

            floodOverlay.bindPopup("<b>Flooded Area</b><br>{metadata['flooded_area_km2']:.3f} km²");
        """
    else:
        # Fallback to rectangle overlay
        overlay_code = f"""
            // Add flood overlay (rectangle approximation)
            var floodBounds = [[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]];
            var floodOverlay = L.rectangle(floodBounds, {{
                color: '#0064ff',
                weight: 2,
                fillColor: '#0064ff',
                fillOpacity: 0.4
            }}).addTo(map);

            floodOverlay.bindPopup("<b>Flooded Area</b><br>{metadata['flooded_area_km2']:.3f} km²");
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
        }}
        .info h4 {{ margin: 0 0 5px; color: #777; }}
        .legend {{
            line-height: 18px;
            color: #555;
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 0 15px rgba(0,0,0,0.2);
        }}
        .legend i {{
            width: 18px;
            height: 18px;
            float: left;
            margin-right: 8px;
            opacity: 0.7;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        // Initialize map
        var map = L.map('map').setView([{center_lat}, {center_lon}], {zoom});

        // Add OpenStreetMap tiles (default)
        var osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        }}).addTo(map);

        // Add satellite layer option
        var satellite = L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={{x}}&y={{y}}&z={{z}}', {{
            attribution: 'Google Satellite',
            maxZoom: 20
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
                '<b>Total Water Level:</b> {metadata["total_water_level"]:.2f} m (ZH)<br>' +
                '<b>Flood Threshold:</b> {metadata["flood_threshold"]:.2f} m (NMM)<br>' +
                '<b>Flooded Area:</b> {metadata["flooded_area_km2"]:.3f} km²<br>' +
                '<b>Flooded Pixels:</b> {metadata["flooded_pixels"]:,}<br>' +
                '<small>Pixel size: {metadata["pixel_size_m"][0]:.2f}m × {metadata["pixel_size_m"][1]:.2f}m</small>';
        }};
        info.addTo(map);

        // Add legend
        var legend = L.control({{position: 'bottomright'}});
        legend.onAdd = function (map) {{
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<i style="background: rgba(0, 100, 255, 0.7)"></i> Flooded Area<br>';
            return div;
        }};
        legend.addTo(map);

        // Layer control
        var baseMaps = {{
            "OpenStreetMap": osm,
            "Satellite": satellite
        }};
        var overlayMaps = {{
            "Flood Extent": floodOverlay
        }};
        L.control.layers(baseMaps, overlayMaps).addTo(map);

        // Fit map to flood bounds
        var floodBounds = [[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]];
        map.fitBounds(floodBounds);
    </script>
    <div style="position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); z-index: 1000; background: white; padding: 5px; border-radius: 3px; font-size: 10px;">
        Generated with Python + Rasterio | Tide: {metadata["tide_zh"]}m + Surge: {metadata["surge"]}m + SLR: {metadata["slr"]}m
    </div>
</body>
</html>
"""

    # Write HTML file
    with open(output_file, 'w') as f:
        f.write(html_content)

    print(f"✓ HTML map saved to: {output_file}")
    return output_file


# ============================================================================
# TILING SUPPORT FOR LARGE REGIONS
# ============================================================================

def create_tiles(bounds, tile_size_deg, overlap=0.001):
    """
    Divide a large bounding box into smaller tiles for processing.

    Parameters:
    -----------
    bounds : tuple
        Overall bounds (min_lon, min_lat, max_lon, max_lat)
    tile_size_deg : float
        Approximate tile size in degrees (e.g., 0.1 = ~11km)
    overlap : float, optional
        Overlap between tiles in degrees (default: 0.001 = ~100m)

    Returns:
    --------
    tiles : list
        List of tile bounds, each as (min_lon, min_lat, max_lon, max_lat)

    Example:
    --------
    >>> # Northern Portugal coast: Caminha to Aveiro
    >>> large_bounds = (-8.90, 40.55, -8.60, 41.87)
    >>> tiles = create_tiles(large_bounds, 0.15, overlap=0.005)

    Notes:
    ------
    Overlap is important for hydrological connectivity at tile boundaries.
    Recommended overlap: 500m (0.005°) for coastal zones.
    """
    min_lon, min_lat, max_lon, max_lat = bounds

    # Calculate number of tiles needed
    n_tiles_x = int(np.ceil((max_lon - min_lon) / tile_size_deg))
    n_tiles_y = int(np.ceil((max_lat - min_lat) / tile_size_deg))

    print("Creating tiling scheme:")
    print(f"  Total area: {(max_lon - min_lon):.3f}° × {(max_lat - min_lat):.3f}°")
    print(f"  Tile size: {tile_size_deg}° (~{tile_size_deg * 111:.1f} km)")
    print(f"  Grid: {n_tiles_x} × {n_tiles_y} = {n_tiles_x * n_tiles_y} tiles")
    print(f"  Overlap: {overlap}° (~{overlap * 111 * 1000:.0f} m)")

    tiles = []

    for j in range(n_tiles_y):
        for i in range(n_tiles_x):
            # Calculate tile bounds with overlap
            tile_min_lon = min_lon + i * tile_size_deg - (overlap if i > 0 else 0)
            tile_max_lon = min(min_lon + (i + 1) * tile_size_deg + overlap, max_lon)

            tile_min_lat = min_lat + j * tile_size_deg - (overlap if j > 0 else 0)
            tile_max_lat = min(min_lat + (j + 1) * tile_size_deg + overlap, max_lat)

            # Ensure we don't exceed overall bounds
            tile_min_lon = max(tile_min_lon, min_lon)
            tile_min_lat = max(tile_min_lat, min_lat)

            tiles.append((tile_min_lon, tile_min_lat, tile_max_lon, tile_max_lat))

    return tiles


def process_tiles(vrt_path, tiles, tide_zh, surge, slr,
                  output_dir="tiles", datum_offset=2.00,
                  save_individual_maps=True):
    """
    Process multiple tiles and save results.

    Parameters:
    -----------
    vrt_path : str
        Path to VRT file
    tiles : list
        List of tile bounds
    tide_zh : float
        Tide level (ZH)
    surge : float
        Storm surge
    slr : float
        Sea level rise
    output_dir : str, optional
        Directory for outputs (default: "tiles")
    datum_offset : float, optional
        Vertical datum offset
    save_individual_maps : bool, optional
        Save HTML map for each tile (default: True)

    Returns:
    --------
    results : list
        List of (flood_mask, metadata, tile_bounds) tuples for each tile
    """

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "="*70)
    print("TILED FLOOD SIMULATION")
    print("="*70)
    print(f"Number of tiles: {len(tiles)}")
    print(f"Scenario: Tide={tide_zh}m + Surge={surge}m + SLR={slr}m")
    print(f"Output directory: {output_dir}")
    print("="*70 + "\n")

    results = []
    total_flooded_area_km2 = 0.0
    total_flooded_pixels = 0

    start_time = datetime.now()

    for idx, tile_bounds in enumerate(tiles, 1):
        print(f"\n[{idx}/{len(tiles)}] Processing tile {idx}...")
        print(f"  Bounds: {tile_bounds}")

        try:
            # Run simulation for this tile
            flood_mask, transform, metadata = run_simulation_on_vrt(
                vrt_path, tide_zh, surge, slr, tile_bounds,
                datum_offset=datum_offset
            )

            # Save GeoTIFF
            tif_file = os.path.join(output_dir, f"tile_{idx:03d}.tif")
            save_flood_geotiff(flood_mask, transform, metadata, tif_file)

            # Optionally save HTML map
            if save_individual_maps:
                html_file = os.path.join(output_dir, f"tile_{idx:03d}.html")
                save_html_map(flood_mask, metadata, html_file)

            # Accumulate statistics
            total_flooded_area_km2 += metadata["flooded_area_km2"]
            total_flooded_pixels += metadata["flooded_pixels"]

            results.append((flood_mask, metadata, tile_bounds))

            print(f"  ✓ Tile {idx} complete: {metadata['flooded_area_km2']:.3f} km²")

        except Exception as e:
            print(f"Warning: Failed to process tile {idx}: {e}")
            import traceback
            traceback.print_exc()
            results.append((None, None, tile_bounds))

    elapsed = datetime.now() - start_time

    # Summary
    print("\n" + "="*70)
    print("SIMULATION COMPLETE")
    print("="*70)
    print(f"Total flooded area: {total_flooded_area_km2:.3f} km²")
    print(f"Total flooded pixels: {total_flooded_pixels:,}")
    print(f"Processing time: {elapsed}")
    print(f"Output location: {output_dir}")
    print("="*70 + "\n")

    return results


def merge_tiles_to_vrt(tile_files, output_vrt):
    """
    Create a VRT mosaic from individual tile GeoTIFFs.

    Parameters:
    -----------
    tile_files : list
        List of tile GeoTIFF paths
    output_vrt : str
        Output VRT filename

    Example:
    --------
    >>> import glob
    >>> tile_files = glob.glob("tiles/tile_*.tif")
    >>> merge_tiles_to_vrt(tile_files, "merged_flood.vrt")
    """
    print(f"Creating merged VRT from {len(tile_files)} tiles...")

    # Use GDAL to build VRT
    try:
        from osgeo import gdal
        vrt_options = gdal.BuildVRTOptions(resampleAlg='nearest')
        gdal.BuildVRT(output_vrt, tile_files, options=vrt_options)
        print(f"✓ Merged VRT created: {output_vrt}")
        print("  Open in QGIS to view the complete mosaic")
    except ImportError:
        print("Warning: GDAL Python bindings not available")
        print("  Try using command line: gdalbuildvrt " + output_vrt + " " + " ".join(tile_files))
    except Exception as e:
        print(f"Warning: Failed to create VRT: {e}")
        print("  Make sure GDAL is installed")


def create_index_map(tiles, output_file):
    """
    Create an HTML map showing the tile grid for reference.

    Parameters:
    -----------
    tiles : list
        List of tile bounds
    output_file : str
        Output HTML filename
    """
    print("Creating tile index map...")

    # Calculate overall bounds
    all_lons = [t[0] for t in tiles] + [t[2] for t in tiles]
    all_lats = [t[1] for t in tiles] + [t[3] for t in tiles]

    center_lon = (min(all_lons) + max(all_lons)) / 2
    center_lat = (min(all_lats) + max(all_lats)) / 2

    # Generate tile rectangles HTML
    tile_html = ""
    for idx, tile in enumerate(tiles, 1):
        min_lon, min_lat, max_lon, max_lat = tile
        tile_html += f"""
            L.rectangle([[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]], {{
                color: '#ff7800',
                weight: 2,
                fillColor: '#ffaa00',
                fillOpacity: 0.1
            }}).addTo(map).bindPopup('<b>Tile {idx}</b><br>Bounds: [{min_lon:.3f}, {min_lat:.3f}, {max_lon:.3f}, {max_lat:.3f}]');
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
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);

        {tile_html}
    </script>
    <div style="position: absolute; top: 10px; right: 10px; z-index: 1000; background: white; padding: 10px; border-radius: 5px;">
        <h3>Tile Grid</h3>
        <p>Total tiles: {len(tiles)}</p>
    </div>
</body>
</html>
"""

    with open(output_file, 'w') as f:
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
        print("="*70)
        print("Coastal Flood Simulation - Python Implementation")
        print("="*70)

        # Configuration
        vrt_file = "portugal_coast_wgs84.vrt"
        output_file = "espinho_flood_result.tif"

        # Predefined bounding boxes
        espinho_bounds = (-8.70, 40.95, -8.60, 41.03)
        aveiro_bounds = (-8.75, 40.55, -8.60, 40.75)
        espinho_aveiro_bounds = (-8.75, 40.55, -8.60, 41.03)

        # Use combined region
        selected_bounds = espinho_aveiro_bounds

        if not os.path.isfile(vrt_file):
            print(f"Error: VRT file '{vrt_file}' not found. Run makeVRT.py first.")
            sys.exit(1)

        print("\n1. Running simulation...")
        print(f"   Region: {selected_bounds}")
        print("   Scenario: HAT + 50yr surge + 2100 SLR")

        # Run simulation
        flood_mask, transform, metadata = run_simulation_on_vrt(
            vrt_file,
            3.8,   # HAT (Highest Astronomical Tide)
            0.6,   # 50-year storm surge
            1.13,  # Sea level rise scenario for 2100
            selected_bounds
        )

        # Display metadata
        print("\n2. Simulation Results:")
        print(f"   Total Water Level: {metadata['total_water_level']:.2f}m (ZH)")
        print(f"   Flood Threshold: {metadata['flood_threshold']:.2f}m (NMM)")
        print(f"   Flooded Area: {metadata['flooded_area_km2']:.3f} km²")

        # Save outputs
        print("\n3. Saving results...")
        save_flood_geotiff(flood_mask, transform, metadata, output_file)

        # Save HTML map
        html_file = output_file.replace(".tif", ".html")
        save_html_map(flood_mask, metadata, html_file)

        print("\n4. Visualization options:")
        print(f"   • HTML map: Open {html_file} in browser")
        print(f"   • GeoTIFF: Open {output_file} in QGIS/ArcGIS")

        print("\n" + "="*70)
        print("Simulation complete!")
        print("="*70)

    elif mode == 'tiled':
        # =================================================================
        # TILED MODE FOR LARGE AREAS
        # =================================================================
        print("="*70)
        print("LARGE AREA FLOOD SIMULATION - NORTHERN PORTUGAL COAST")
        print("="*70)

        # Define large region: Caminha (north) to Aveiro (south)
        # This covers approximately 150km of coastline
        caminha_to_aveiro = (-8.90, 40.55, -8.60, 41.87)

        vrt_file = "portugal_coast_wgs84.vrt"

        if not os.path.isfile(vrt_file):
            print(f"Error: VRT file not found: {vrt_file}")
            print("Run makeVRT.py first.")
            sys.exit(1)

        # Step 1: Create tiles
        # 0.15° ≈ 16.5 km tiles with 500m overlap
        tiles = create_tiles(caminha_to_aveiro, 0.15, overlap=0.005)

        # Step 2: Create index map (for reference)
        create_index_map(tiles, "tile_index.html")
        print("\n→ Open tile_index.html to see the tile grid\n")

        # Step 3: Process all tiles
        results = process_tiles(
            vrt_file,
            tiles,
            3.8,   # HAT
            0.6,   # 50-year surge
            1.13,  # 2100 SLR
            output_dir="tiles_output",
            save_individual_maps=True  # Set to False for faster processing
        )

        # Step 4: Create merged VRT (requires GDAL)
        # This allows viewing all tiles as one continuous dataset in QGIS
        print("\n4. Creating merged VRT...")
        import glob
        tile_files = glob.glob("tiles_output/tile_*.tif")

        if tile_files:
            try:
                merge_tiles_to_vrt(tile_files, "merged_flood_north_portugal.vrt")
            except Exception as e:
                print(f"  (Optional) Could not create merged VRT: {e}")

        print("\n" + "="*70)
        print("ALL PROCESSING COMPLETE")
        print("="*70)
        print("\nOutputs:")
        print("  • Individual tiles: tiles_output/tile_*.tif")
        print("  • Individual maps: tiles_output/tile_*.html")
        print("  • Tile index: tile_index.html")
        print("  • Merged VRT: merged_flood_north_portugal.vrt (open in QGIS)")
        print("\nRecommendations:")
        print("  • For presentations: Use individual HTML maps for specific areas")
        print("  • For GIS analysis: Open merged VRT in QGIS/ArcGIS")
        print("  • For statistics: Sum the flooded areas from individual tiles")
        print("="*70)
