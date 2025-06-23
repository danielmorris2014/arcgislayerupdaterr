import streamlit as st
import pandas as pd
import geopandas as gpd
from arcgis.gis import GIS
from arcgis.features import FeatureLayer, FeatureLayerCollection
import zipfile
import tempfile
import os
import shutil
from datetime import datetime
import json
import folium
from streamlit_folium import st_folium
# import fiona  # Removed due to system dependency issues
import warnings
warnings.filterwarnings('ignore')

# Page configuration
st.set_page_config(
    page_title="ArcGIS Layer Manager",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def authenticate():
    """Handle ArcGIS Online authentication"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        st.header("🔐 ArcGIS Online Authentication")
        
        col1, col2 = st.columns(2)
        with col1:
            username = st.text_input("Username", key="auth_username")
        with col2:
            password = st.text_input("Password", type="password", key="auth_password")
        
        if st.button("Login", type="primary"):
            if username and password:
                try:
                    with st.spinner("Authenticating..."):
                        gis = GIS("https://www.arcgis.com", username, password)
                        st.session_state.gis = gis
                        st.session_state.authenticated = True
                        st.session_state.username = username
                        st.success(f"Successfully authenticated as {gis.users.me.username}")
                        st.rerun()
                except Exception as e:
                    st.error(f"Authentication failed: {str(e)}")
            else:
                st.warning("Please enter both username and password")
        
        return False
    
    return True

def get_feature_layers(username):
    """Get user's existing feature layers"""
    try:
        search_results = st.session_state.gis.content.search(
            query="owner:" + username,
            item_type="Feature Service",
            max_items=100
        )
        return search_results
    except Exception as e:
        st.error(f"Error retrieving layers: {str(e)}")
        return []

def get_web_maps(username):
    """Get user's existing web maps"""
    try:
        search_results = st.session_state.gis.content.search(
            query="owner:" + username,
            item_type="Web Map",
            max_items=100
        )
        return search_results
    except Exception as e:
        st.error(f"Error retrieving web maps: {str(e)}")
        return []

def get_layer_preview_data(layer_id, max_features=10):
    """Get preview data for a layer"""
    try:
        layer_item = st.session_state.gis.content.get(layer_id)
        layer_collection = FeatureLayerCollection.fromitem(layer_item)
        feature_layer = layer_collection.layers[0]
        
        # Query limited features
        feature_set = feature_layer.query(return_count_only=False, result_record_count=max_features)
        
        if feature_set.features:
            # Convert to DataFrame
            df = feature_set.sdf
            
            # Get layer info
            layer_info = {
                'title': layer_item.title,
                'feature_count': feature_layer.query(return_count_only=True),
                'geometry_type': feature_layer.properties.geometryType,
                'fields': [field['name'] for field in feature_layer.properties.fields]
            }
            
            return df, layer_info
        else:
            return None, None
            
    except Exception as e:
        st.error(f"Error loading layer preview: {str(e)}")
        return None, None

def validate_layer_compatibility(layers):
    """Validate that layers are compatible for merging"""
    if len(layers) < 2:
        return False, "At least 2 layers are required for merging"
    
    try:
        geometry_types = set()
        for layer in layers:
            layer_collection = FeatureLayerCollection.fromitem(layer)
            feature_layer = layer_collection.layers[0]
            geometry_types.add(feature_layer.properties.geometryType)
        
        if len(geometry_types) > 1:
            return False, f"Layers have different geometry types: {', '.join(geometry_types)}"
        
        return True, "Layers are compatible for merging"
        
    except Exception as e:
        return False, f"Error validating layer compatibility: {str(e)}"

def create_layer_map(df, layer_title):
    """Create a folium map for layer preview"""
    try:
        if df is None or len(df) == 0:
            return None
        
        # Check if SHAPE column exists and has geometry
        if 'SHAPE' not in df.columns:
            return None
            
        # Convert to GeoDataFrame
        gdf = df.set_geometry('SHAPE')
        
        # Calculate center point
        bounds = gdf.total_bounds
        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2
        
        # Create map
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=10,
            tiles='OpenStreetMap'
        )
        
        # Add features to map
        for idx, row in gdf.iterrows():
            if row.geometry is not None:
                # Create popup content
                popup_content = f"<b>{layer_title}</b><br>"
                for col in df.columns:
                    if col not in ['SHAPE', 'geometry'] and pd.notna(row[col]):
                        popup_content += f"{col}: {row[col]}<br>"
                
                # Add geometry to map
                folium.GeoJson(
                    row.geometry.__geo_interface__,
                    popup=popup_content,
                    tooltip=f"Feature {idx + 1}"
                ).add_to(m)
        
        return m
        
    except Exception as e:
        st.warning(f"Could not create map visualization: {str(e)}")
        return None

def preview_layer_data(layer_item, max_features=10):
    """Display layer data preview with map and table"""
    st.subheader(f"📊 Preview: {layer_item.title}")
    
    with st.spinner("Loading layer preview..."):
        df, layer_info = get_layer_preview_data(layer_item.id, max_features)
    
    if df is not None and layer_info is not None:
        # Layer information
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Features", layer_info['feature_count'])
        with col2:
            st.metric("Geometry Type", layer_info['geometry_type'])
        with col3:
            st.metric("Preview Records", len(df))
        
        # Tabbed view for data and map
        tab1, tab2 = st.tabs(["📋 Attribute Table", "🗺️ Map View"])
        
        with tab1:
            # Display attribute table
            display_df = df.drop(columns=['SHAPE', 'geometry'], errors='ignore')
            if len(display_df.columns) > 0:
                st.dataframe(display_df, use_container_width=True)
            else:
                st.info("No attribute data to display")
            
            # Field information
            with st.expander("Field Information"):
                field_info = pd.DataFrame({
                    'Field Name': layer_info['fields'],
                    'Data Type': [df[field].dtype if field in df.columns else 'Unknown' 
                                 for field in layer_info['fields']]
                })
                st.dataframe(field_info, use_container_width=True)
        
        with tab2:
            # Display map
            if 'SHAPE' in df.columns:
                layer_map = create_layer_map(df, layer_item.title)
                if layer_map:
                    st_folium(layer_map, width=700, height=400)
                else:
                    st.info("Map visualization not available for this layer")
            else:
                st.info("No spatial data available for map display")
        
        return True
    else:
        st.warning("No data available for preview")
        return False

