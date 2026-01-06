import rasterio
import numpy as np
import folium
from rasterio.mask import mask
from shapely.geometry import box
from skimage.morphology import reconstruction

def run_simulation_on_vrt(vrt_path, tide_zh, surge, slr, bounds):
    """
    vrt_path: Path to 'portugal_coast_wgs84.vrt'
    bounds: Tuple (min_lon, min_lat, max_lon, max_lat) to clip the analysis
    """
    
    # --- 1. PARAMETERS ---
    # DGT Datum (Cascais 1938) vs Hydrographic Zero (ZH)
    # Offset is -2.00m for Viana/Aveiro coastal zone [1]
    DATUM_OFFSET = 2.00
    
    total_water_level = tide_zh + surge + slr
    flood_threshold = total_water_level - DATUM_OFFSET
    
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

    # --- 4. VISUALIZE ---
    # Center map on the region
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles=None)
    
    folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Satellite',
        overlay=False, control=True
    ).add_to(m)

    # FIXED: Correct bounds order for ImageOverlay
    # Format: [[south, west], [north, east]]
    overlay_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
    
    # IMPROVED: Better colormap for flood visualization
    # Blue color for flooded areas (value=1), transparent for dry areas (value=0)
    def flood_colormap(x):
        if x == 0:
            return (0, 0, 0, 0)  # Transparent for no flood
        else:
            return (0, 100, 255, 200)  # Blue with alpha for flooded areas
    
    folium.raster_layers.ImageOverlay(
        image=flood_mask,
        bounds=overlay_bounds,
        opacity=0.6,
        colormap=flood_colormap,
        name="Flood Extent"
    ).add_to(m)
    
    folium.LayerControl().add_to(m)
    
    return m, flood_mask, out_transform

# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    # Define area for Ria de Aveiro (Lon Min, Lat Min, Lon Max, Lat Max)
    aveiro_bounds = (-8.75, 40.55, -8.60, 40.75) 
    
    # Define the bounding box for Espinho Municipality
    # (Lon Min, Lat Min, Lon Max, Lat Max)
    espinho_bounds = (-8.70, 40.95, -8.60, 41.03)
    espinho_aveiro_bounds = (-8.75, 40.55, -8.60, 41.03)
    # Run simulation
    map_result, flood_mask, transform = run_simulation_on_vrt(
        'portugal_coast_wgs84.vrt', 
        tide_zh=3.8,   # HAT (Highest Astronomical Tide)
        surge=0.6,     # 50-year storm surge
        slr=1.13,      # Sea level rise scenario for 2100
        bounds=espinho_aveiro_bounds
    )
    
    # Save the map
    output_file = "espinho_flood_simulation.html"
    map_result.save(output_file)
    print(f"\nMap saved to: {output_file}")
    
    # Optionally save the flood mask as a GeoTIFF for further analysis
    # (You would need to add rasterio write code here if needed)
