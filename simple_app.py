import streamlit as st
import os
import tempfile
import zipfile
from arcgis.gis import GIS
from arcgis.features import FeatureLayerCollection
import pandas as pd

# Page configuration
st.set_page_config(
    page_title="ArcGISLayerUpdater",
    page_icon="🗺️",
    layout="wide"
)

# Initialize session state
if 'gis' not in st.session_state:
    st.session_state.gis = None
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

def authenticate():
    """Handle ArcGIS Online authentication"""
    st.header("🔐 ArcGIS Online Authentication")
    
    with st.form("auth_form"):
        username = st.text_input("Username", help="Your ArcGIS Online username")
        password = st.text_input("Password", type="password", help="Your ArcGIS Online password")
        portal_url = st.text_input("Portal URL", value="https://www.arcgis.com", help="ArcGIS Online portal URL")
        
        submit = st.form_submit_button("Login", type="primary")
        
        if submit:
            if username and password:
                try:
                    with st.spinner("Authenticating..."):
                        gis = GIS(portal_url, username, password)
                        # Test authentication by accessing user properties
                        user = gis.users.me
                        if user:
                            st.session_state.gis = gis
                            st.session_state.authenticated = True
                            st.success(f"Successfully authenticated as {user.fullName}")
                            st.rerun()
                        else:
                            st.error("Authentication failed - invalid credentials")
                except Exception as e:
                    st.error(f"Authentication failed: {str(e)}")
            else:
                st.warning("Please enter both username and password")

def get_feature_layers():
    """Get user's existing feature layers"""
    try:
        items = st.session_state.gis.content.search(
            query=f"owner:{st.session_state.gis.users.me.username}",
            item_type="Feature Service",
            max_items=100
        )
        return items
    except Exception as e:
        st.error(f"Error fetching feature layers: {str(e)}")
        return []

def get_web_maps():
    """Get user's existing web maps"""
    try:
        items = st.session_state.gis.content.search(
            query=f"owner:{st.session_state.gis.users.me.username}",
            item_type="Web Map",
            max_items=100
        )
        return items
    except Exception as e:
        st.error(f"Error fetching web maps: {str(e)}")
        return []

def validate_zip_file(zip_file):
    """Validate that zip file contains shapefile components"""
    try:
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            
            # Check for required shapefile components
            has_shp = any(f.endswith('.shp') for f in file_list)
            has_shx = any(f.endswith('.shx') for f in file_list)
            has_dbf = any(f.endswith('.dbf') for f in file_list)
            
            if has_shp and has_shx and has_dbf:
                return True, "Valid shapefile archive"
            else:
                missing = []
                if not has_shp: missing.append('.shp')
                if not has_shx: missing.append('.shx')
                if not has_dbf: missing.append('.dbf')
                return False, f"Missing required files: {', '.join(missing)}"
                
    except zipfile.BadZipFile:
        return False, "Invalid zip file format"
    except Exception as e:
        return False, f"Error validating zip file: {str(e)}"

def apply_sharing_settings(item, sharing_level):
    """Apply sharing settings to an item"""
    try:
        if sharing_level == "Public":
            item.share(everyone=True)
        elif sharing_level == "Organization":
            item.share(org=True)
        # Private is default, no sharing needed
        return True
    except Exception as e:
        st.error(f"Error applying sharing settings: {str(e)}")
        return False