def validate_zip_file(zip_file):
    """Validate that zip file contains shapefile components"""
    required_extensions = ['.shp', '.shx', '.dbf']
    
    try:
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            
            # Check for required shapefile components
            extensions_found = set()
            for file_name in file_list:
                _, ext = os.path.splitext(file_name.lower())
                if ext in required_extensions:
                    extensions_found.add(ext)
            
            missing = set(required_extensions) - extensions_found
            if missing:
                return False, f"Missing required files: {', '.join(missing)}"
            
            return True, "Valid shapefile archive"
    
    except Exception as e:
        return False, f"Error reading zip file: {str(e)}"

def extract_and_load_shapefile(zip_file):
    """Extract zip file and load shapefile"""
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Extract zip file
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find shapefile
        shp_file = None
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.lower().endswith('.shp'):
                    shp_file = os.path.join(root, file)
                    break
            if shp_file:
                break
        
        if not shp_file:
            raise Exception("No .shp file found in the archive")
        
        # Load with geopandas
        gdf = gpd.read_file(shp_file)
        
        return gdf, temp_dir
    
    except Exception as e:
        # Clean up on error
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise e

def view_content():
    """Display user's existing content with enhanced UI and preview capabilities"""
    st.header("📋 Your ArcGIS Content")
    
    # Feature Layers section with enhanced UI
    with st.expander("📊 Feature Layers", expanded=True):
        feature_layers = get_feature_layers(st.session_state.username)
        
        if feature_layers:
            layer_data = []
            for layer in feature_layers:
                # Get FeatureServer URL
                try:
                    layer_collection = FeatureLayerCollection.fromitem(layer)
                    feature_server_url = layer_collection.url
                except:
                    feature_server_url = "URL not available"
                
                layer_data.append({
                    "Title": layer.title,
                    "ID": layer.id,
                    "Type": layer.type,
                    "Owner": layer.owner,
                    "Created": datetime.fromtimestamp(layer.created/1000).strftime('%Y-%m-%d'),
                    "FeatureServer URL": feature_server_url
                })
            
            df = pd.DataFrame(layer_data)
            st.dataframe(df, use_container_width=True)
            
            # Layer actions
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📥 Export Layer List as CSV"):
                    csv_data = df.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv_data,
                        file_name=f"arcgis_layers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
            
            with col2:
                # Layer preview selection
                layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
                selected_preview_key = st.selectbox(
                    "Select layer to preview",
                    options=[""] + list(layer_options.keys()),
                    help="Choose a layer to view its data and spatial extent"
                )
            
            # Display layer preview
            if selected_preview_key:
                selected_layer = layer_options[selected_preview_key]
                st.info("Select a layer to preview its data before proceeding with any operations.")
                preview_layer_data(selected_layer)
                
        else:
            st.info("No feature layers found in your account")
    
    # Web Maps section
    with st.expander("🗺️ Web Maps"):
        web_maps = get_web_maps(st.session_state.username)
        
        if web_maps:
            map_data = []
            for web_map in web_maps:
                map_data.append({
                    "Title": web_map.title,
                    "ID": web_map.id,
                    "Owner": web_map.owner,
                    "Created": datetime.fromtimestamp(web_map.created/1000).strftime('%Y-%m-%d')
                })
            
            df_maps = pd.DataFrame(map_data)
            st.dataframe(df_maps, use_container_width=True)
        else:
            st.info("No web maps found in your account")

