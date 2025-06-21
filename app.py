import streamlit as st
import os
import tempfile
import zipfile
import geopandas as gpd
from arcgis.gis import GIS
from arcgis.features import FeatureLayerCollection, FeatureLayer
from arcgis import geometry as arcgis_geometry
import pandas as pd
import json
from typing import Dict, List, Any
from datetime import datetime
import time
import io
import base64

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
if 'user_settings' not in st.session_state:
    st.session_state.user_settings = {
        'default_sharing_level': 'Private',
        'irth_id': '',
        'batch_size': 1000,
        'auto_reproject': True
    }

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

def load_user_settings():
    """Load user settings from file or session state"""
    settings_file = "user_settings.json"
    try:
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                loaded_settings = json.load(f)
                st.session_state.user_settings.update(loaded_settings)
    except Exception:
        pass  # Use default settings
    return st.session_state.user_settings

def save_user_settings():
    """Save user settings to file"""
    settings_file = "user_settings.json"
    try:
        with open(settings_file, 'w') as f:
            json.dump(st.session_state.user_settings, f)
        return True
    except Exception as e:
        st.error(f"Error saving settings: {str(e)}")
        return False

def validate_coordinate_system(gdf, target_layer=None):
    """Validate and offer reprojection for coordinate systems"""
    try:
        source_crs = gdf.crs
        if target_layer:
            # Get target layer CRS
            target_crs_info = target_layer.properties.get('spatialReference', {})
            target_wkid = target_crs_info.get('wkid', 4326)
            
            if source_crs and source_crs.to_epsg() != target_wkid:
                st.warning(f"Coordinate system mismatch: Source ({source_crs.to_epsg()}) vs Target ({target_wkid})")
                
                if st.session_state.user_settings.get('auto_reproject', True):
                    if st.button("Reproject to match target layer"):
                        try:
                            gdf = gdf.to_crs(f"EPSG:{target_wkid}")
                            st.success(f"Reprojected to EPSG:{target_wkid}")
                            return gdf, True
                        except Exception as e:
                            st.error(f"Reprojection failed: {str(e)}")
                            return gdf, False
                else:
                    st.info("Auto-reprojection disabled in settings")
                    
        return gdf, True
    except Exception as e:
        st.error(f"Error validating coordinate system: {str(e)}")
        return gdf, False

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

