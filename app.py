import streamlit as st
import os
import json
import tempfile
import pandas as pd
import folium
from streamlit_folium import st_folium
import time
from datetime import datetime

# Import utility modules
from utils.file_handler import FileHandler
from utils.arcgis_manager import ArcGISManager
from utils.validation import Validator
from utils.logger import Logger
from utils.settings_manager import SettingsManager
from utils.backup_manager import BackupManager
from utils.notification import NotificationManager
from utils.export_manager import ExportManager

# Page configuration
st.set_page_config(
    page_title="ArcGISLayerUpdater",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'arcgis_manager' not in st.session_state:
    st.session_state.arcgis_manager = None
if 'uploaded_files' not in st.session_state:
    st.session_state.uploaded_files = []
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = {}
if 'update_history' not in st.session_state:
    st.session_state.update_history = []

# Initialize managers
logger = Logger()
settings_manager = SettingsManager()
file_handler = FileHandler()
validator = Validator()
backup_manager = BackupManager()
notification_manager = NotificationManager()
export_manager = ExportManager()

def main():
    st.title("🗺️ ArcGISLayerUpdater")
    st.markdown("### Comprehensive ArcGIS Online Feature Layer Management")
    
    # Sidebar for navigation and settings
    with st.sidebar:
        st.header("Navigation")
        tab = st.selectbox(
            "Select Function",
            ["Authentication", "File Upload", "Layer Management", "Settings", "Logs", "History"]
        )
        
        # Theme toggle
        if st.button("Toggle High Contrast"):
            st.session_state.high_contrast = not st.session_state.get('high_contrast', False)
            st.rerun()
    
    # Apply high contrast styling if enabled
    if st.session_state.get('high_contrast', False):
        st.markdown("""
        <style>
        .stApp { background-color: #000000; color: #FFFFFF; }
        .stButton > button { background-color: #FFFFFF; color: #000000; border: 2px solid #FFFFFF; }
        </style>
        """, unsafe_allow_html=True)
    
    # Main content based on selected tab
    if tab == "Authentication":
        authentication_section()
    elif tab == "File Upload":
        file_upload_section()
    elif tab == "Layer Management":
        layer_management_section()
    elif tab == "Settings":
        settings_section()
    elif tab == "Logs":
        logs_section()
    elif tab == "History":
        history_section()

def authentication_section():
    st.header("🔐 Authentication")
    
    # Load saved settings
    saved_settings = settings_manager.load_settings()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("ArcGIS Online Credentials")
        
        # API Key input with fallback to secrets
        api_key = st.text_input(
            "API Key",
            value=saved_settings.get('api_key', ''),
            type="password",
            help="Enter your ArcGIS Online API key or configure it in Streamlit secrets"
        )
        
        # Check for API key in secrets if not provided
        if not api_key:
            api_key = st.secrets.get("ARCGIS_API_KEY", "")
        
        username = st.text_input(
            "Username",
            value=saved_settings.get('username', ''),
            help="Your ArcGIS Online username"
        )
        
        portal_url = st.text_input(
            "Portal URL",
            value=saved_settings.get('portal_url', 'https://www.arcgis.com'),
            help="ArcGIS Online portal URL"
        )
        
        if st.button("Authenticate", type="primary"):
            if api_key and username:
                try:
                    with st.spinner("Authenticating..."):
                        arcgis_manager = ArcGISManager(api_key, username, portal_url)
                        if arcgis_manager.authenticate():
                            st.session_state.arcgis_manager = arcgis_manager
                            st.session_state.authenticated = True
                            
                            # Save credentials
                            settings_to_save = {
                                'api_key': api_key,
                                'username': username,
                                'portal_url': portal_url
                            }
                            settings_manager.save_settings(settings_to_save)
                            
                            st.success("✅ Authentication successful!")
                            logger.log("info", f"User {username} authenticated successfully")
                            st.rerun()
                        else:
                            st.error("❌ Authentication failed. Please check your credentials.")
                            logger.log("error", f"Authentication failed for user {username}")
                except Exception as e:
                    st.error(f"❌ Authentication error: {str(e)}")
                    logger.log("error", f"Authentication error: {str(e)}")
            else:
                st.warning("⚠️ Please provide both API key and username.")
    
    with col2:
        st.subheader("Authentication Status")
        if st.session_state.authenticated:
            st.success("🟢 Authenticated")
            st.info(f"**Username:** {username}")
            st.info(f"**Portal:** {portal_url}")
            
            if st.button("Logout"):
                st.session_state.authenticated = False
                st.session_state.arcgis_manager = None
                st.success("Logged out successfully")
                st.rerun()
        else:
            st.error("🔴 Not Authenticated")
            st.warning("Please authenticate to access layer management features.")

def file_upload_section():
    st.header("📁 File Upload & Validation")
    
    if not st.session_state.authenticated:
        st.warning("⚠️ Please authenticate first to upload files.")
        return
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Upload Shapefiles (.zip)")
        uploaded_files = st.file_uploader(
            "Select .zip files containing shapefiles",
            type=['zip'],
            accept_multiple_files=True,
            help="Upload .zip files containing shapefiles with required components (.shp, .shx, .dbf)"
        )
        
        if uploaded_files:
            st.session_state.uploaded_files = uploaded_files
            
            # Process uploaded files
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            processed_files = []
            
            for i, uploaded_file in enumerate(uploaded_files):
                progress = (i + 1) / len(uploaded_files)
                progress_bar.progress(progress)
                status_text.text(f"Processing {uploaded_file.name}...")
                
                try:
                    # Validate zip file
                    validation_result = file_handler.validate_zip_file(uploaded_file)
                    
                    if validation_result['valid']:
                        # Extract and process shapefile
                        with tempfile.TemporaryDirectory() as temp_dir:
                            extracted_files = file_handler.extract_zip_file(uploaded_file, temp_dir)
                            shapefile_data = file_handler.read_shapefile(extracted_files['shp'])
                            
                            processed_files.append({
                                'filename': uploaded_file.name,
                                'data': shapefile_data,
                                'geometry_type': shapefile_data.geom_type.iloc[0] if not shapefile_data.empty else 'Unknown',
                                'record_count': len(shapefile_data),
                                'fields': list(shapefile_data.columns),
                                'crs': shapefile_data.crs.to_string() if shapefile_data.crs else 'Unknown'
                            })
                            
                            logger.log("info", f"Successfully processed {uploaded_file.name}")
                    else:
                        st.error(f"❌ Invalid shapefile: {uploaded_file.name}")
                        st.error(f"Missing components: {', '.join(validation_result['missing_files'])}")
                        logger.log("error", f"Invalid shapefile: {uploaded_file.name}, missing: {validation_result['missing_files']}")
                        
                except Exception as e:
                    st.error(f"❌ Error processing {uploaded_file.name}: {str(e)}")
                    logger.log("error", f"Error processing {uploaded_file.name}: {str(e)}")
            
            progress_bar.progress(1.0)
            status_text.text("Processing complete!")
            
            st.session_state.processed_data = {file['filename']: file for file in processed_files}
            
            if processed_files:
                st.success(f"✅ Successfully processed {len(processed_files)} shapefile(s)")
                
                # Display file summary
                st.subheader("File Summary")
                summary_data = []
                for file_info in processed_files:
                    summary_data.append({
                        'Filename': file_info['filename'],
                        'Geometry Type': file_info['geometry_type'],
                        'Records': file_info['record_count'],
                        'CRS': file_info['crs']
                    })
                
                st.dataframe(pd.DataFrame(summary_data), use_container_width=True)
    
    with col2:
        st.subheader("Validation Results")
        if st.session_state.processed_data:
            for filename, file_info in st.session_state.processed_data.items():
                with st.expander(f"📊 {filename}"):
                    st.write(f"**Geometry Type:** {file_info['geometry_type']}")
                    st.write(f"**Record Count:** {file_info['record_count']}")
                    st.write(f"**CRS:** {file_info['crs']}")
                    st.write(f"**Fields:** {len(file_info['fields'])}")
                    
                    if st.button(f"Preview {filename}", key=f"preview_{filename}"):
                        preview_data(file_info['data'], filename)

def preview_data(data, filename):
    st.subheader(f"📊 Data Preview: {filename}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Attribute Data**")
        # Show first 100 rows to avoid performance issues
        display_data = data.head(100) if len(data) > 100 else data
        st.dataframe(display_data.drop('geometry', axis=1, errors='ignore'), use_container_width=True)
        
        if len(data) > 100:
            st.info(f"Showing first 100 of {len(data)} records")
    
    with col2:
        st.write("**Map Preview**")
        try:
            # Create Folium map
            if not data.empty and 'geometry' in data.columns:
                # Get bounds
                bounds = data.total_bounds
                center_lat = (bounds[1] + bounds[3]) / 2
                center_lon = (bounds[0] + bounds[2]) / 2
                
                m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
                
                # Add features to map (limit to first 1000 for performance)
                sample_data = data.head(1000) if len(data) > 1000 else data
                
                for idx, row in sample_data.iterrows():
                    if row.geometry is not None:
                        folium.GeoJson(
                            row.geometry.__geo_interface__,
                            tooltip=f"Feature {idx}"
                        ).add_to(m)
                
                st_folium(m, width=400, height=300)
                
                if len(data) > 1000:
                    st.info(f"Showing first 1000 of {len(data)} features on map")
            else:
                st.warning("No geometry data available for map preview")
                
        except Exception as e:
            st.error(f"Map preview error: {str(e)}")

def layer_management_section():
    st.header("🗂️ Layer Management")
    
    if not st.session_state.authenticated:
        st.warning("⚠️ Please authenticate first to manage layers.")
        return
    
    if not st.session_state.processed_data:
        st.warning("⚠️ Please upload and process shapefiles first.")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Layer Mapping")
        
        # Get user's feature layers
        try:
            layers = st.session_state.arcgis_manager.get_user_layers()
            layer_options = {f"{layer['title']} ({layer['id']})": layer['id'] for layer in layers}
            
            mappings = {}
            for filename in st.session_state.processed_data.keys():
                st.write(f"**{filename}**")
                selected_layer = st.selectbox(
                    f"Target Layer for {filename}",
                    options=list(layer_options.keys()),
                    key=f"layer_{filename}"
                )
                if selected_layer:
                    mappings[filename] = {
                        'layer_id': layer_options[selected_layer],
                        'layer_title': selected_layer.split(' (')[0]
                    }
            
            st.session_state.layer_mappings = mappings
            
        except Exception as e:
            st.error(f"Error fetching layers: {str(e)}")
            logger.log("error", f"Error fetching layers: {str(e)}")
    
    with col2:
        st.subheader("Schema Validation")
        
        if 'layer_mappings' in st.session_state:
            for filename, mapping in st.session_state.layer_mappings.items():
                with st.expander(f"🔍 {filename} → {mapping['layer_title']}"):
                    try:
                        # Get target layer schema
                        target_schema = st.session_state.arcgis_manager.get_layer_schema(mapping['layer_id'])
                        source_fields = st.session_state.processed_data[filename]['fields']
                        
                        # Compare schemas
                        schema_comparison = validator.compare_schemas(source_fields, target_schema)
                        
                        if schema_comparison['compatible']:
                            st.success("✅ Schema compatible")
                        else:
                            st.warning("⚠️ Schema differences detected")
                            
                            if schema_comparison['missing_in_target']:
                                st.write("**Missing in target:**")
                                st.write(", ".join(schema_comparison['missing_in_target']))
                            
                            if schema_comparison['missing_in_source']:
                                st.write("**Missing in source:**")
                                st.write(", ".join(schema_comparison['missing_in_source']))
                            
                            # Offer field mapping
                            if st.button(f"Configure Field Mapping for {filename}", key=f"map_{filename}"):
                                configure_field_mapping(filename, source_fields, target_schema)
                    
                    except Exception as e:
                        st.error(f"Schema validation error: {str(e)}")
    
    # Update operations
    st.subheader("🚀 Update Operations")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        create_backup = st.checkbox("Create backup before update", value=True)
    
    with col2:
        send_notification = st.checkbox("Send email notification", value=False)
    
    with col3:
        coordinate_system = st.selectbox(
            "Target Coordinate System",
            options=["Keep Original", "WGS84 (EPSG:4326)", "Web Mercator (EPSG:3857)"],
            help="Coordinate system for the updated layer"
        )
    
    if st.button("🚀 Update Layers", type="primary"):
        update_layers(create_backup, send_notification, coordinate_system)

def configure_field_mapping(filename, source_fields, target_schema):
    st.subheader(f"🔗 Field Mapping: {filename}")
    
    target_fields = [field['name'] for field in target_schema]
    
    field_mapping = {}
    
    st.write("Map source fields to target fields:")
    
    for source_field in source_fields:
        if source_field != 'geometry':  # Skip geometry field
            mapped_field = st.selectbox(
                f"Source: {source_field}",
                options=["<Skip>"] + target_fields,
                key=f"mapping_{filename}_{source_field}"
            )
            
            if mapped_field != "<Skip>":
                field_mapping[source_field] = mapped_field
    
    if st.button(f"Save Mapping for {filename}"):
        # Store field mapping in session state
        if 'field_mappings' not in st.session_state:
            st.session_state.field_mappings = {}
        st.session_state.field_mappings[filename] = field_mapping
        st.success("Field mapping saved!")

def update_layers(create_backup, send_notification, coordinate_system):
    if 'layer_mappings' not in st.session_state:
        st.error("No layer mappings configured")
        return
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    update_results = []
    total_operations = len(st.session_state.layer_mappings)
    
    for i, (filename, mapping) in enumerate(st.session_state.layer_mappings.items()):
        progress = i / total_operations
        progress_bar.progress(progress)
        status_text.text(f"Updating {mapping['layer_title']}...")
        
        try:
            # Create backup if requested
            if create_backup:
                backup_result = backup_manager.create_backup(
                    st.session_state.arcgis_manager,
                    mapping['layer_id'],
                    mapping['layer_title']
                )
                if not backup_result['success']:
                    st.warning(f"Backup failed for {mapping['layer_title']}: {backup_result['error']}")
            
            # Get data
            data = st.session_state.processed_data[filename]['data']
            
            # Apply field mapping if configured
            if 'field_mappings' in st.session_state and filename in st.session_state.field_mappings:
                data = validator.apply_field_mapping(data, st.session_state.field_mappings[filename])
            
            # Handle coordinate system transformation
            if coordinate_system != "Keep Original":
                data = validator.transform_coordinate_system(data, coordinate_system)
            
            # Update layer
            result = st.session_state.arcgis_manager.update_layer(
                mapping['layer_id'],
                data,
                mapping['layer_title']
            )
            
            update_results.append({
                'filename': filename,
                'layer_title': mapping['layer_title'],
                'layer_id': mapping['layer_id'],
                'success': result['success'],
                'message': result.get('message', ''),
                'timestamp': datetime.now().isoformat()
            })
            
            if result['success']:
                logger.log("info", f"Successfully updated {mapping['layer_title']}")
            else:
                logger.log("error", f"Failed to update {mapping['layer_title']}: {result.get('error', '')}")
                
        except Exception as e:
            update_results.append({
                'filename': filename,
                'layer_title': mapping['layer_title'],
                'layer_id': mapping['layer_id'],
                'success': False,
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            })
            logger.log("error", f"Error updating {mapping['layer_title']}: {str(e)}")
    
    progress_bar.progress(1.0)
    status_text.text("Update operations complete!")
    
    # Store results in session state
    st.session_state.update_history.extend(update_results)
    
    # Display results
    st.subheader("📊 Update Results")
    
    success_count = sum(1 for result in update_results if result['success'])
    failure_count = len(update_results) - success_count
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Updates", len(update_results))
    with col2:
        st.metric("Successful", success_count)
    with col3:
        st.metric("Failed", failure_count)
    
    # Detailed results
    results_df = pd.DataFrame(update_results)
    st.dataframe(results_df, use_container_width=True)
    
    # Send notification if requested
    if send_notification:
        try:
            notification_manager.send_update_notification(update_results)
            st.success("📧 Notification sent successfully!")
        except Exception as e:
            st.error(f"Failed to send notification: {str(e)}")
    
    # Export results
    if st.button("📥 Export Results"):
        export_data = export_manager.create_update_summary(update_results)
        st.download_button(
            label="Download CSV Report",
            data=export_data['csv'],
            file_name=f"update_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

def settings_section():
    st.header("⚙️ Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("General Settings")
        
        # Load current settings
        current_settings = settings_manager.load_settings()
        
        # Auto-save settings
        auto_save = st.checkbox(
            "Auto-save credentials",
            value=current_settings.get('auto_save', True)
        )
        
        # Email notification settings
        st.subheader("Email Notifications")
        email_enabled = st.checkbox(
            "Enable email notifications",
            value=current_settings.get('email_enabled', False)
        )
        
        if email_enabled:
            smtp_server = st.text_input(
                "SMTP Server",
                value=current_settings.get('smtp_server', 'smtp.gmail.com')
            )
            smtp_port = st.number_input(
                "SMTP Port",
                value=current_settings.get('smtp_port', 587),
                min_value=1,
                max_value=65535
            )
            email_from = st.text_input(
                "From Email",
                value=current_settings.get('email_from', '')
            )
            email_password = st.text_input(
                "Email Password",
                value=current_settings.get('email_password', ''),
                type="password"
            )
            email_to = st.text_input(
                "To Email",
                value=current_settings.get('email_to', '')
            )
        
        # Directory monitoring
        st.subheader("Directory Monitoring")
        monitor_enabled = st.checkbox(
            "Enable directory monitoring",
            value=current_settings.get('monitor_enabled', False)
        )
        
        if monitor_enabled:
            monitor_path = st.text_input(
                "Directory to Monitor",
                value=current_settings.get('monitor_path', '')
            )
        
        if st.button("💾 Save Settings"):
            new_settings = {
                'auto_save': auto_save,
                'email_enabled': email_enabled,
                'monitor_enabled': monitor_enabled
            }
            
            if email_enabled:
                new_settings.update({
                    'smtp_server': smtp_server,
                    'smtp_port': smtp_port,
                    'email_from': email_from,
                    'email_password': email_password,
                    'email_to': email_to
                })
            
            if monitor_enabled:
                new_settings['monitor_path'] = monitor_path
            
            # Merge with existing settings
            current_settings.update(new_settings)
            settings_manager.save_settings(current_settings)
            st.success("Settings saved successfully!")
    
    with col2:
        st.subheader("Backup Management")
        
        # List existing backups
        backups = backup_manager.list_backups()
        
        if backups:
            st.write("**Available Backups:**")
            for backup in backups:
                with st.expander(f"📦 {backup['layer_name']} - {backup['timestamp']}"):
                    st.write(f"**Layer ID:** {backup['layer_id']}")
                    st.write(f"**Size:** {backup['size']}")
                    st.write(f"**Records:** {backup['record_count']}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"🔄 Restore", key=f"restore_{backup['id']}"):
                            restore_backup(backup)
                    with col2:
                        if st.button(f"🗑️ Delete", key=f"delete_{backup['id']}"):
                            delete_backup(backup)
        else:
            st.info("No backups available")
        
        # Backup settings
        st.subheader("Backup Settings")
        max_backups = st.number_input(
            "Maximum backups per layer",
            value=current_settings.get('max_backups', 5),
            min_value=1,
            max_value=20
        )
        
        backup_compression = st.checkbox(
            "Compress backups",
            value=current_settings.get('backup_compression', True)
        )

def restore_backup(backup):
    if not st.session_state.authenticated:
        st.error("Authentication required")
        return
    
    try:
        with st.spinner(f"Restoring backup for {backup['layer_name']}..."):
            result = backup_manager.restore_backup(
                st.session_state.arcgis_manager,
                backup['id']
            )
            
            if result['success']:
                st.success(f"✅ Successfully restored {backup['layer_name']}")
                logger.log("info", f"Restored backup for {backup['layer_name']}")
            else:
                st.error(f"❌ Failed to restore backup: {result['error']}")
                logger.log("error", f"Failed to restore backup: {result['error']}")
                
    except Exception as e:
        st.error(f"Restore error: {str(e)}")
        logger.log("error", f"Restore error: {str(e)}")

def delete_backup(backup):
    try:
        result = backup_manager.delete_backup(backup['id'])
        if result['success']:
            st.success(f"✅ Deleted backup for {backup['layer_name']}")
            st.rerun()
        else:
            st.error(f"❌ Failed to delete backup: {result['error']}")
    except Exception as e:
        st.error(f"Delete error: {str(e)}")

def logs_section():
    st.header("📋 Logs")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        log_level = st.selectbox(
            "Filter by Level",
            options=["All", "INFO", "WARNING", "ERROR"],
            index=0
        )
        
        if st.button("🔄 Refresh Logs"):
            st.rerun()
        
        if st.button("🗑️ Clear Logs"):
            logger.clear_logs()
            st.success("Logs cleared")
            st.rerun()
    
    with col1:
        # Display logs
        try:
            logs = logger.get_logs(level=log_level if log_level != "All" else None)
            
            if logs:
                st.text_area(
                    "Log Output",
                    value="\n".join(logs),
                    height=400,
                    disabled=True
                )
            else:
                st.info("No logs available")
                
        except Exception as e:
            st.error(f"Error reading logs: {str(e)}")

def history_section():
    st.header("📈 Update History")
    
    if st.session_state.update_history:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        total_updates = len(st.session_state.update_history)
        successful_updates = sum(1 for h in st.session_state.update_history if h['success'])
        failed_updates = total_updates - successful_updates
        success_rate = (successful_updates / total_updates * 100) if total_updates > 0 else 0
        
        with col1:
            st.metric("Total Updates", total_updates)
        with col2:
            st.metric("Successful", successful_updates)
        with col3:
            st.metric("Failed", failed_updates)
        with col4:
            st.metric("Success Rate", f"{success_rate:.1f}%")
        
        # History table
        st.subheader("Update History")
        history_df = pd.DataFrame(st.session_state.update_history)
        
        # Add formatted timestamp
        history_df['formatted_time'] = pd.to_datetime(history_df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Reorder columns for better display
        display_columns = ['formatted_time', 'layer_title', 'filename', 'success', 'message']
        display_df = history_df[display_columns].copy()
        display_df.columns = ['Timestamp', 'Layer', 'Source File', 'Success', 'Message']
        
        st.dataframe(display_df, use_container_width=True)
        
        # Export history
        if st.button("📥 Export History"):
            csv_data = history_df.to_csv(index=False)
            st.download_button(
                label="Download History CSV",
                data=csv_data,
                file_name=f"update_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    else:
        st.info("No update history available")

if __name__ == "__main__":
    main()
