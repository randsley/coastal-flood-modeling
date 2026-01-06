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
        out_meta = src.meta.copy()
        
        # Squeeze to 2D array
        dem_array = out_image
        
        # Handle NoData (DGT usually uses -9999 or very small numbers)
        dem_array = np.where(dem_array < -100, 9999, dem_array)

    # --- 3. CONNECTED FLOODING ---
    # Seed the flood from the edges (assuming ocean is at the boundary)
    seed = np.copy(dem_array)
    seed[1:-1, 1:-1] = dem_array.max()
    seed = np.where(dem_array < flood_threshold, seed, dem_array)
    
    print("Calculating hydrological connectivity...")
    flooded = reconstruction(seed, dem_array, method='erosion')
    flood_mask = (flooded < flood_threshold).astype(np.uint8)

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

    # Add flood layer
    # Note: For very large areas, this might still lag the browser. 
    # Ideally, export this as a GeoTIFF and serve it, but ImageOverlay works for analysis.
    folium.raster_layers.ImageOverlay(
        image=flood_mask,
        bounds=[[bounds[2], bounds[0]], [bounds[3], bounds[1]]],
        opacity=0.6,
        colormap=lambda x: (0, 0, 255, x),
        name="Flood Extent"
    ).add_to(m)
    
    folium.LayerControl().add_to(m)
    return m

# --- EXAMPLE USAGE ---
# Define area for Ria de Aveiro (Lon Min, Lat Min, Lon Max, Lat Max)
aveiro_bounds = (-8.75, 40.55, -8.60, 40.75) 
# Define the bounding box for Espinho Municipality
# (Lon Min, Lat Min, Lon Max, Lat Max)
espinho_bounds = (-8.70, 40.95, -8.60, 41.03)

# Run
map_result = run_simulation_on_vrt(
    'portugal_coast_wgs84.vrt', 
    tide_zh=3.8,   # HAT
    surge=0.6,     # 50yr Surge
    slr=1.13,      # 2100 Scenario
    bounds=espinho_bounds
)
map_result