def generate_irth_export(layer_info, operation_type="update"):
    """Generate CSV export for irth integration"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    export_data = {
        'operation_type': [operation_type],
        'layer_title': [layer_info.get('title', '')],
        'layer_id': [layer_info.get('id', '')],
        'feature_server_url': [layer_info.get('url', '')],
        'owner': [layer_info.get('owner', '')],
        'sharing_level': [layer_info.get('sharing', 'Private')],
        'timestamp': [timestamp],
        'irth_id': [st.session_state.user_settings.get('irth_id', '')]
    }
    
    df = pd.DataFrame(export_data)
    return df

def batch_edit_features(layer, features, operation='add', batch_size=None):
    """Apply edits in batches for better performance"""
    if not batch_size:
        batch_size = st.session_state.user_settings.get('batch_size', 1000)
    
    total_features = len(features)
    success_count = 0
    
    # Create progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(0, total_features, batch_size):
        batch = features[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_features + batch_size - 1) // batch_size
        
        status_text.text(f"Processing batch {batch_num}/{total_batches}...")
        
        try:
            if operation == 'add':
                result = layer.edit_features(adds=batch)
                batch_success = sum(1 for r in result.get('addResults', []) if r.get('success', False))
            elif operation == 'update':
                result = layer.edit_features(updates=batch)
                batch_success = sum(1 for r in result.get('updateResults', []) if r.get('success', False))
            elif operation == 'delete':
                # For delete, batch contains where clauses
                result = layer.delete_features(where=batch)
                batch_success = sum(1 for r in result.get('deleteResults', []) if r.get('success', False))
            else:
                batch_success = 0
                
            success_count += batch_success
            
        except Exception as e:
            st.error(f"Error in batch {batch_num}: {str(e)}")
        
        # Update progress
        progress = min((i + batch_size) / total_features, 1.0)
        progress_bar.progress(progress)
        time.sleep(0.1)  # Small delay for UI responsiveness
    
    status_text.text(f"Completed: {success_count}/{total_features} features processed successfully")
    return success_count

def get_layer_sublayers(feature_layer):
    """Get sublayers from a feature layer"""
    try:
        flc = FeatureLayerCollection.fromitem(feature_layer)
        sublayers = []
        for layer in flc.layers:
            sublayers.append({
                'id': layer.properties.id,
                'name': layer.properties.name,
                'layer': layer
            })
        return sublayers
    except Exception as e:
        st.error(f"Error getting sublayers: {str(e)}")
        return []

def load_shapefile_data(zip_file):
    """Load shapefile data from zip file"""
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_zip_path = os.path.join(temp_dir, "temp.zip")
            with open(temp_zip_path, "wb") as f:
                f.write(zip_file.getbuffer())
            
            # Extract zip file
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find the .shp file
            shp_files = [f for f in os.listdir(temp_dir) if f.endswith('.shp')]
            if shp_files:
                shp_path = os.path.join(temp_dir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                return gdf
            else:
                st.error("No shapefile found in zip archive")
                return None
    except Exception as e:
        st.error(f"Error loading shapefile: {str(e)}")
        return None

def display_enhanced_editable_table(gdf, target_layer=None, key_suffix=""):
    """Display form-based table editing interface with ArcGIS API integration"""
    if gdf is None or gdf.empty:
        st.warning("No data to display")
        return None, None
    
    st.subheader("Feature Data Editor")
    
    # Convert geometry to string for display
    display_df = gdf.copy()
    if 'geometry' in display_df.columns:
        display_df['geometry'] = display_df['geometry'].astype(str)
    
    # Initialize session state for edit tracking
    if f'editing_row_{key_suffix}' not in st.session_state:
        st.session_state[f'editing_row_{key_suffix}'] = None
    if f'delete_confirmation_{key_suffix}' not in st.session_state:
        st.session_state[f'delete_confirmation_{key_suffix}'] = None
    if f'changes_applied_{key_suffix}' not in st.session_state:
        st.session_state[f'changes_applied_{key_suffix}'] = []
    
    # Display summary info
    st.info(f"Total Features: {len(display_df)} | Columns: {len(display_df.columns)}")
    
    # Progress tracking for applied changes
    if st.session_state[f'changes_applied_{key_suffix}']:
        st.success(f"Changes applied: {len(st.session_state[f'changes_applied_{key_suffix}'])}")
    
    # Form-based row display and editing
    for idx, row in display_df.iterrows():
        # Create unique container for each row
        with st.container():
            st.markdown(f"### Row {idx + 1}")
            
            # Create form for each row
            with st.form(f"row_form_{idx}_{key_suffix}"):
                # Display fields in a grid layout
                cols = st.columns(min(3, len(display_df.columns)))
                edited_values = {}
                
                for col_idx, column in enumerate(display_df.columns):
                    with cols[col_idx % 3]:
                        current_value = row[column]
                        # Handle different data types appropriately
                        if pd.isna(current_value):
                            current_value = ""
                        
                        edited_values[column] = st.text_input(
                            label=f"{column}",
                            value=str(current_value),
                            key=f"field_{column}_{idx}_{key_suffix}",
                            help=f"Edit {column} for row {idx + 1}"
                        )
                
                # Action buttons for each row
                col1, col2, col3 = st.columns([1, 1, 2])
                
                with col1:
                    save_edit = st.form_submit_button(
                        "Save Edit",
                        type="primary",
                        help="Save changes to this row"
                    )
                
                with col2:
                    delete_row = st.form_submit_button(
                        "Delete",
                        help="Delete this row"
                    )
                
                # Handle Save Edit action
                if save_edit:
                    try:
                        with st.spinner(f"Saving changes to row {idx + 1}..."):
                            if target_layer:
                                # Apply changes to ArcGIS layer
                                feature_attributes = {k: v for k, v in edited_values.items() if k != 'geometry'}
                                
                                # Get OBJECTID for update (assuming it exists)
                                if 'OBJECTID' in row:
                                    feature_attributes['OBJECTID'] = row['OBJECTID']
                                    
                                    # Create feature for update
                                    update_feature = {
                                        'attributes': feature_attributes
                                    }
                                    
                                    # Add geometry if present
                                    if 'geometry' in edited_values and edited_values['geometry']:
                                        try:
                                            from shapely import wkt
                                            geom = wkt.loads(edited_values['geometry'])
                                            update_feature['geometry'] = json.loads(geom.__geo_interface__)
                                        except:
                                            pass
                                    
                                    # Apply update to ArcGIS layer
                                    result = target_layer.edit_features(updates=[update_feature])
                                    
                                    if result.get('updateResults') and result['updateResults'][0].get('success'):
                                        # Update local dataframe
                                        for col, value in edited_values.items():
                                            display_df.loc[idx, col] = value
                                        
                                        st.session_state[f'changes_applied_{key_suffix}'].append(f"Updated row {idx + 1}")
                                        st.success(f"Row {idx + 1} updated successfully!")
                                        st.rerun()
                                    else:
                                        error_msg = result.get('updateResults', [{}])[0].get('error', {}).get('description', 'Unknown error')
                                        st.error(f"Failed to update row {idx + 1}: {error_msg}")
                                else:
                                    st.error("Cannot update row: OBJECTID not found")
                            else:
                                # Local update only (for preview mode)
                                for col, value in edited_values.items():
                                    display_df.loc[idx, col] = value
                                st.success(f"Row {idx + 1} updated locally!")
                                st.rerun()
                                
                    except Exception as e:
                        st.error(f"Error updating row {idx + 1}: {str(e)}")
                
                # Handle Delete action with confirmation
                if delete_row:
                    st.session_state[f'delete_confirmation_{key_suffix}'] = idx
                    st.rerun()
            
            # Display delete confirmation dialog
            if st.session_state[f'delete_confirmation_{key_suffix}'] == idx:
                st.warning(f"⚠️ Are you sure you want to delete Row {idx + 1}?")
                st.write("This action cannot be undone.")
                
                # Show row data for confirmation
                with st.expander("Row data to be deleted"):
                    for col, val in row.items():
                        st.write(f"**{col}:** {val}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"Confirm Delete Row {idx + 1}", type="primary", key=f"confirm_del_{idx}_{key_suffix}"):
                        try:
                            with st.spinner(f"Deleting row {idx + 1}..."):
                                if target_layer and 'OBJECTID' in row:
                                    # Delete from ArcGIS layer
                                    where_clause = f"OBJECTID = {row['OBJECTID']}"
                                    result = target_layer.delete_features(where=where_clause)
                                    
                                    if result.get('deleteResults') and result['deleteResults'][0].get('success'):
                                        # Remove from local dataframe
                                        display_df = display_df.drop(idx).reset_index(drop=True)
                                        st.session_state[f'changes_applied_{key_suffix}'].append(f"Deleted row {idx + 1}")
                                        st.session_state[f'delete_confirmation_{key_suffix}'] = None
                                        st.success(f"Row {idx + 1} deleted successfully!")
                                        st.rerun()
                                    else:
                                        error_msg = result.get('deleteResults', [{}])[0].get('error', {}).get('description', 'Unknown error')
                                        st.error(f"Failed to delete row {idx + 1}: {error_msg}")
                                else:
                                    # Local delete only
                                    display_df = display_df.drop(idx).reset_index(drop=True)
                                    st.session_state[f'delete_confirmation_{key_suffix}'] = None
                                    st.success(f"Row {idx + 1} deleted locally!")
                                    st.rerun()
                                    
                        except Exception as e:
                            st.error(f"Error deleting row {idx + 1}: {str(e)}")
                
                with col2:
                    if st.button(f"Cancel Delete", key=f"cancel_del_{idx}_{key_suffix}"):
                        st.session_state[f'delete_confirmation_{key_suffix}'] = None
                        st.rerun()
            
            st.divider()  # Visual separator between rows
    
    # Add new row functionality
    st.subheader("Add New Row")
    with st.form(f"add_new_row_{key_suffix}"):
        st.write("Enter values for new feature:")
        new_values = {}
        
        cols = st.columns(min(3, len(display_df.columns)))
        for col_idx, column in enumerate(display_df.columns):
            if column != 'OBJECTID':  # Don't allow editing OBJECTID for new rows
                with cols[col_idx % 3]:
                    new_values[column] = st.text_input(
                        f"{column}",
                        key=f"new_{column}_{key_suffix}",
                        help=f"Enter value for {column}"
                    )
        
        if st.form_submit_button("Add New Row", type="primary"):
            try:
                with st.spinner("Adding new row..."):
                    if target_layer:
                        # Add to ArcGIS layer
                        feature_attributes = {k: v for k, v in new_values.items() if k != 'geometry' and v}
                        
                        new_feature = {
                            'attributes': feature_attributes
                        }
                        
                        # Add geometry if present
                        if 'geometry' in new_values and new_values['geometry']:
                            try:
                                from shapely import wkt
                                geom = wkt.loads(new_values['geometry'])
                                new_feature['geometry'] = json.loads(geom.__geo_interface__)
                            except:
                                pass
                        
                        # Apply addition to ArcGIS layer
                        result = target_layer.edit_features(adds=[new_feature])
                        
                        if result.get('addResults') and result['addResults'][0].get('success'):
                            # Add to local dataframe
                            new_row = pd.Series(new_values, name=len(display_df))
                            display_df = pd.concat([display_df, new_row.to_frame().T], ignore_index=True)
                            st.session_state[f'changes_applied_{key_suffix}'].append("Added new row")
                            st.success("New row added successfully!")
                            st.rerun()
                        else:
                            error_msg = result.get('addResults', [{}])[0].get('error', {}).get('description', 'Unknown error')
                            st.error(f"Failed to add new row: {error_msg}")
                    else:
                        # Local add only
                        new_row = pd.Series(new_values, name=len(display_df))
                        display_df = pd.concat([display_df, new_row.to_frame().T], ignore_index=True)
                        st.success("New row added locally!")
                        st.rerun()
                        
            except Exception as e:
                st.error(f"Error adding new row: {str(e)}")
    
    return display_df, {'added': [], 'deleted': [], 'modified': []}

def display_editable_table(gdf):
    """Backward compatibility wrapper"""
    return display_enhanced_editable_table(gdf, "default")

def apply_edits_to_layer(feature_layer, original_gdf, edited_df, changes):
    """Apply edits to the feature layer"""
    try:
        if not changes['added'] and not changes['deleted'] and not changes['modified']:
            st.info("No changes to apply")
            return True
        
        # Convert edited_df back to GeoDataFrame if needed
        if 'geometry' in edited_df.columns and isinstance(edited_df['geometry'].iloc[0], str):
            from shapely import wkt
            edited_df['geometry'] = edited_df['geometry'].apply(wkt.loads)
            edited_gdf = gpd.GeoDataFrame(edited_df, geometry='geometry')
        else:
            edited_gdf = edited_df
        
        # Apply edits using ArcGIS API
        if changes['deleted']:
            # Delete features
            delete_ids = [str(i) for i in changes['deleted']]
            if hasattr(feature_layer, 'delete_features'):
                result = feature_layer.delete_features(where=f"OBJECTID IN ({','.join(delete_ids)})")
                if not result.get('deleteResults', [{}])[0].get('success', False):
                    st.error("Failed to delete some features")
        
        if changes['added']:
            # Add new features
            new_features = []
            for idx in changes['added']:
                if idx < len(edited_gdf):
                    row = edited_gdf.iloc[idx]
                    feature = {
                        'attributes': {col: val for col, val in row.items() if col != 'geometry'},
                        'geometry': json.loads(row['geometry'].__geo_interface__) if 'geometry' in row else None
                    }
                    new_features.append(feature)
            
            if new_features and hasattr(feature_layer, 'edit_features'):
                result = feature_layer.edit_features(adds=new_features)
                if not all(r.get('success', False) for r in result.get('addResults', [])):
                    st.error("Failed to add some features")
        
        if changes['modified']:
            # Update existing features
            update_features = []
            for idx in changes['modified']:
                if idx < len(edited_gdf):
                    row = edited_gdf.iloc[idx]
                    feature = {
                        'attributes': {col: val for col, val in row.items() if col != 'geometry'},
                        'geometry': json.loads(row['geometry'].__geo_interface__) if 'geometry' in row else None
                    }
                    update_features.append(feature)
            
            if update_features and hasattr(feature_layer, 'edit_features'):
                result = feature_layer.edit_features(updates=update_features)
                if not all(r.get('success', False) for r in result.get('updateResults', [])):
                    st.error("Failed to update some features")
        
        return True
    except Exception as e:
        st.error(f"Error applying edits: {str(e)}")
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
    
    # Layer selection outside form for sublayer detection
    selected_layer_key = st.selectbox(
        "Select Feature Layer to Update",
        options=list(layer_options.keys()),
        help="Choose the feature layer you want to update",
        key="layer_selector"
    )
    
    selected_layer = layer_options[selected_layer_key] if selected_layer_key else None
    
    # Get sublayers if available
    sublayers = []
    selected_sublayer = None
    if selected_layer:
        sublayers = get_layer_sublayers(selected_layer)
        
        if len(sublayers) > 1:
            st.subheader("Sublayer Selection")
            sublayer_options = {f"{sub['name']} (ID: {sub['id']})": sub for sub in sublayers}
            selected_sublayer_key = st.selectbox(
                "Select Sublayer to Update",
                options=list(sublayer_options.keys()),
                help="Choose the specific sublayer to update",
                key="sublayer_selector"
            )
            selected_sublayer = sublayer_options[selected_sublayer_key] if selected_sublayer_key else None
        elif len(sublayers) == 1:
            selected_sublayer = sublayers[0]
            st.info(f"Single sublayer detected: {selected_sublayer['name']}")
    
    with st.form("update_layer_form"):
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
            if uploaded_file and selected_layer:
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
                            
                            if selected_sublayer and len(sublayers) > 1:
                                # Update specific sublayer
                                target_layer = selected_sublayer['layer']
                                
                                # Truncate and append for sublayer update
                                truncate_result = target_layer.manager.truncate()
                                if truncate_result.get('success', False):
                                    # Load new data and append
                                    gdf = load_shapefile_data(uploaded_file)
                                    if gdf is not None:
                                        # Convert to features for append
                                        features = []
                                        for _, row in gdf.iterrows():
                                            feature = {
                                                'attributes': {col: val for col, val in row.items() if col != 'geometry'},
                                                'geometry': json.loads(row['geometry'].__geo_interface__) if 'geometry' in row else None
                                            }
                                            features.append(feature)
                                        
                                        append_result = target_layer.edit_features(adds=features)
                                        if all(r.get('success', False) for r in append_result.get('addResults', [])):
                                            st.success(f"✅ Sublayer '{selected_sublayer['name']}' updated successfully!")
                                        else:
                                            st.error("Failed to append new features to sublayer")
                                    else:
                                        st.error("Failed to load shapefile data")
                                else:
                                    st.error("Failed to truncate sublayer")
                            else:
                                # Update entire layer
                                result = flc.manager.overwrite(temp_zip_path)
                                
                                if result:
                                    st.success("✅ Layer updated successfully!")
                                else:
                                    st.error("Failed to update layer")
                            
                            # Apply sharing settings
                            apply_sharing_settings(selected_layer, sharing_level)
                            
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
                                
                except Exception as e:
                    st.error(f"Error updating layer: {str(e)}")
                    if "schema" in str(e).lower():
                        st.info("💡 **Tip:** Make sure the uploaded shapefile has the same schema (field names and types) as the existing layer")
            else:
                st.warning("Please select a layer and upload a zip file")

def create_new_layer():
    """Create a new feature layer"""
    st.header("➕ Create New Layer")
    
    # Initialize session state for data editing
    if 'shapefile_data' not in st.session_state:
        st.session_state.shapefile_data = None
    if 'edited_data' not in st.session_state:
        st.session_state.edited_data = None
    if 'show_editor' not in st.session_state:
        st.session_state.show_editor = False
    
    # File upload section
    st.subheader("Upload Shapefile")
    uploaded_file = st.file_uploader(
        "Upload Shapefile (.zip)",
        type=['zip'],
        help="Upload a .zip file containing the shapefile",
        key="create_file_uploader"
    )
    
    if uploaded_file:
        # Validate zip file
        is_valid, message = validate_zip_file(uploaded_file)
        if not is_valid:
            st.error(f"Invalid zip file: {message}")
        else:
            st.success(f"Valid shapefile: {message}")
            
            # Load shapefile data
            if st.button("Load and Preview Data", key="load_preview"):
                with st.spinner("Loading shapefile data..."):
                    gdf = load_shapefile_data(uploaded_file)
                    if gdf is not None:
                        # Validate coordinate system
                        gdf, crs_valid = validate_coordinate_system(gdf)
                        
                        st.session_state.shapefile_data = gdf
                        st.session_state.show_editor = True
                        st.success(f"Loaded {len(gdf)} features with {len(gdf.columns)} attributes")
                        
                        # Display CRS info
                        if gdf.crs:
                            st.info(f"Coordinate System: {gdf.crs}")
                        else:
                            st.warning("No coordinate system detected")
    
    # Data editing section
    if st.session_state.show_editor and st.session_state.shapefile_data is not None:
        st.subheader("Edit Shapefile Data")
        st.info("You can edit, add, or delete rows in the table below. Changes will be applied when creating the layer.")
        
        edited_df, changes = display_editable_table(st.session_state.shapefile_data)
        st.session_state.edited_data = edited_df
        
        if changes and (changes['added'] or changes['deleted'] or changes['modified']):
            st.info(f"Changes detected: {len(changes['added'])} added, {len(changes['modified'])} modified, {len(changes['deleted'])} deleted")
    
    # Layer creation form
    if st.session_state.shapefile_data is not None:
        st.subheader("Create Layer")
        with st.form("create_layer_form"):
            # Layer title
            layer_title = st.text_input(
                "Layer Title",
                help="Enter a title for the new feature layer"
            )
            
            # Sharing level - use default from settings
            default_sharing = st.session_state.user_settings.get('default_sharing_level', 'Private')
            sharing_level = st.radio(
                "Sharing Level",
                options=["Private", "Organization", "Public"],
                index=["Private", "Organization", "Public"].index(default_sharing),
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
                if layer_title:
                    try:
                        with st.spinner("Creating new layer..."):
                            # Use edited data if available, otherwise use original data
                            data_to_use = st.session_state.edited_data if st.session_state.edited_data is not None else st.session_state.shapefile_data
                            
                            # Convert edited data back to GeoDataFrame if needed
                            if 'geometry' in data_to_use.columns and isinstance(data_to_use['geometry'].iloc[0], str):
                                from shapely import wkt
                                data_to_use = data_to_use.copy()
                                data_to_use['geometry'] = data_to_use['geometry'].apply(wkt.loads)
                                data_to_use = gpd.GeoDataFrame(data_to_use, geometry='geometry')
                            
                            # Save edited data to temporary shapefile
                            with tempfile.TemporaryDirectory() as temp_dir:
                                import pathlib
                                temp_shp_path = str(pathlib.Path(temp_dir) / "edited_layer.shp")
                                data_to_use.to_file(temp_shp_path)
                                
                                # Create zip from edited shapefile
                                temp_zip_path = os.path.join(temp_dir, "edited_layer.zip")
                                with zipfile.ZipFile(temp_zip_path, 'w') as zipf:
                                    for ext in ['.shp', '.shx', '.dbf', '.prj']:
                                        file_path = temp_shp_path.replace('.shp', ext)
                                        if os.path.exists(file_path):
                                            zipf.write(file_path, f"edited_layer{ext}")
                                
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
                                
                                # Generate IRTH export
                                layer_info = {
                                    'title': feature_layer.title,
                                    'id': feature_layer.id,
                                    'url': feature_layer.url,
                                    'owner': feature_layer.owner,
                                    'sharing': sharing_level
                                }
                                
                                irth_df = generate_irth_export(layer_info, "create")
                                csv_data = irth_df.to_csv(index=False)
                                
                                # Display layer details with IRTH download
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
                                
                                # IRTH integration download
                                st.subheader("IRTH Integration")
                                st.download_button(
                                    label="📥 Download IRTH Export (CSV)",
                                    data=csv_data,
                                    file_name=f"irth_export_{feature_layer.title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv",
                                    help="Download layer metadata for IRTH system integration"
                                )
                                
                                # Clean up the temporary zip item
                                zip_item.delete()
                                
                                # Reset session state
                                st.session_state.shapefile_data = None
                                st.session_state.edited_data = None
                                st.session_state.show_editor = False
                                
                    except Exception as e:
                        st.error(f"Error creating layer: {str(e)}")
                else:
                    st.warning("Please enter a layer title")
    elif uploaded_file is None:
        st.info("Please upload a shapefile to begin creating a new layer")

def edit_layer_data():
    """Edit existing layer data"""
    st.header("✏️ Edit Layer Data")
    
    # Get existing feature layers
    feature_layers = get_feature_layers()
    
    if not feature_layers:
        st.warning("No feature layers found in your account")
        return
    
    # Create layer selection options
    layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
    
    # Layer selection
    selected_layer_key = st.selectbox(
        "Select Feature Layer to Edit",
        options=list(layer_options.keys()),
        help="Choose the feature layer you want to edit",
        key="edit_layer_selector"
    )
    
    if not selected_layer_key:
        return
        
    selected_layer = layer_options[selected_layer_key]
    
    # Get sublayers if available
    sublayers = get_layer_sublayers(selected_layer)
    selected_sublayer = None
    
    if len(sublayers) > 1:
        st.subheader("Sublayer Selection")
        sublayer_options = {f"{sub['name']} (ID: {sub['id']})": sub for sub in sublayers}
        selected_sublayer_key = st.selectbox(
            "Select Sublayer to Edit",
            options=list(sublayer_options.keys()),
            help="Choose the specific sublayer to edit",
            key="edit_sublayer_selector"
        )
        selected_sublayer = sublayer_options[selected_sublayer_key] if selected_sublayer_key else None
    elif len(sublayers) == 1:
        selected_sublayer = sublayers[0]
        st.info(f"Editing sublayer: {selected_sublayer['name']}")
    
    if selected_sublayer:
        target_layer = selected_sublayer['layer']
        
        # Load current layer data
        if st.button("Load Current Layer Data", key="load_layer_data"):
            try:
                with st.spinner("Loading layer data..."):
                    # Query features from the layer
                    feature_set = target_layer.query()
                    features = feature_set.features
                    
                    if features:
                        # Convert to DataFrame
                        data_rows = []
                        for feature in features:
                            row = feature.attributes.copy()
                            if feature.geometry:
                                row['geometry'] = str(feature.geometry)
                            data_rows.append(row)
                        
                        df = pd.DataFrame(data_rows)
                        st.session_state.current_layer_data = df
                        st.session_state.target_layer = target_layer
                        st.success(f"Loaded {len(df)} features from layer")
                    else:
                        st.warning("No features found in this layer")
                        
            except Exception as e:
                st.error(f"Error loading layer data: {str(e)}")
        
        # Display editable data if loaded
        if 'current_layer_data' in st.session_state and st.session_state.current_layer_data is not None:
            st.subheader("Edit Layer Features")
            st.info("Use the form-based editor below. Changes are applied immediately to ArcGIS Online.")
            
            # Use the enhanced form-based editing interface
            edited_df, changes = display_enhanced_editable_table(
                st.session_state.current_layer_data,
                target_layer=target_layer,
                key_suffix="edit_layer"
            )
            
            # Update session state with any changes
            if edited_df is not None:
                st.session_state.current_layer_data = edited_df
            
            # Additional controls
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Refresh Layer Data", key="refresh_data", type="secondary"):
                    st.session_state.current_layer_data = None
                    st.success("Data refreshed! Click 'Load Current Layer Data' to reload.")
                    st.rerun()
            
            with col2:
                if st.button("Reset Changes Tracker", key="reset_tracker"):
                    if f'changes_applied_edit_layer' in st.session_state:
                        st.session_state[f'changes_applied_edit_layer'] = []
                    st.success("Changes tracker reset!")
                    st.rerun()

def user_settings():
    """User settings and preferences management"""
    st.header("⚙️ Settings")
    
    # Load current settings
    load_user_settings()
    
    st.subheader("General Preferences")
    
    with st.form("settings_form"):
        # Default sharing level
        default_sharing = st.selectbox(
            "Default Sharing Level",
            options=["Private", "Organization", "Public"],
            index=["Private", "Organization", "Public"].index(
                st.session_state.user_settings.get('default_sharing_level', 'Private')
            ),
            help="Default sharing level for new layers"
        )
        
        # IRTH integration settings
        st.subheader("IRTH Integration")
        irth_id = st.text_input(
            "IRTH ID/Tag",
            value=st.session_state.user_settings.get('irth_id', ''),
            help="Optional IRTH identifier for layer tracking"
        )
        
        # Performance settings
        st.subheader("Performance Settings")
        batch_size = st.number_input(
            "Batch Size for Large Operations",
            min_value=100,
            max_value=10000,
            value=st.session_state.user_settings.get('batch_size', 1000),
            step=100,
            help="Number of features processed in each batch"
        )
        
        # Coordinate system settings
        auto_reproject = st.checkbox(
            "Auto-reproject coordinate systems",
            value=st.session_state.user_settings.get('auto_reproject', True),
            help="Automatically offer reprojection for mismatched coordinate systems"
        )
        
        # Save settings button
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.form_submit_button("Save Settings", type="primary"):
                st.session_state.user_settings.update({
                    'default_sharing_level': default_sharing,
                    'irth_id': irth_id,
                    'batch_size': batch_size,
                    'auto_reproject': auto_reproject
                })
                
                if save_user_settings():
                    st.success("Settings saved successfully!")
                else:
                    st.error("Failed to save settings")
        
        with col2:
            if st.form_submit_button("Reset to Defaults"):
                st.session_state.user_settings = {
                    'default_sharing_level': 'Private',
                    'irth_id': '',
                    'batch_size': 1000,
                    'auto_reproject': True
                }
                save_user_settings()
                st.success("Settings reset to defaults!")
                st.rerun()
        
        with col3:
            if st.form_submit_button("Export Settings"):
                settings_json = json.dumps(st.session_state.user_settings, indent=2)
                st.download_button(
                    label="Download Settings",
                    data=settings_json,
                    file_name="arcgis_layer_updater_settings.json",
                    mime="application/json"
                )
    
    # Import settings
    st.subheader("Import Settings")
    uploaded_settings = st.file_uploader(
        "Upload Settings File",
        type=['json'],
        help="Upload a previously exported settings file"
    )
    
    if uploaded_settings:
        try:
            settings_data = json.load(uploaded_settings)
            st.session_state.user_settings.update(settings_data)
            save_user_settings()
            st.success("Settings imported successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Error importing settings: {str(e)}")
    
    # Display current settings
    st.subheader("Current Settings")
    st.json(st.session_state.user_settings)

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
        ["View Content", "Update Existing Layer", "Create New Layer", "Edit Layer Data", "Settings"]
    )
    
    # Display selected page
    if page == "View Content":
        view_content()
    elif page == "Update Existing Layer":
        update_existing_layer()
    elif page == "Create New Layer":
        create_new_layer()
    elif page == "Edit Layer Data":
        edit_layer_data()
    elif page == "Settings":
        user_settings()

if __name__ == "__main__":
    main()