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

def get_feature_layers():
    """Get user's existing feature layers"""
    try:
        search_results = st.session_state.gis.content.search(
            query="owner:" + st.session_state.username,
            item_type="Feature Service",
            max_items=100
        )
        return search_results
    except Exception as e:
        st.error(f"Error retrieving layers: {str(e)}")
        return []

def get_web_maps():
    """Get user's existing web maps"""
    try:
        search_results = st.session_state.gis.content.search(
            query="owner:" + st.session_state.username,
            item_type="Web Map",
            max_items=100
        )
        return search_results
    except Exception as e:
        st.error(f"Error retrieving web maps: {str(e)}")
        return []

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
    """Display user's existing content"""
    st.header("📋 Your ArcGIS Content")
    
    # Feature Layers
    st.subheader("Feature Layers")
    feature_layers = get_feature_layers()
    
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
        
        # Export functionality
        if st.button("📥 Export Layer List as CSV"):
            csv_data = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name=f"arcgis_layers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    else:
        st.info("No feature layers found in your account")
    
    # Web Maps
    st.subheader("Web Maps")
    web_maps = get_web_maps()
    
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
    """Update an existing feature layer"""
    st.header("🔄 Update Existing Layer")
    
    feature_layers = get_feature_layers()
    
    if not feature_layers:
        st.warning("No feature layers found in your account")
        return
    
    # Layer selection
    layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
    selected_layer_key = st.selectbox(
        "Select layer to update",
        options=list(layer_options.keys())
    )
    
    if selected_layer_key:
        selected_layer = layer_options[selected_layer_key]
        
        # Display current layer info
        st.info(f"Selected: {selected_layer.title}")
        
        try:
            layer_collection = FeatureLayerCollection.fromitem(selected_layer)
            st.code(f"FeatureServer URL: {layer_collection.url}")
        except:
            st.warning("Could not retrieve FeatureServer URL")
        
        # File upload
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
                
                if st.button("Update Layer", type="primary"):
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

def create_new_layer():
    """Create a new feature layer"""
    st.header("➕ Create New Layer")
    
    # Layer details
    col1, col2 = st.columns(2)
    
    with col1:
        layer_title = st.text_input("Layer Title", placeholder="Enter a title for your new layer")
        layer_description = st.text_area("Description (Optional)", placeholder="Describe your layer")
    
    with col2:
        layer_tags = st.text_input("Tags (comma-separated)", placeholder="tag1, tag2, tag3")
        sharing_level = st.selectbox("Sharing Level", ["private", "org", "public"])
    
    # Web map selection
    web_maps = get_web_maps()
    if web_maps:
        st.subheader("Add to Web Maps (Optional)")
        map_options = {f"{web_map.title} ({web_map.id})": web_map for web_map in web_maps}
        selected_maps = st.multiselect(
            "Select web maps to add this layer to",
            options=list(map_options.keys())
        )
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload shapefile (.zip)",
        type=['zip'],
        help="Upload a zip file containing .shp, .shx, .dbf, and optional .prj files"
    )
    
    if uploaded_file and layer_title:
        # Validate zip file
        is_valid, message = validate_zip_file(uploaded_file)
        
        if is_valid:
            st.success(message)
            
            if st.button("Create Layer", type="primary"):
                try:
                    with st.spinner("Creating new layer..."):
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
                        
                        # Create temporary zip for upload
                        temp_zip_path = os.path.join(temp_dir, "new_layer.zip")
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
                        
                        # Apply sharing settings
                        if sharing_level == "org":
                            feature_service.share(org=True)
                        elif sharing_level == "public":
                            feature_service.share(everyone=True)
                        
                        # Get FeatureServer URL
                        layer_collection = FeatureLayerCollection.fromitem(feature_service)
                        feature_server_url = layer_collection.url
                        
                        st.success("Layer created successfully!")
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
        else:
            st.error(message)
    elif uploaded_file and not layer_title:
        st.warning("Please enter a layer title")

