import os
from osgeo import gdal

# 1. SETUP PATHS
# Update this path to where your files are in Drive
input_folder = './DEM2m' 
output_vrt = 'portugal_coast_mosaic.vrt'
output_reprojected = 'portugal_coast_wgs84.vrt'

# 2. GET LIST OF FILES
# DGT files are often.tif,.asc, or.xyz. Change extension if needed.
dem_files = [os.path.join(input_folder, f) for f in os.listdir(input_folder) if f.endswith('.tif')]
print(f"Found {len(dem_files)} files.")

# 3. BUILD VIRTUAL MOSAIC (No heavy processing yet)
# This creates a small text file linking all images together
print("Building virtual mosaic...")
gdal.BuildVRT(output_vrt, dem_files)

# 4. REPROJECT TO LAT/LON (EPSG:4326)
# Google Maps/Folium needs Lat/Lon. We create a new VRT for this transformation.
print("Reprojecting to WGS84...")
gdal.Warp(output_reprojected, output_vrt, dstSRS='EPSG:4326')

print("Done! Use 'portugal_coast_wgs84.vrt' as your input file.")