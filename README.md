# ArcGIS Layer Updater

A comprehensive Streamlit web application for managing ArcGIS Online feature layers with advanced geospatial data processing capabilities.

## Features

- **Shapefile Upload & Processing**: Handle .zip files containing shapefiles with robust error handling
- **Direct Layer Creation**: Bypass CSV conversion issues with multiple upload methods
- **Layer Styling**: Custom colors, popups, and sharing configurations
- **Content Management**: View, update, and delete existing layers
- **Web Map Integration**: Add layers directly to web maps
- **Debug Mode**: Comprehensive logging and troubleshooting tools

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install streamlit geopandas pandas arcgis folium streamlit-folium
   ```

2. **Run the Application**:
   ```bash
   streamlit run app.py
   ```

3. **Login**: Enter your ArcGIS Online credentials

4. **Upload**: Select a shapefile (.zip) and configure layer settings

## File Structure

```
├── app.py                    # Main application with full features
├── simplified_app.py         # Streamlined version without CSV operations
├── complete_app_export.py    # Complete code export for reference
├── data_handler_demo.py      # Safe data handling utilities
├── utils/
│   ├── arcgis_manager.py     # ArcGIS operations manager
│   ├── backup_manager.py     # Backup and restore functionality
│   └── export_manager.py     # Data export utilities
├── backups/                  # Backup storage directory
├── update_log.txt           # Application logs
├── user_settings.json       # User preferences
└── README.md                # This file
```

## Supported File Formats

- **Shapefile (.zip)**: Must contain .shp, .shx files (minimum)
- **Empty .dbf Files**: Automatically handled with default ID column
- **Coordinate Systems**: Automatically reprojected to WGS84

## Error Resolution

The application includes multiple fallback methods to handle common issues:

1. **Direct Shapefile Upload**: Primary method using temporary files
2. **CSV Conversion**: Fallback method with WKT geometry conversion
3. **Minimal Feature Collection**: Final fallback for problematic data

## Debug Mode

Enable debug mode to see:
- Step-by-step processing information
- Data type validation at each stage
- Detailed error messages with solutions
- Processing logs and performance metrics

## Authentication

The application connects to ArcGIS Online using your organization credentials:
- Username and password authentication
- Secure session management
- Organization permission validation

## Common Issues

**Layer not appearing in portal:**
- Wait 1-5 minutes for ArcGIS Online indexing
- Use the direct portal link provided after upload
- Check Content > My Content in ArcGIS Online

**Upload errors:**
- Ensure .zip contains required shapefile components
- Verify ArcGIS Online permissions
- Check organization content creation privileges

## Development

### Key Components

- **Authentication**: Secure ArcGIS Online login
- **File Processing**: Shapefile validation and conversion
- **Layer Creation**: Multiple upload methods with fallbacks
- **Error Handling**: Comprehensive logging and debugging
- **UI Components**: Streamlit interface with forms and navigation

### Recent Updates

- Fixed persistent "dict object has no attribute to_csv" error
- Implemented direct shapefile upload method
- Added comprehensive error handling and logging
- Enhanced debug mode with detailed information
- Improved portal link generation and verification

## License

This project is built for educational and professional GIS workflow automation.

## Support

For issues or questions:
1. Enable debug mode to view detailed logs
2. Check the troubleshooting section in the application
3. Review the update_log.txt file for processing details