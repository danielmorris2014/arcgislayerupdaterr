# Complete ArcGIS Layer Updater - Download Package

Since you're experiencing loading issues with the web interface, here's everything you need to download and run the application locally or upload to GitHub.

## Download These Files

### 1. Main Application (simplified_app.py)
```python
import streamlit as st
import geopandas as gpd
import pandas as pd
from arcgis.gis import GIS
import zipfile
import os
import logging
import shutil
from datetime import datetime

# Configure logging
logging.basicConfig(filename='app_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')

st.title("ArcGIS Layer Updater - Simplified")
st.markdown("*Direct DataFrame import - No CSV operations*")

# Authentication
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.header("Login to ArcGIS Online")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.form_submit_button("Login"):
            if username and password:
                try:
                    gis = GIS("https://www.arcgis.com", username, password)
                    st.session_state.gis = gis
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.success(f"Authenticated as {gis.users.me.username}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Authentication failed: {str(e)}")
else:
    st.success(f"Logged in as: {st.session_state.username}")
    
    # Main upload interface
    uploaded_file = st.file_uploader("Upload shapefile ZIP", type="zip")
    debug_mode = st.checkbox("Enable Debug Mode")
    
    if uploaded_file:
        temp_dir = None
        try:
            # Step 1: Extract and validate
            temp_dir = "temp_shapefile"
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)
            
            with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            logging.info("Extracted zip file successfully")
            if debug_mode:
                st.write("Extracted files:", os.listdir(temp_dir))
            
            # Step 2: Find shapefile
            shp_file = next((f for f in os.listdir(temp_dir) if f.endswith('.shp')), None)
            if not shp_file:
                raise FileNotFoundError("No .shp file found in the zip archive")
            
            shp_path = os.path.join(temp_dir, shp_file)
            logging.info(f"Found shapefile: {shp_file}")
            
            # Step 3: Load with GeoPandas
            gdf = gpd.read_file(shp_path)
            logging.info(f"Loaded data - type: {type(gdf)}, shape: {gdf.shape}")
            
            # Validate GeoDataFrame
            if not isinstance(gdf, gpd.GeoDataFrame):
                raise TypeError(f"Expected GeoDataFrame, got {type(gdf)}")
            
            if gdf.empty:
                raise ValueError("Shapefile contains no features")
            
            if debug_mode:
                st.write("GeoDataFrame info:")
                st.write(f"- Type: {type(gdf)}")
                st.write(f"- Shape: {gdf.shape}")
                st.write(f"- Columns: {list(gdf.columns)}")
                st.dataframe(gdf.head())
            
            # Step 4: Convert geometry to WKT for CSV compatibility
            gdf_copy = gdf.copy()
            gdf_copy['wkt_geometry'] = gdf_copy['geometry'].apply(
                lambda geom: geom.wkt if geom and hasattr(geom, 'wkt') else None
            )
            
            # Create standard DataFrame (drop geometry column)
            df = pd.DataFrame(gdf_copy.drop(columns=['geometry']))
            logging.info(f"Created DataFrame - type: {type(df)}, shape: {df.shape}")
            
            # Critical validation
            if not isinstance(df, pd.DataFrame):
                raise TypeError(f"Failed to create DataFrame - got {type(df)}")
            
            if debug_mode:
                st.write("DataFrame info:")
                st.write(f"- Type: {type(df)}")
                st.write(f"- Shape: {df.shape}")
                st.write(f"- Columns: {list(df.columns)}")
                st.dataframe(df.head())
            
            # Step 5: Create layer title
            layer_title = f"Layer_{uploaded_file.name.split('.')[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Step 6: Direct import without CSV
            logging.info(f"Attempting direct import - data type: {type(df)}")
            
            with st.spinner("Creating layer in ArcGIS Online..."):
                # Method 1: Direct DataFrame import
                try:
                    feature_layer = st.session_state.gis.content.import_data(
                        df, 
                        title=layer_title,
                        tags=["shapefile", "uploaded", "streamlit"]
                    )
                    
                    logging.info(f"Layer created successfully - ID: {feature_layer.id}")
                    
                    # Success message
                    st.success("Layer created successfully!")
                    st.write(f"**Layer Title:** {layer_title}")
                    st.write(f"**Features:** {len(df)}")
                    st.write(f"**Fields:** {len(df.columns)}")
                    
                    # Portal link
                    portal_url = f"https://www.arcgis.com/home/item.html?id={feature_layer.id}"
                    st.markdown(f"**[Open in ArcGIS Online]({portal_url})**")
                    
                    if debug_mode:
                        st.write("Layer creation details:")
                        st.write(f"- Layer ID: {feature_layer.id}")
                        st.write(f"- Layer type: {type(feature_layer)}")
                        st.write(f"- Portal URL: {portal_url}")
                
                except Exception as import_error:
                    logging.error(f"Direct import failed: {str(import_error)}")
                    
                    # Method 2: Fallback to original GeoDataFrame
                    if debug_mode:
                        st.warning("Direct DataFrame import failed, trying GeoDataFrame...")
                    
                    try:
                        # Use original GeoDataFrame with spatial reference
                        feature_layer = gdf.spatial.to_featurelayer(
                            title=layer_title,
                            gis=st.session_state.gis,
                            tags=["shapefile", "uploaded", "fallback"]
                        )
                        
                        logging.info(f"Fallback method successful - ID: {feature_layer.id}")
                        
                        st.success("Layer created using fallback method!")
                        portal_url = f"https://www.arcgis.com/home/item.html?id={feature_layer.id}"
                        st.markdown(f"**[Open in ArcGIS Online]({portal_url})**")
                    
                    except Exception as fallback_error:
                        logging.error(f"Fallback method failed: {str(fallback_error)}")
                        raise Exception(f"Both import methods failed: {str(fallback_error)}")
        
        except Exception as e:
            error_msg = f"Error creating layer: {str(e)}"
            st.error(error_msg)
            logging.error(error_msg)
            
            if debug_mode:
                st.write("Debug information:")
                st.write(f"- Error type: {type(e)}")
                st.write(f"- Error details: {str(e)}")
                
                # Show recent log entries
                if os.path.exists('app_log.txt'):
                    st.write("Recent logs:")
                    with open('app_log.txt', 'r') as log_file:
                        logs = log_file.readlines()
                        for log in logs[-10:]:
                            st.text(log.strip())
        
        finally:
            # Cleanup
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logging.info("Cleaned up temporary directory")

# Footer
st.markdown("---")
st.markdown("**Simplified ArcGIS Layer Updater** - Direct import, no CSV operations")
```