def update_existing_layer():
    """Update an existing feature layer with enhanced UI and preview"""
    st.header("🔄 Update Existing Layer")
    
    feature_layers = get_feature_layers(st.session_state.username)
    
    if not feature_layers:
        st.warning("No feature layers found in your account")
        return
    
    # Layer selection with preview
    with st.expander("📋 Select Layer to Update", expanded=True):
        layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
        selected_layer_key = st.selectbox(
            "Select layer to update",
            options=list(layer_options.keys()),
            help="Choose the layer you want to update with new data"
        )
        
        if selected_layer_key:
            selected_layer = layer_options[selected_layer_key]
            
            # Display current layer info
            col1, col2 = st.columns([2, 1])
            with col1:
                st.info(f"Selected: {selected_layer.title}")
                try:
                    layer_collection = FeatureLayerCollection.fromitem(selected_layer)
                    st.code(f"FeatureServer URL: {layer_collection.url}")
                except:
                    st.warning("Could not retrieve FeatureServer URL")
            
            with col2:
                if st.button("👀 Preview Current Data", key="preview_current"):
                    preview_layer_data(selected_layer)
    
    # File upload section
    if selected_layer_key:
        with st.expander("📁 Upload New Data", expanded=True):
            st.info("Upload a zip file containing the updated shapefile data")
            
            uploaded_file = st.file_uploader(
                "Upload updated shapefile (.zip)",
                type=['zip'],
                help="Upload a zip file containing .shp, .shx, .dbf, and optional .prj files"
            )
            
            if uploaded_file:
                # Validate zip file
                is_valid, message = validate_zip_file(uploaded_file)
                
                if is_valid:
                    st.success(message)
                    
                    # Preview new data before updating
                    with st.expander("👀 Preview New Data"):
                        try:
                            gdf, temp_dir = extract_and_load_shapefile(uploaded_file)
                            st.write(f"**Records in new data:** {len(gdf)}")
                            st.dataframe(gdf.head().drop(columns=['geometry'] if 'geometry' in gdf.columns else []))
                            shutil.rmtree(temp_dir)
                        except Exception as e:
                            st.warning(f"Could not preview new data: {str(e)}")
                    
                    # Confirmation section
                    with st.expander("⚠️ Confirm Update", expanded=True):
                        st.warning("This action will replace all existing data in the selected layer. This cannot be undone.")
                        
                        confirm_update = st.checkbox("I understand this will replace all existing data")
                        
                        if confirm_update and st.button("🔄 Update Layer", type="primary"):
                            try:
                                with st.spinner("Updating layer..."):
                                    # Extract and load shapefile
                                    gdf, temp_dir = extract_and_load_shapefile(uploaded_file)
                                    
                                    # Create temporary zip for upload
                                    temp_zip_path = os.path.join(temp_dir, "update.zip")
                                    with zipfile.ZipFile(temp_zip_path, 'w') as zip_ref:
                                        for root, dirs, files in os.walk(temp_dir):
                                            for file in files:
                                                if not file.endswith('.zip'):
                                                    file_path = os.path.join(root, file)
                                                    zip_ref.write(file_path, file)
                                    
                                    # Update layer
                                    layer_collection = FeatureLayerCollection.fromitem(selected_layer)
                                    result = layer_collection.manager.overwrite(temp_zip_path)
                                    
                                    if result:
                                        st.success("Layer updated successfully!")
                                        st.info(f"Records updated: {len(gdf)}")
                                        st.code(f"FeatureServer URL: {layer_collection.url}")
                                        
                                        # Show sample data
                                        st.subheader("Sample of updated data")
                                        st.dataframe(gdf.head().drop(columns=['geometry'] if 'geometry' in gdf.columns else []))
                                    else:
                                        st.error("Failed to update layer")
                                    
                                    # Clean up
                                    shutil.rmtree(temp_dir)
                                    
                            except Exception as e:
                                st.error(f"Error updating layer: {str(e)}")
                else:
                    st.error(message)

def get_shapefile_info_geopandas(zip_file):
    """Get shapefile geometry type and field names using geopandas"""
    try:
        # Extract and load shapefile using existing function
        gdf, temp_dir = extract_and_load_shapefile(zip_file)
        
        # Get geometry type from first feature
        if len(gdf) > 0 and gdf.geometry.iloc[0] is not None:
            geom_type = gdf.geometry.iloc[0].geom_type
            # Map geopandas geometry types to standard names
            if geom_type in ['Point', 'MultiPoint']:
                geometry_type = 'Point'
            elif geom_type in ['LineString', 'MultiLineString']:
                geometry_type = 'LineString'
            elif geom_type in ['Polygon', 'MultiPolygon']:
                geometry_type = 'Polygon'
            else:
                geometry_type = geom_type
        else:
            geometry_type = 'Unknown'
        
        # Get field names (excluding geometry column)
        field_names = [col for col in gdf.columns if col.lower() not in ['geometry', 'shape']]
        
        # Clean up
        shutil.rmtree(temp_dir)
        
        return geometry_type, field_names, None
        
    except Exception as e:
        return None, None, str(e)