def update_existing_layer():
    """Update an existing feature layer"""
    st.header("🔄 Update Existing Layer")
    
    # Get existing feature layers
    feature_layers = get_feature_layers()
    
    if not feature_layers:
        st.warning("No feature layers found in your account")
        return
    
    # Create layer selection options
    layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
    
    with st.form("update_layer_form"):
        # Layer selection
        selected_layer_key = st.selectbox(
            "Select Feature Layer to Update",
            options=list(layer_options.keys()),
            help="Choose the feature layer you want to update"
        )
        
        # File upload
        uploaded_file = st.file_uploader(
            "Upload Shapefile (.zip)",
            type=['zip'],
            help="Upload a .zip file containing the updated shapefile"
        )
        
        # Sharing level
        sharing_level = st.radio(
            "Sharing Level",
            options=["Private", "Organization", "Public"],
            help="Set the sharing level for the updated layer"
        )
        
        update_button = st.form_submit_button("Update Layer", type="primary")
        
        if update_button:
            if uploaded_file and selected_layer_key:
                selected_layer = layer_options[selected_layer_key]
                
                # Validate zip file
                is_valid, message = validate_zip_file(uploaded_file)
                if not is_valid:
                    st.error(f"Invalid zip file: {message}")
                    return
                
                try:
                    with st.spinner("Updating layer..."):
                        # Save uploaded file to temporary location
                        with tempfile.TemporaryDirectory() as temp_dir:
                            temp_zip_path = os.path.join(temp_dir, "update.zip")
                            with open(temp_zip_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())
                            
                            # Get the feature layer collection
                            flc = FeatureLayerCollection.fromitem(selected_layer)
                            
                            # Overwrite the layer
                            result = flc.manager.overwrite(temp_zip_path)
                            
                            if result:
                                # Apply sharing settings
                                apply_sharing_settings(selected_layer, sharing_level)
                                
                                st.success("✅ Layer updated successfully!")
                                st.info(f"**FeatureServer URL:** {selected_layer.url}")
                                
                                # Display layer details
                                st.subheader("Updated Layer Details")
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**Title:** {selected_layer.title}")
                                    st.write(f"**Type:** {selected_layer.type}")
                                    st.write(f"**Sharing:** {sharing_level}")
                                with col2:
                                    st.write(f"**Owner:** {selected_layer.owner}")
                                    st.write(f"**Modified:** {selected_layer.modified}")
                                    st.write(f"**ID:** {selected_layer.id}")
                            else:
                                st.error("Failed to update layer")
                                
                except Exception as e:
                    st.error(f"Error updating layer: {str(e)}")
                    if "schema" in str(e).lower():
                        st.info("💡 **Tip:** Make sure the uploaded shapefile has the same schema (field names and types) as the existing layer")
            else:
                st.warning("Please select a layer and upload a zip file")