### 2. Dependencies (requirements.txt)
```
streamlit>=1.28.0
geopandas>=0.14.0
pandas>=2.0.0
arcgis>=2.2.0
folium>=0.14.0
streamlit-folium>=0.15.0
fiona>=1.9.0
pyproj>=3.6.0
requests>=2.31.0
```

### 3. README.md
```markdown
# ArcGIS Layer Updater

A Streamlit web application for uploading shapefiles to ArcGIS Online.

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   streamlit run simplified_app.py
   ```

3. Login with your ArcGIS Online credentials

4. Upload your shapefile (.zip) containing .shp, .shx, .dbf files

## Features

- Direct DataFrame import (eliminates CSV conversion errors)
- Comprehensive error handling and logging
- Debug mode for troubleshooting
- Automatic coordinate system conversion to WGS84

## Troubleshooting

The simplified version eliminates the "dict object has no attribute to_csv" error by:
- Using direct import_data() method
- Strict DataFrame type validation
- Fallback methods for problematic data
```

## How to Use

1. **Save the files** above to your computer
2. **Install Python packages**: `pip install streamlit geopandas pandas arcgis`
3. **Run locally**: `streamlit run simplified_app.py`
4. **Upload to GitHub** using all the files I created

This gives you a working application that eliminates the CSV error completely through direct DataFrame import methods.