def merge_layers():
    """Merge multiple feature layers"""
    st.header("🔗 Merge Layers")
    
    feature_layers = get_feature_layers()
    
    if len(feature_layers) < 2:
        st.warning("You need at least 2 feature layers to perform a merge")
        return
    
    # Layer selection
    layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
    selected_layers = st.multiselect(
        "Select layers to merge",
        options=list(layer_options.keys()),
        help="Select 2 or more layers to merge into a new layer"
    )
    
    if len(selected_layers) >= 2:
        # Show selected layers info
        st.subheader("Selected Layers")
        for layer_key in selected_layers:
            layer = layer_options[layer_key]
            st.write(f"• {layer.title}")
        
        # Merge options
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
                        # Save merged data to temporary shapefile
                        temp_dir = tempfile.mkdtemp()
                        shapefile_path = os.path.join(temp_dir, "merged_layer.shp")
                        
                        # Convert to GeoDataFrame if needed
                        if not isinstance(merged_gdf, gpd.GeoDataFrame):
                            merged_gdf = gpd.GeoDataFrame(merged_gdf)
                        
                        merged_gdf.to_file(shapefile_path)
                        
                        # Create zip file
                        zip_path = os.path.join(temp_dir, "merged_layer.zip")
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
    """Delete a feature layer"""
    st.header("🗑️ Delete Layer")
    
    st.warning("⚠️ This action cannot be undone. Please be careful when deleting layers.")
    
    feature_layers = get_feature_layers()
    
    if not feature_layers:
        st.info("No feature layers found in your account")
        return
    
    # Layer selection
    layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
    selected_layer_key = st.selectbox(
        "Select layer to delete",
        options=[""] + list(layer_options.keys()),
        help="Choose the layer you want to delete"
    )
    
    if selected_layer_key:
        selected_layer = layer_options[selected_layer_key]
        
        # Display layer info
        st.subheader("Layer Information")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Title:** {selected_layer.title}")
            st.write(f"**Type:** {selected_layer.type}")
            st.write(f"**Owner:** {selected_layer.owner}")
        
        with col2:
            st.write(f"**Created:** {datetime.fromtimestamp(selected_layer.created/1000).strftime('%Y-%m-%d %H:%M:%S')}")
            st.write(f"**ID:** {selected_layer.id}")
        
        # Confirmation
        st.subheader("Confirm Deletion")
        confirm_text = st.text_input(
            f"Type '{selected_layer.title}' to confirm deletion",
            placeholder=selected_layer.title
        )
        
        if confirm_text == selected_layer.title:
            if st.button("🗑️ DELETE LAYER", type="primary"):
                try:
                    with st.spinner("Deleting layer..."):
                        result = selected_layer.delete()
                        
                        if result:
                            st.success(f"Layer '{selected_layer.title}' has been deleted successfully")
                        else:
                            st.error("Failed to delete the layer")
                            
                except Exception as e:
                    st.error(f"Error deleting layer: {str(e)}")
        else:
            st.info("Enter the exact layer title above to enable deletion")

def main():
    """Main application"""
    st.title("🗺️ ArcGIS Layer Manager")
    st.markdown("Manage your ArcGIS Online feature layers with ease")
    
    # Authentication
    if not authenticate():
        return
    
    # Sidebar navigation
    st.sidebar.header("Navigation")
    
    # Logout button
    if st.sidebar.button("🚪 Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    
    st.sidebar.markdown("---")
    
    # User info
    if hasattr(st.session_state, 'gis'):
        user = st.session_state.gis.users.me
        st.sidebar.write(f"**User:** {user.username}")
        st.sidebar.write(f"**Role:** {user.role}")
    
    st.sidebar.markdown("---")
    
    # Page selection
    page = st.sidebar.selectbox(
        "Select Action",
        ["View Content", "Update Layer", "Create Layer", "Merge Layers", "Delete Layer"]
    )
    
    # Display selected page
    if page == "View Content":
        view_content()
    elif page == "Update Layer":
        update_existing_layer()
    elif page == "Create Layer":
        create_new_layer()
    elif page == "Merge Layers":
        merge_layers()
    elif page == "Delete Layer":
        delete_layer()

if __name__ == "__main__":
    main()