def create_new_layer():
    """Create a new feature layer"""
    st.header("➕ Create New Layer")
    
    with st.form("create_layer_form"):
        # Layer title
        layer_title = st.text_input(
            "Layer Title",
            help="Enter a title for the new feature layer"
        )
        
        # File upload
        uploaded_file = st.file_uploader(
            "Upload Shapefile (.zip)",
            type=['zip'],
            help="Upload a .zip file containing the shapefile"
        )
        
        # Sharing level
        sharing_level = st.radio(
            "Sharing Level",
            options=["Private", "Organization", "Public"],
            help="Set the sharing level for the new layer"
        )
        
        # Web maps selection
        web_maps = get_web_maps()
        if web_maps:
            selected_maps = st.multiselect(
                "Add to Web Maps (Optional)",
                options=[f"{wm.title} ({wm.id})" for wm in web_maps],
                help="Select web maps to add this new layer to"
            )
        else:
            selected_maps = []
            st.info("No web maps found in your account")
        
        create_button = st.form_submit_button("Create Layer", type="primary")
        
        if create_button:
            if uploaded_file and layer_title:
                # Validate zip file
                is_valid, message = validate_zip_file(uploaded_file)
                if not is_valid:
                    st.error(f"Invalid zip file: {message}")
                    return
                
                try:
                    with st.spinner("Creating new layer..."):
                        # Save uploaded file to temporary location
                        with tempfile.TemporaryDirectory() as temp_dir:
                            temp_zip_path = os.path.join(temp_dir, "new_layer.zip")
                            with open(temp_zip_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())
                            
                            # Add the zip file as an item
                            zip_item = st.session_state.gis.content.add({
                                'title': layer_title,
                                'type': 'Shapefile'
                            }, data=temp_zip_path)
                            
                            # Publish as feature layer
                            feature_layer = zip_item.publish()
                            
                            # Apply sharing settings
                            apply_sharing_settings(feature_layer, sharing_level)
                            
                            # Add to web maps if selected
                            if selected_maps:
                                for map_title in selected_maps:
                                    map_id = map_title.split('(')[-1].replace(')', '')
                                    try:
                                        web_map = st.session_state.gis.content.get(map_id)
                                        # Add layer to web map
                                        web_map_obj = web_map.get_data()
                                        web_map_obj['operationalLayers'].append({
                                            'id': feature_layer.id,
                                            'title': feature_layer.title,
                                            'url': feature_layer.url,
                                            'layerType': 'ArcGISFeatureLayer',
                                            'visibility': True
                                        })
                                        web_map.update(data=web_map_obj)
                                        st.success(f"Added to web map: {web_map.title}")
                                    except Exception as e:
                                        st.warning(f"Could not add to web map {map_title}: {str(e)}")
                            
                            st.success("✅ New layer created successfully!")
                            st.info(f"**FeatureServer URL:** {feature_layer.url}")
                            
                            # Display layer details
                            st.subheader("New Layer Details")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Title:** {feature_layer.title}")
                                st.write(f"**Type:** {feature_layer.type}")
                                st.write(f"**Sharing:** {sharing_level}")
                            with col2:
                                st.write(f"**Owner:** {feature_layer.owner}")
                                st.write(f"**Created:** {feature_layer.created}")
                                st.write(f"**ID:** {feature_layer.id}")
                            
                            # Clean up the temporary zip item
                            zip_item.delete()
                            
                except Exception as e:
                    st.error(f"Error creating layer: {str(e)}")
            else:
                st.warning("Please enter a layer title and upload a zip file")

def view_content():
    """Display user's existing content"""
    st.header("📋 Your ArcGIS Online Content")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Feature Layers")
        feature_layers = get_feature_layers()
        
        if feature_layers:
            for layer in feature_layers:
                with st.expander(f"📊 {layer.title}"):
                    st.write(f"**Type:** {layer.type}")
                    st.write(f"**Owner:** {layer.owner}")
                    st.write(f"**Modified:** {layer.modified}")
                    st.write(f"**URL:** {layer.url}")
                    st.write(f"**ID:** {layer.id}")
        else:
            st.info("No feature layers found")
    
    with col2:
        st.subheader("Web Maps")
        web_maps = get_web_maps()
        
        if web_maps:
            for web_map in web_maps:
                with st.expander(f"🗺️ {web_map.title}"):
                    st.write(f"**Type:** {web_map.type}")
                    st.write(f"**Owner:** {web_map.owner}")
                    st.write(f"**Modified:** {web_map.modified}")
                    st.write(f"**ID:** {web_map.id}")
        else:
            st.info("No web maps found")

def main():
    """Main application"""
    st.title("🗺️ ArcGISLayerUpdater")
    st.markdown("**Manage your ArcGIS Online hosted feature layers**")
    
    # Check authentication
    if not st.session_state.authenticated:
        authenticate()
        return
    
    # Display user info
    try:
        user = st.session_state.gis.users.me
        st.sidebar.success(f"Logged in as: **{user.fullName}**")
        st.sidebar.info(f"Organization: {st.session_state.gis.properties.name}")
        
        if st.sidebar.button("Logout"):
            st.session_state.gis = None
            st.session_state.authenticated = False
            st.rerun()
    except:
        st.session_state.authenticated = False
        st.rerun()
    
    # Navigation
    st.sidebar.header("Navigation")
    page = st.sidebar.selectbox(
        "Select Action",
        ["View Content", "Update Existing Layer", "Create New Layer"]
    )
    
    # Display selected page
    if page == "View Content":
        view_content()
    elif page == "Update Existing Layer":
        update_existing_layer()
    elif page == "Create New Layer":
        create_new_layer()

if __name__ == "__main__":
    main()