def create_new_layer():
    """Create a new feature layer with enhanced UI and customization"""
    st.header("➕ Create New Layer")
    
    # Layer details section
    with st.expander("📝 Layer Information", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            layer_title = st.text_input("Layer Title", placeholder="Enter a title for your new layer")
            layer_description = st.text_area("Description (Optional)", placeholder="Describe your layer")
        
        with col2:
            layer_tags = st.text_input("Tags (comma-separated)", placeholder="tag1, tag2, tag3")
            sharing_level = st.selectbox("Sharing Level", ["private", "org", "public"])
    
    # File upload section
    with st.expander("📁 Upload Shapefile", expanded=True):
        st.info("Upload a zip file containing your shapefile data")
        
        uploaded_file = st.file_uploader(
            "Upload shapefile (.zip)",
            type=['zip'],
            help="Upload a zip file containing .shp, .shx, .dbf, and optional .prj files"
        )
        
        # Initialize variables for styling
        geometry_type = None
        field_names = []
        selected_color = "#FF5733"
        selected_fields = []
        
        if uploaded_file:
            # Validate and analyze the shapefile
            is_valid, message = validate_zip_file(uploaded_file)
            
            if is_valid:
                st.success(message)
                
                # Get shapefile information using geopandas
                geometry_type, field_names, error = get_shapefile_info_geopandas(uploaded_file)
                
                if error:
                    st.error(f"Error reading shapefile: {error}")
                elif geometry_type and field_names:
                    st.info(f"Detected geometry type: **{geometry_type}**")
                    st.info(f"Available fields: **{', '.join(field_names)}**")
                    
                    # Styling configuration
                    with st.expander("🎨 Layer Styling", expanded=True):
                        st.write(f"**Configure styling for {geometry_type} layer**")
                        
                        if geometry_type.lower() in ['point', 'multipoint']:
                            st.write("Setting up point symbol styling")
                        elif geometry_type.lower() in ['linestring', 'multilinestring']:
                            st.write("Setting up line symbol styling")
                        elif geometry_type.lower() in ['polygon', 'multipolygon']:
                            st.write("Setting up polygon symbol styling")
                        
                        selected_color = st.color_picker("Choose layer color", "#FF5733")
                        
                        # Show color preview
                        st.markdown(f"""
                        <div style="background-color: {selected_color}; width: 100%; height: 30px; border-radius: 5px; border: 1px solid #ccc;">
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Popup configuration
                    with st.expander("💬 Popup Configuration", expanded=True):
                        enable_popups = st.checkbox("Enable popups for this layer", value=True)
                        
                        if enable_popups and field_names:
                            selected_fields = st.multiselect(
                                "Select fields to display in popup",
                                options=field_names,
                                default=field_names[:3] if len(field_names) >= 3 else field_names,
                                help="Choose which fields will be shown when users click on features"
                            )
                        elif enable_popups:
                            st.warning("No fields available for popup configuration")
                else:
                    st.error("Could not read shapefile geometry or fields")
            else:
                st.error(message)
    
    # Web map selection
    with st.expander("🗺️ Add to Web Maps (Optional)"):
        web_maps = get_web_maps(st.session_state.username)
        selected_maps = []
        map_options = {}
        
        if web_maps:
            st.info("Select web maps to automatically add this new layer to")
            map_options = {f"{web_map.title} ({web_map.id})": web_map for web_map in web_maps}
            selected_maps = st.multiselect(
                "Select web maps",
                options=list(map_options.keys()),
                help="The new layer will be added to these web maps"
            )
        else:
            st.info("No web maps found in your account")
    
    # Create and Publish Layer Button
    if uploaded_file and layer_title and geometry_type:
        with st.expander("🚀 Create and Publish Layer", expanded=True):
            st.info("Review your settings and create the layer with custom styling")
            
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Layer Settings:**")
                st.write(f"• Title: {layer_title}")
                st.write(f"• Geometry: {geometry_type}")
                st.write(f"• Sharing: {sharing_level}")
            
            with col2:
                st.write("**Styling:**")
                st.markdown(f"""
                <div style="background-color: {selected_color}; width: 50px; height: 20px; border-radius: 3px; border: 1px solid #ccc; display: inline-block;"></div>
                <span style="margin-left: 10px;">Color: {selected_color}</span>
                """, unsafe_allow_html=True)
                
                if selected_fields:
                    st.write(f"• Popup fields: {', '.join(selected_fields)}")
                else:
                    st.write("• Popups: Disabled")
            
            if st.button("🚀 Create and Publish Layer", type="primary"):
                try:
                    with st.spinner("Creating new layer with custom styling..."):
                        # Extract and load shapefile
                        gdf, temp_dir = extract_and_load_shapefile(uploaded_file)
                        
                        # Prepare item properties
                        item_properties = {
                            'title': layer_title,
                            'type': 'Shapefile',
                            'tags': [tag.strip() for tag in layer_tags.split(',') if tag.strip()] if layer_tags else []
                        }
                        
                        if layer_description:
                            item_properties['description'] = layer_description
                        
                        # Create temporary zip for upload using layer title
                        safe_title = "".join(c for c in layer_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
                        safe_title = safe_title.replace(' ', '_')
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        unique_zip_name = f"{safe_title}_{timestamp}.zip"
                        temp_zip_path = os.path.join(temp_dir, unique_zip_name)
                        with zipfile.ZipFile(temp_zip_path, 'w') as zip_ref:
                            for root, dirs, files in os.walk(temp_dir):
                                for file in files:
                                    if not file.endswith('.zip'):
                                        file_path = os.path.join(root, file)
                                        zip_ref.write(file_path, file)
                        
                        # Add item to ArcGIS Online
                        item = st.session_state.gis.content.add(item_properties, temp_zip_path)
                        
                        # Publish as feature service
                        feature_service = item.publish()
                        
                        # Apply custom styling and popup configuration
                        try:
                            layer_collection = FeatureLayerCollection.fromitem(feature_service)
                            feature_layer = layer_collection.layers[0]
                            
                            # Create layer definition with styling and popup
                            layer_definition = {}
                            
                            # Add custom renderer
                            if geometry_type and selected_color:
                                renderer = create_renderer(geometry_type, selected_color)
                                if renderer:
                                    layer_definition["drawingInfo"] = {"renderer": renderer}
                            
                            # Add popup configuration
                            if selected_fields:
                                popup_info = create_popup_info(selected_fields)
                                if popup_info:
                                    layer_definition["popupInfo"] = popup_info
                            elif not enable_popups:
                                layer_definition["popupInfo"] = None
                            
                            # Apply the layer definition
                            if layer_definition:
                                feature_layer.manager.update_definition(layer_definition)
                                st.success("Custom styling and popup configuration applied!")
                        
                        except Exception as e:
                            st.warning(f"Layer created but styling could not be applied: {str(e)}")
                        
                        # Apply sharing settings
                        if sharing_level == "org":
                            feature_service.share(org=True)
                        elif sharing_level == "public":
                            feature_service.share(everyone=True)
                        
                        # Get FeatureServer URL
                        feature_server_url = layer_collection.url
                        
                        st.success("Layer created successfully with custom styling!")
                        st.info(f"Records created: {len(gdf)}")
                        st.code(f"FeatureServer URL: {feature_server_url}")
                        
                        # Add to selected web maps
                        if web_maps and selected_maps:
                            for map_key in selected_maps:
                                try:
                                    web_map = map_options[map_key]
                                    web_map_item = st.session_state.gis.content.get(web_map.id)
                                    
                                    # Add layer to web map
                                    web_map_obj = web_map_item.get_data()
                                    
                                    # Create layer definition
                                    layer_def = {
                                        "id": feature_service.id,
                                        "title": layer_title,
                                        "url": feature_server_url,
                                        "visibility": True,
                                        "opacity": 1
                                    }
                                    
                                    # Add to operational layers
                                    if 'operationalLayers' not in web_map_obj:
                                        web_map_obj['operationalLayers'] = []
                                    web_map_obj['operationalLayers'].append(layer_def)
                                    
                                    # Update web map
                                    web_map_item.update(data=json.dumps(web_map_obj))
                                    st.success(f"Added to web map: {web_map.title}")
                                    
                                except Exception as e:
                                    st.warning(f"Could not add to web map {web_map.title}: {str(e)}")
                        
                        # Show sample data
                        st.subheader("Sample of created data")
                        st.dataframe(gdf.head().drop(columns=['geometry'] if 'geometry' in gdf.columns else []))
                        
                        # Clean up
                        shutil.rmtree(temp_dir)
                        
                except Exception as e:
                    st.error(f"Error creating layer: {str(e)}")
    
    if uploaded_file and not layer_title:
        st.warning("Please enter a layer title")

def merge_layers():
    """Merge multiple feature layers with enhanced UI and validation"""
    st.header("🔗 Merge Layers")
    
    feature_layers = get_feature_layers(st.session_state.username)
    
    if len(feature_layers) < 2:
        st.warning("You need at least 2 feature layers to perform a merge")
        return
    
    # Layer selection with preview
    with st.expander("📋 Select Layers to Merge", expanded=True):
        layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
        selected_layers = st.multiselect(
            "Select layers to merge",
            options=list(layer_options.keys()),
            help="Select 2 or more layers to merge into a new layer"
        )
        
        if len(selected_layers) >= 2:
            # Validate layer compatibility
            selected_layer_objects = [layer_options[key] for key in selected_layers]
            is_compatible, compatibility_message = validate_layer_compatibility(selected_layer_objects)
            
            if is_compatible:
                st.success(compatibility_message)
            else:
                st.error(compatibility_message)
                return
            
            # Show selected layers info with preview option
            st.subheader("Selected Layers")
            for layer_key in selected_layers:
                layer = layer_options[layer_key]
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"• {layer.title}")
                with col2:
                    if st.button(f"Preview", key=f"preview_{layer.id}"):
                        preview_layer_data(layer)
        
        elif len(selected_layers) == 1:
            st.info("Please select at least one more layer to merge")
    
    # Merge configuration
    if len(selected_layers) >= 2:
        with st.expander("⚙️ Merge Configuration", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                merged_title = st.text_input("Title for merged layer", placeholder="Enter title for the new merged layer")
                merged_description = st.text_area("Description (Optional)", placeholder="Describe the merged layer")
            
            with col2:
                merged_tags = st.text_input("Tags (comma-separated)", placeholder="tag1, tag2, tag3")
                sharing_level = st.selectbox("Sharing Level", ["private", "org", "public"], key="merge_sharing")
        
        if merged_title and st.button("Merge Layers", type="primary"):
            try:
                with st.spinner("Merging layers..."):
                    merged_gdf = None
                    total_records = 0
                    
                    # Collect data from all selected layers
                    for layer_key in selected_layers:
                        layer = layer_options[layer_key]
                        
                        try:
                            # Get layer data
                            layer_collection = FeatureLayerCollection.fromitem(layer)
                            feature_layer = layer_collection.layers[0]
                            
                            # Query all features
                            feature_set = feature_layer.query()
                            
                            if feature_set.features:
                                # Convert to GeoDataFrame
                                layer_gdf = feature_set.sdf
                                
                                if 'SHAPE' in layer_gdf.columns:
                                    layer_gdf = layer_gdf.set_geometry('SHAPE')
                                
                                # Add source layer information
                                layer_gdf['source_layer'] = layer.title
                                
                                # Merge with existing data
                                if merged_gdf is None:
                                    merged_gdf = layer_gdf
                                else:
                                    # Align columns
                                    common_columns = list(set(merged_gdf.columns) & set(layer_gdf.columns))
                                    merged_gdf = pd.concat([
                                        merged_gdf[common_columns],
                                        layer_gdf[common_columns]
                                    ], ignore_index=True)
                                
                                total_records += len(layer_gdf)
                                st.info(f"Added {len(layer_gdf)} records from {layer.title}")
                        
                        except Exception as e:
                            st.warning(f"Could not process layer {layer.title}: {str(e)}")
                    
                    if merged_gdf is not None and len(merged_gdf) > 0:
                        # Save merged data to temporary shapefile using merged layer title
                        temp_dir = tempfile.mkdtemp()
                        # Clean the title for safe filename use
                        safe_title = "".join(c for c in merged_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
                        safe_title = safe_title.replace(' ', '_')
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        shapefile_name = f"{safe_title}_{timestamp}"
                        shapefile_path = os.path.join(temp_dir, f"{shapefile_name}.shp")
                        
                        # Convert to GeoDataFrame if needed
                        if not isinstance(merged_gdf, gpd.GeoDataFrame):
                            merged_gdf = gpd.GeoDataFrame(merged_gdf)
                        
                        merged_gdf.to_file(shapefile_path)
                        
                        # Create zip file with unique name
                        zip_path = os.path.join(temp_dir, f"{shapefile_name}.zip")
                        with zipfile.ZipFile(zip_path, 'w') as zip_ref:
                            for root, dirs, files in os.walk(temp_dir):
                                for file in files:
                                    if not file.endswith('.zip'):
                                        file_path = os.path.join(root, file)
                                        zip_ref.write(file_path, file)
                        
                        # Prepare item properties
                        item_properties = {
                            'title': merged_title,
                            'type': 'Shapefile',
                            'tags': [tag.strip() for tag in merged_tags.split(',') if tag.strip()] if merged_tags else []
                        }
                        
                        if merged_description:
                            item_properties['description'] = merged_description
                        
                        # Upload and publish
                        item = st.session_state.gis.content.add(item_properties, zip_path)
                        feature_service = item.publish()
                        
                        # Apply sharing settings
                        if sharing_level == "org":
                            feature_service.share(org=True)
                        elif sharing_level == "public":
                            feature_service.share(everyone=True)
                        
                        # Get FeatureServer URL
                        layer_collection = FeatureLayerCollection.fromitem(feature_service)
                        feature_server_url = layer_collection.url
                        
                        st.success("Layers merged successfully!")
                        st.info(f"Total records in merged layer: {len(merged_gdf)}")
                        st.code(f"FeatureServer URL: {feature_server_url}")
                        
                        # Show sample data
                        st.subheader("Sample of merged data")
                        st.dataframe(merged_gdf.head().drop(columns=['geometry'] if 'geometry' in merged_gdf.columns else []))
                        
                        # Clean up
                        shutil.rmtree(temp_dir)
                    
                    else:
                        st.error("No data could be retrieved from the selected layers")
                        
            except Exception as e:
                st.error(f"Error merging layers: {str(e)}")

def delete_layer():
    """Delete a feature layer with enhanced safety and preview"""
    st.header("🗑️ Delete Layer")
    
    st.warning("This action cannot be undone. Please be careful when deleting layers.")
    
    feature_layers = get_feature_layers(st.session_state.username)
    
    if not feature_layers:
        st.info("No feature layers found in your account")
        return
    
    # Layer selection with preview
    with st.expander("📋 Select Layer to Delete", expanded=True):
        layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
        selected_layer_key = st.selectbox(
            "Select layer to delete",
            options=[""] + list(layer_options.keys()),
            help="Choose the layer you want to delete"
        )
        
        if selected_layer_key:
            selected_layer = layer_options[selected_layer_key]
            
            # Display layer info
            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader("Layer Information")
                info_col1, info_col2 = st.columns(2)
                
                with info_col1:
                    st.write(f"**Title:** {selected_layer.title}")
                    st.write(f"**Type:** {selected_layer.type}")
                    st.write(f"**Owner:** {selected_layer.owner}")
                
                with info_col2:
                    st.write(f"**Created:** {datetime.fromtimestamp(selected_layer.created/1000).strftime('%Y-%m-%d %H:%M:%S')}")
                    st.write(f"**ID:** {selected_layer.id}")
            
            with col2:
                if st.button("👀 Preview Before Delete", key="preview_delete"):
                    preview_layer_data(selected_layer)
    
    # Confirmation section
    if selected_layer_key:
        with st.expander("⚠️ Confirm Deletion", expanded=True):
            st.error("This action will permanently delete the selected layer and all its data. This cannot be undone.")
            
            # Double confirmation
            confirm_checkbox = st.checkbox("I understand this action cannot be undone")
            
            if confirm_checkbox:
                confirm_text = st.text_input(
                    f"Type '{selected_layer.title}' to confirm deletion",
                    placeholder=selected_layer.title,
                    help="Type the exact layer title to enable deletion"
                )
                
                if confirm_text == selected_layer.title:
                    if st.button("🗑️ DELETE LAYER PERMANENTLY", type="primary"):
                        try:
                            with st.spinner("Deleting layer..."):
                                result = selected_layer.delete()
                                
                                if result:
                                    st.success(f"Layer '{selected_layer.title}' has been deleted successfully")
                                    st.info("The layer has been permanently removed from your ArcGIS Online account")
                                else:
                                    st.error("Failed to delete the layer")
                                    
                        except Exception as e:
                            st.error(f"Error deleting layer: {str(e)}")
                else:
                    st.info("Enter the exact layer title above to enable deletion")
            else:
                st.info("Check the confirmation box to proceed with deletion")

def create_renderer(geometry_type, color):
    """Create a simple renderer based on geometry type and color"""
    if geometry_type.lower() in ['point', 'multipoint']:
        return {
            "type": "simple",
            "symbol": {
                "type": "esriSMS",
                "style": "esriSMSCircle",
                "color": [int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16), 255],
                "size": 8,
                "outline": {
                    "color": [0, 0, 0, 255],
                    "width": 1
                }
            }
        }
    elif geometry_type.lower() in ['polyline', 'line']:
        return {
            "type": "simple",
            "symbol": {
                "type": "esriSLS",
                "style": "esriSLSSolid",
                "color": [int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16), 255],
                "width": 2
            }
        }
    elif geometry_type.lower() in ['polygon', 'multipolygon']:
        return {
            "type": "simple",
            "symbol": {
                "type": "esriSFS",
                "style": "esriSFSSolid",
                "color": [int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16), 128],
                "outline": {
                    "type": "esriSLS",
                    "style": "esriSLSSolid",
                    "color": [int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16), 255],
                    "width": 1
                }
            }
        }
    else:
        return None

def create_popup_info(field_names):
    """Create popup info configuration from selected fields"""
    if not field_names:
        return None
    
    field_infos = []
    for field in field_names:
        field_infos.append({
            "fieldName": field,
            "label": field,
            "isEditable": False,
            "tooltip": "",
            "visible": True,
            "format": None,
            "stringFieldOption": "textbox"
        })
    
    return {
        "title": "",
        "fieldInfos": field_infos,
        "description": None,
        "showAttachments": False,
        "mediaInfos": []
    }

def layer_editor():
    """Layer Editor section with styling, popup control, and data management"""
    st.header("🎨 Layer Editor")
    
    feature_layers = get_feature_layers(st.session_state.username)
    
    if not feature_layers:
        st.info("No feature layers found in your account")
        return
    
    # Feature Service selection
    layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
    selected_layer_key = st.selectbox(
        "Select Feature Service",
        options=[""] + list(layer_options.keys()),
        help="Choose the feature service you want to edit"
    )
    
    if not selected_layer_key:
        st.info("Please select a feature service to begin editing")
        return
    
    selected_layer = layer_options[selected_layer_key]
    
    # Get sublayers from the feature service
    try:
        layer_collection = FeatureLayerCollection.fromitem(selected_layer)
        sublayers = layer_collection.layers
        
        if not sublayers:
            st.error("No sublayers found in this feature service")
            return
        
        # Sublayer selection
        if len(sublayers) > 1:
            sublayer_options = {}
            for i, sublayer in enumerate(sublayers):
                try:
                    name = sublayer.properties.name if hasattr(sublayer.properties, 'name') and sublayer.properties.name else f"Layer {i}"
                except:
                    name = f"Layer {i}"
                sublayer_options[f"{name} (ID: {i})"] = sublayer
            
            selected_sublayer_key = st.selectbox(
                "Select Sublayer",
                options=[""] + list(sublayer_options.keys()),
                help="Choose the specific sublayer to edit"
            )
            
            if not selected_sublayer_key:
                st.info("Please select a sublayer to edit")
                return
            
            feature_layer = sublayer_options[selected_sublayer_key]
            st.success(f"Selected sublayer: {selected_sublayer_key}")
        else:
            feature_layer = sublayers[0]
            st.info("Feature service has only one sublayer")
        
        layer_props = feature_layer.properties
        
        # Sublayer Info Expander
        with st.expander("ℹ️ Sublayer Information", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Geometry Type:** {layer_props.geometryType}")
                try:
                    feature_count = feature_layer.query(return_count_only=True)
                    st.write(f"**Feature Count:** {feature_count}")
                except:
                    st.write("**Feature Count:** Unable to retrieve")
            with col2:
                st.write(f"**Fields:** {len(layer_props.fields)}")
                field_names = [field['name'] for field in layer_props.fields if field['name'] not in ['OBJECTID', 'GlobalID']]
                st.write(f"**Available Fields:** {', '.join(field_names[:5])}{'...' if len(field_names) > 5 else ''}")
                
                # Show sublayer-specific information
                if hasattr(layer_props, 'name') and layer_props.name:
                    st.write(f"**Sublayer Name:** {layer_props.name}")
                if hasattr(layer_props, 'id'):
                    st.write(f"**Sublayer ID:** {layer_props.id}")
        
        # Symbology Expander
        with st.expander("🎨 Symbology"):
            st.info("Set the display color for this layer")
            
            # Color picker based on geometry type
            if layer_props.geometryType.lower() in ['point', 'multipoint']:
                st.write("**Point Layer Styling**")
            elif layer_props.geometryType.lower() in ['polyline']:
                st.write("**Line Layer Styling**")
            elif layer_props.geometryType.lower() in ['polygon']:
                st.write("**Polygon Layer Styling**")
            
            selected_color = st.color_picker("Choose layer color", "#FF5733")
            
            if st.button("Apply Symbology", type="primary"):
                try:
                    renderer = create_renderer(layer_props.geometryType, selected_color)
                    if renderer:
                        definition = {"drawingInfo": {"renderer": renderer}}
                        feature_layer.manager.update_definition(definition)
                        st.success("Symbology updated successfully!")
                    else:
                        st.error("Could not create renderer for this geometry type")
                except Exception as e:
                    st.error(f"Error updating symbology: {str(e)}")
        
        # Popup Configuration Expander
        with st.expander("💬 Popup Configuration"):
            enable_popups = st.checkbox("Enable popups for this layer", value=True)
            
            if enable_popups:
                available_fields = [field['name'] for field in layer_props.fields 
                                  if field['name'] not in ['OBJECTID', 'GlobalID', 'SHAPE', 'Shape']]
                
                selected_fields = st.multiselect(
                    "Select fields to display in popup",
                    options=available_fields,
                    default=available_fields[:3] if len(available_fields) >= 3 else available_fields,
                    help="Choose which fields will be shown when users click on features"
                )
                
                if st.button("Apply Popup Settings", type="primary"):
                    try:
                        popup_info = create_popup_info(selected_fields) if selected_fields else None
                        definition = {"popupInfo": popup_info}
                        feature_layer.manager.update_definition(definition)
                        st.success("Popup configuration updated successfully!")
                    except Exception as e:
                        st.error(f"Error updating popup settings: {str(e)}")
            else:
                if st.button("Disable Popups", type="primary"):
                    try:
                        definition = {"popupInfo": None}
                        feature_layer.manager.update_definition(definition)
                        st.success("Popups disabled successfully!")
                    except Exception as e:
                        st.error(f"Error disabling popups: {str(e)}")
        
        # Data Management Expander
        with st.expander("📊 Data Management"):
            st.warning("Data management operations cannot be undone. Use with caution.")
            
            # Show attribute table
            st.subheader("Attribute Table")
            try:
                # Query limited features for performance
                feature_set = feature_layer.query(return_count_only=False, result_record_count=100)
                if feature_set.features:
                    df = feature_set.sdf
                    
                    # Remove geometry column for display
                    display_df = df.drop(columns=['SHAPE'] if 'SHAPE' in df.columns else [])
                    
                    # Add selection checkboxes
                    if 'OBJECTID' in display_df.columns:
                        st.write(f"Showing first 100 records (Total: {feature_layer.query(return_count_only=True)})")
                        
                        # Row selection
                        selected_rows = st.multiselect(
                            "Select rows to delete",
                            options=display_df['OBJECTID'].tolist(),
                            format_func=lambda x: f"OBJECTID: {x}",
                            help="Select the Object IDs of features you want to delete"
                        )
                        
                        # Display the data table
                        st.dataframe(display_df, use_container_width=True)
                        
                        # Delete selected rows
                        if selected_rows:
                            st.warning(f"You have selected {len(selected_rows)} rows for deletion")
                            
                            confirm_delete = st.checkbox("I understand this will permanently delete the selected features")
                            
                            if confirm_delete and st.button("🗑️ Delete Selected Rows", type="primary"):
                                try:
                                    # Delete features by OBJECTID
                                    where_clause = f"OBJECTID IN ({','.join(map(str, selected_rows))})"
                                    delete_result = feature_layer.delete_features(where=where_clause)
                                    
                                    if delete_result.get('deleteResults'):
                                        successful_deletes = sum(1 for result in delete_result['deleteResults'] if result.get('success'))
                                        st.success(f"Successfully deleted {successful_deletes} features")
                                        st.rerun()
                                    else:
                                        st.error("No features were deleted")
                                except Exception as e:
                                    st.error(f"Error deleting features: {str(e)}")
                    else:
                        st.dataframe(display_df, use_container_width=True)
                else:
                    st.info("No features found in this layer")
            except Exception as e:
                st.error(f"Error loading attribute table: {str(e)}")
            
            # Delete entire layer
            st.subheader("Layer Management")
            st.error("Danger Zone: Complete layer deletion")
            
            confirm_layer_delete = st.checkbox("I want to delete this entire layer and all its data")
            
            if confirm_layer_delete:
                confirm_text = st.text_input(
                    f"Type '{selected_layer.title}' to confirm layer deletion",
                    placeholder=selected_layer.title
                )
                
                if confirm_text == selected_layer.title:
                    if st.button("🗑️ DELETE ENTIRE LAYER", type="primary"):
                        try:
                            result = selected_layer.delete()
                            if result:
                                st.success(f"Layer '{selected_layer.title}' has been deleted successfully")
                                st.rerun()
                            else:
                                st.error("Failed to delete the layer")
                        except Exception as e:
                            st.error(f"Error deleting layer: {str(e)}")
                else:
                    st.info("Enter the exact layer title above to enable deletion")
    
    except Exception as e:
        st.error(f"Error accessing layer properties: {str(e)}")

def show_help():
    """Display help and guidance for using the application"""
    with st.sidebar.expander("❓ Help & Guide"):
        st.write("**Quick Start Guide:**")
        st.write("1. **View Layers** - Browse your existing feature layers and preview their data")
        st.write("2. **Update Layer** - Replace data in existing layers with new shapefiles")
        st.write("3. **Create Layer** - Upload shapefiles to create new feature layers with custom styling")
        st.write("4. **Layer Editor** - Style layers, configure popups, and manage data")
        st.write("5. **Merge Layers** - Combine multiple layers into one new layer")
        st.write("6. **Delete Layer** - Permanently remove layers from your account")
        
        st.write("**Tips:**")
        st.write("• Use the preview feature to examine data before operations")
        st.write("• Set custom colors and popup fields when creating new layers")
        st.write("• Use Layer Editor to modify styling and manage existing data")
        st.write("• All operations include confirmation steps for safety")
        
        st.write("**File Requirements:**")
        st.write("• Upload zip files containing .shp, .shx, and .dbf files")
        st.write("• Include .prj files for proper coordinate system handling")
        st.write("• Maximum 100 features shown in data management for performance")

def main():
    """Enhanced main application with improved navigation and help"""
    st.title("🗺️ ArcGIS Layer Manager")
    st.markdown("Professional ArcGIS Online feature layer management with data preview capabilities")
    
    # Authentication
    if not authenticate():
        return
    
    # Enhanced sidebar navigation
    st.sidebar.header("🧭 Navigation")
    
    # User info section
    if hasattr(st.session_state, 'gis'):
        user = st.session_state.gis.users.me
        with st.sidebar.container():
            st.write(f"**👤 User:** {user.username}")
            st.write(f"**🔑 Role:** {user.role}")
            
            # Quick stats
            try:
                feature_layers = get_feature_layers(st.session_state.username)
                web_maps = get_web_maps(st.session_state.username)
                st.write(f"**📊 Layers:** {len(feature_layers)}")
                st.write(f"**🗺️ Maps:** {len(web_maps)}")
            except:
                pass
    
    st.sidebar.markdown("---")
    
    # Page selection with enhanced descriptions
    page = st.sidebar.selectbox(
        "Select Action",
        ["View Layers", "Update Layer", "Create Layer", "Layer Editor", "Merge Layers", "Delete Layer"],
        help="Choose the operation you want to perform"
    )
    
    # Help section
    show_help()
    
    # Logout button
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout", help="Sign out and clear session"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    
    # Display selected page with enhanced routing
    if page == "View Layers":
        view_content()
    elif page == "Update Layer":
        update_existing_layer()
    elif page == "Create Layer":
        create_new_layer()
    elif page == "Layer Editor":
        layer_editor()
    elif page == "Merge Layers":
        merge_layers()
    elif page == "Delete Layer":
        delete_layer()

if __name__ == "__main__":
    main()