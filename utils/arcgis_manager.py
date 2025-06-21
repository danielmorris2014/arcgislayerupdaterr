import os
from arcgis.gis import GIS
from arcgis.features import FeatureLayer, FeatureSet
import geopandas as gpd
import pandas as pd
from typing import Dict, List, Any, Optional
import tempfile
import json
import time

class ArcGISManager:
    """Manages ArcGIS Online operations"""
    
    def __init__(self, api_key: str, username: str, portal_url: str = "https://www.arcgis.com"):
        self.api_key = api_key
        self.username = username
        self.portal_url = portal_url
        self.gis = None
        self.authenticated = False
    
    def authenticate(self) -> bool:
        """
        Authenticate with ArcGIS Online
        
        Returns:
            bool: True if authentication successful
        """
        try:
            # Try token authentication first
            self.gis = GIS(self.portal_url, token=self.api_key)
            
            # Verify authentication by accessing user properties
            user = self.gis.users.me
            if user:
                self.authenticated = True
                return True
            else:
                # Try username/password if token fails
                self.gis = GIS(self.portal_url, username=self.username, password=self.api_key)
                user = self.gis.users.me
                if user:
                    self.authenticated = True
                    return True
                    
        except Exception as e:
            self.authenticated = False
            raise Exception(f"Authentication failed: {str(e)}")
        
        return False
    
    def get_user_layers(self) -> List[Dict[str, Any]]:
        """
        Get list of user's feature layers
        
        Returns:
            List of layer information dictionaries
        """
        if not self.authenticated:
            raise Exception("Not authenticated")
        
        try:
            layers = []
            
            # Search for feature layers owned by the user
            search_results = self.gis.content.search(
                query=f"owner:{self.username}",
                item_type="Feature Layer",
                max_items=100
            )
            
            for item in search_results:
                try:
                    # Get layer details
                    layer_info = {
                        'id': item.id,
                        'title': item.title,
                        'description': item.description or '',
                        'type': item.type,
                        'created': item.created,
                        'modified': item.modified,
                        'url': item.url,
                        'layer_count': len(item.layers) if hasattr(item, 'layers') else 0
                    }
                    
                    # Get additional layer properties if available
                    if hasattr(item, 'layers') and item.layers:
                        layer_info['geometry_type'] = item.layers[0].properties.get('geometryType', 'Unknown')
                        layer_info['feature_count'] = item.layers[0].properties.get('featureCount', 0)
                    
                    layers.append(layer_info)
                    
                except Exception as e:
                    # Skip layers that can't be accessed
                    continue
            
            return layers
            
        except Exception as e:
            raise Exception(f"Error fetching user layers: {str(e)}")
    
    def get_layer_schema(self, layer_id: str) -> List[Dict[str, Any]]:
        """
        Get schema information for a feature layer
        
        Args:
            layer_id: ArcGIS Online item ID
            
        Returns:
            List of field dictionaries
        """
        if not self.authenticated:
            raise Exception("Not authenticated")
        
        try:
            # Get the item
            item = self.gis.content.get(layer_id)
            if not item:
                raise Exception(f"Layer with ID {layer_id} not found")
            
            # Get the first layer (assuming single layer feature service)
            if hasattr(item, 'layers') and item.layers:
                layer = item.layers[0]
                
                # Get field information
                fields = []
                for field in layer.properties.fields:
                    field_info = {
                        'name': field.name,
                        'type': field.type,
                        'alias': field.alias,
                        'length': getattr(field, 'length', None),
                        'nullable': getattr(field, 'nullable', True),
                        'editable': getattr(field, 'editable', True)
                    }
                    fields.append(field_info)
                
                return fields
            else:
                raise Exception("No layers found in feature service")
                
        except Exception as e:
            raise Exception(f"Error getting layer schema: {str(e)}")
    
    def get_layer_data(self, layer_id: str, max_records: int = 1000) -> gpd.GeoDataFrame:
        """
        Get data from a feature layer
        
        Args:
            layer_id: ArcGIS Online item ID
            max_records: Maximum number of records to retrieve
            
        Returns:
            GeoDataFrame containing layer data
        """
        if not self.authenticated:
            raise Exception("Not authenticated")
        
        try:
            # Get the item
            item = self.gis.content.get(layer_id)
            if not item:
                raise Exception(f"Layer with ID {layer_id} not found")
            
            # Get the first layer
            if hasattr(item, 'layers') and item.layers:
                layer = item.layers[0]
                
                # Query features
                feature_set = layer.query(
                    where="1=1",
                    out_fields="*",
                    return_geometry=True,
                    result_record_count=max_records
                )
                
                # Convert to GeoDataFrame
                if feature_set.features:
                    # Convert features to GeoDataFrame
                    gdf = feature_set.sdf
                    return gdf
                else:
                    # Return empty GeoDataFrame with correct schema
                    fields = self.get_layer_schema(layer_id)
                    columns = [field['name'] for field in fields if field['name'] != 'geometry']
                    return gpd.GeoDataFrame(columns=columns + ['geometry'])
                    
            else:
                raise Exception("No layers found in feature service")
                
        except Exception as e:
            raise Exception(f"Error getting layer data: {str(e)}")
    
    def update_layer(self, layer_id: str, data: gpd.GeoDataFrame, layer_title: str) -> Dict[str, Any]:
        """
        Update feature layer with new data
        
        Args:
            layer_id: ArcGIS Online item ID
            data: GeoDataFrame containing new data
            layer_title: Layer title for logging
            
        Returns:
            Dict containing operation results
        """
        if not self.authenticated:
            raise Exception("Not authenticated")
        
        try:
            # Get the item
            item = self.gis.content.get(layer_id)
            if not item:
                return {
                    'success': False,
                    'error': f"Layer with ID {layer_id} not found"
                }
            
            # Get the first layer
            if not (hasattr(item, 'layers') and item.layers):
                return {
                    'success': False,
                    'error': "No layers found in feature service"
                }
            
            layer = item.layers[0]
            
            # Prepare data for upload
            # Convert GeoDataFrame to feature set format
            try:
                # Create temporary shapefile
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_shp = os.path.join(temp_dir, "temp_data.shp")
                    
                    # Ensure CRS is set (default to WGS84 if missing)
                    if data.crs is None:
                        data = data.set_crs('EPSG:4326')
                    
                    # Write to shapefile
                    data.to_file(temp_shp)
                    
                    # Create feature collection from shapefile
                    feature_collection = {
                        "type": "FeatureCollection",
                        "features": []
                    }
                    
                    # Convert each row to GeoJSON feature
                    for idx, row in data.iterrows():
                        if row.geometry is not None:
                            feature = {
                                "type": "Feature",
                                "geometry": row.geometry.__geo_interface__,
                                "properties": {}
                            }
                            
                            # Add attributes (excluding geometry)
                            for col in data.columns:
                                if col != 'geometry':
                                    value = row[col]
                                    # Handle NaN and None values
                                    if pd.isna(value):
                                        value = None
                                    elif isinstance(value, (pd.Timestamp, pd.DatetimeIndex)):
                                        value = str(value)
                                    feature["properties"][col] = value
                            
                            feature_collection["features"].append(feature)
                    
                    # Overwrite layer data
                    # First, delete all existing features
                    delete_result = layer.delete_features(where="1=1")
                    
                    if delete_result.get('deleteResults'):
                        # Add new features in batches
                        batch_size = 1000
                        features = feature_collection["features"]
                        
                        success_count = 0
                        error_count = 0
                        
                        for i in range(0, len(features), batch_size):
                            batch = features[i:i + batch_size]
                            
                            # Create FeatureSet from batch
                            batch_collection = {
                                "type": "FeatureCollection",
                                "features": batch
                            }
                            
                            # Add features
                            add_result = layer.edit_features(adds=batch_collection["features"])
                            
                            if add_result.get('addResults'):
                                for result in add_result['addResults']:
                                    if result.get('success'):
                                        success_count += 1
                                    else:
                                        error_count += 1
                            
                            # Small delay between batches
                            time.sleep(0.1)
                        
                        return {
                            'success': True,
                            'message': f"Successfully updated {success_count} features",
                            'features_added': success_count,
                            'errors': error_count
                        }
                    else:
                        return {
                            'success': False,
                            'error': "Failed to delete existing features"
                        }
                        
            except Exception as e:
                return {
                    'success': False,
                    'error': f"Error processing data: {str(e)}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Error updating layer: {str(e)}"
            }
    
    def create_backup_item(self, layer_id: str, backup_title: str) -> Dict[str, Any]:
        """
        Create a backup copy of a feature layer
        
        Args:
            layer_id: Source layer ID
            backup_title: Title for backup item
            
        Returns:
            Dict containing backup operation results
        """
        if not self.authenticated:
            raise Exception("Not authenticated")
        
        try:
            # Get source item
            source_item = self.gis.content.get(layer_id)
            if not source_item:
                return {
                    'success': False,
                    'error': f"Source layer {layer_id} not found"
                }
            
            # Clone the item
            backup_item = source_item.copy(title=backup_title)
            
            if backup_item:
                return {
                    'success': True,
                    'backup_id': backup_item.id,
                    'backup_title': backup_item.title,
                    'backup_url': backup_item.url
                }
            else:
                return {
                    'success': False,
                    'error': "Failed to create backup copy"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Error creating backup: {str(e)}"
            }
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to ArcGIS Online
        
        Returns:
            Dict containing connection test results
        """
        try:
            if not self.authenticated:
                return {
                    'success': False,
                    'error': "Not authenticated"
                }
            
            # Try to access user properties
            user = self.gis.users.me
            
            return {
                'success': True,
                'username': user.username,
                'full_name': user.fullName,
                'role': user.role,
                'organization': self.gis.properties.name if hasattr(self.gis, 'properties') else 'Unknown'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Connection test failed: {str(e)}"
            }
    
    def get_layer_statistics(self, layer_id: str) -> Dict[str, Any]:
        """
        Get statistics for a feature layer
        
        Args:
            layer_id: Layer ID
            
        Returns:
            Dict containing layer statistics
        """
        if not self.authenticated:
            raise Exception("Not authenticated")
        
        try:
            # Get the item
            item = self.gis.content.get(layer_id)
            if not item:
                return {
                    'success': False,
                    'error': f"Layer with ID {layer_id} not found"
                }
            
            # Get the first layer
            if hasattr(item, 'layers') and item.layers:
                layer = item.layers[0]
                
                # Get feature count
                count_result = layer.query(where="1=1", return_count_only=True)
                feature_count = count_result if isinstance(count_result, int) else 0
                
                # Get layer properties
                properties = layer.properties
                
                stats = {
                    'success': True,
                    'feature_count': feature_count,
                    'geometry_type': properties.get('geometryType', 'Unknown'),
                    'spatial_reference': properties.get('spatialReference', {}),
                    'extent': properties.get('extent', {}),
                    'fields': len(properties.get('fields', [])),
                    'has_attachments': properties.get('hasAttachments', False),
                    'max_record_count': properties.get('maxRecordCount', 0)
                }
                
                return stats
            else:
                return {
                    'success': False,
                    'error': "No layers found in feature service"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Error getting layer statistics: {str(e)}"
            }
