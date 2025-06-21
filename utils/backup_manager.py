import os
import json
import tempfile
import shutil
import gzip
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import streamlit as st
import pandas as pd
import geopandas as gpd

class BackupManager:
    """Manages backup operations for ArcGIS layers"""
    
    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = backup_dir
        self.metadata_file = os.path.join(backup_dir, "backup_metadata.json")
        self.ensure_backup_directory()
    
    def ensure_backup_directory(self):
        """Ensure backup directory exists"""
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
        except Exception as e:
            st.error(f"Error creating backup directory: {str(e)}")
    
    def create_backup(self, arcgis_manager, layer_id: str, layer_title: str, compress: bool = True) -> Dict[str, Any]:
        """
        Create a backup of a feature layer
        
        Args:
            arcgis_manager: ArcGIS manager instance
            layer_id: Layer ID to backup
            layer_title: Layer title
            compress: Whether to compress backup files
            
        Returns:
            Dict containing backup operation results
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_id = f"{layer_id}_{timestamp}"
            backup_folder = os.path.join(self.backup_dir, backup_id)
            
            # Create backup folder
            os.makedirs(backup_folder, exist_ok=True)
            
            # Get layer data
            layer_data = arcgis_manager.get_layer_data(layer_id, max_records=10000)
            layer_schema = arcgis_manager.get_layer_schema(layer_id)
            layer_stats = arcgis_manager.get_layer_statistics(layer_id)
            
            # Save data as shapefile
            data_file = os.path.join(backup_folder, "data.shp")
            if not layer_data.empty:
                # Ensure CRS is set
                if layer_data.crs is None:
                    layer_data = layer_data.set_crs('EPSG:4326')
                
                layer_data.to_file(data_file)
            else:
                # Create empty shapefile with schema
                self._create_empty_shapefile(data_file, layer_schema)
            
            # Save metadata
            metadata = {
                'backup_id': backup_id,
                'layer_id': layer_id,
                'layer_title': layer_title,
                'timestamp': timestamp,
                'datetime': datetime.now().isoformat(),
                'record_count': len(layer_data),
                'schema': layer_schema,
                'statistics': layer_stats,
                'compressed': compress,
                'files': []
            }
            
            # Get list of created files
            backup_files = []
            for file in os.listdir(backup_folder):
                file_path = os.path.join(backup_folder, file)
                file_size = os.path.getsize(file_path)
                backup_files.append({
                    'name': file,
                    'size': file_size,
                    'path': file_path
                })
            
            metadata['files'] = backup_files
            metadata['total_size'] = sum(f['size'] for f in backup_files)
            
            # Compress backup if requested
            if compress:
                compressed_file = f"{backup_folder}.tar.gz"
                self._compress_backup(backup_folder, compressed_file)
                
                # Remove original folder
                shutil.rmtree(backup_folder)
                
                # Update metadata
                metadata['compressed'] = True
                metadata['compressed_file'] = compressed_file
                metadata['compressed_size'] = os.path.getsize(compressed_file)
            
            # Save backup metadata
            self._save_backup_metadata(backup_id, metadata)
            
            return {
                'success': True,
                'backup_id': backup_id,
                'timestamp': timestamp,
                'record_count': len(layer_data),
                'size': metadata.get('compressed_size', metadata['total_size'])
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_empty_shapefile(self, file_path: str, schema: List[Dict[str, Any]]):
        """Create empty shapefile with given schema"""
        try:
            # Create empty GeoDataFrame with schema
            columns = {}
            for field in schema:
                field_name = field['name']
                field_type = field['type']
                
                if field_type in ['esriFieldTypeString']:
                    columns[field_name] = pd.Series(dtype='object')
                elif field_type in ['esriFieldTypeInteger']:
                    columns[field_name] = pd.Series(dtype='int64')
                elif field_type in ['esriFieldTypeDouble']:
                    columns[field_name] = pd.Series(dtype='float64')
                elif field_type in ['esriFieldTypeDate']:
                    columns[field_name] = pd.Series(dtype='datetime64[ns]')
                else:
                    columns[field_name] = pd.Series(dtype='object')
            
            # Create empty GeoDataFrame
            gdf = gpd.GeoDataFrame(columns, geometry=[])
            gdf = gdf.set_crs('EPSG:4326')
            
            # Save as shapefile
            gdf.to_file(file_path)
            
        except Exception as e:
            # Fallback: create minimal shapefile
            gdf = gpd.GeoDataFrame({'id': []}, geometry=[])
            gdf = gdf.set_crs('EPSG:4326')
            gdf.to_file(file_path)
    
    def _compress_backup(self, source_folder: str, compressed_file: str):
        """Compress backup folder"""
        try:
            import tarfile
            
            with tarfile.open(compressed_file, 'w:gz') as tar:
                tar.add(source_folder, arcname=os.path.basename(source_folder))
                
        except Exception as e:
            raise Exception(f"Error compressing backup: {str(e)}")
    
    def _save_backup_metadata(self, backup_id: str, metadata: Dict[str, Any]):
        """Save backup metadata"""
        try:
            # Load existing metadata
            all_metadata = self._load_all_metadata()
            
            # Add new backup
            all_metadata[backup_id] = metadata
            
            # Save metadata
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(all_metadata, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            st.error(f"Error saving backup metadata: {str(e)}")
    
    def _load_all_metadata(self) -> Dict[str, Any]:
        """Load all backup metadata"""
        try:
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception:
            return {}
    
    def list_backups(self, layer_id: str = None) -> List[Dict[str, Any]]:
        """
        List available backups
        
        Args:
            layer_id: Optional layer ID to filter by
            
        Returns:
            List of backup information
        """
        try:
            all_metadata = self._load_all_metadata()
            backups = []
            
            for backup_id, metadata in all_metadata.items():
                if layer_id is None or metadata.get('layer_id') == layer_id:
                    backup_info = {
                        'id': backup_id,
                        'layer_id': metadata.get('layer_id'),
                        'layer_name': metadata.get('layer_title'),
                        'timestamp': metadata.get('datetime'),
                        'record_count': metadata.get('record_count', 0),
                        'size': self._format_size(metadata.get('compressed_size', metadata.get('total_size', 0))),
                        'compressed': metadata.get('compressed', False)
                    }
                    backups.append(backup_info)
            
            # Sort by timestamp (newest first)
            backups.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return backups
            
        except Exception as e:
            st.error(f"Error listing backups: {str(e)}")
            return []
    
    def restore_backup(self, arcgis_manager, backup_id: str) -> Dict[str, Any]:
        """
        Restore a backup
        
        Args:
            arcgis_manager: ArcGIS manager instance
            backup_id: Backup ID to restore
            
        Returns:
            Dict containing restore operation results
        """
        try:
            # Get backup metadata
            all_metadata = self._load_all_metadata()
            
            if backup_id not in all_metadata:
                return {
                    'success': False,
                    'error': f"Backup {backup_id} not found"
                }
            
            metadata = all_metadata[backup_id]
            layer_id = metadata['layer_id']
            layer_title = metadata['layer_title']
            
            # Extract backup data
            with tempfile.TemporaryDirectory() as temp_dir:
                if metadata.get('compressed', False):
                    # Extract compressed backup
                    compressed_file = metadata.get('compressed_file')
                    if not os.path.exists(compressed_file):
                        return {
                            'success': False,
                            'error': f"Backup file not found: {compressed_file}"
                        }
                    
                    self._extract_backup(compressed_file, temp_dir)
                    data_folder = os.path.join(temp_dir, backup_id)
                else:
                    # Use uncompressed backup
                    data_folder = os.path.join(self.backup_dir, backup_id)
                
                # Find shapefile
                shp_file = None
                for file in os.listdir(data_folder):
                    if file.endswith('.shp'):
                        shp_file = os.path.join(data_folder, file)
                        break
                
                if not shp_file:
                    return {
                        'success': False,
                        'error': "No shapefile found in backup"
                    }
                
                # Read backup data
                backup_data = gpd.read_file(shp_file)
                
                # Restore data to layer
                result = arcgis_manager.update_layer(layer_id, backup_data, layer_title)
                
                if result['success']:
                    return {
                        'success': True,
                        'message': f"Successfully restored {layer_title} from backup",
                        'features_restored': len(backup_data)
                    }
                else:
                    return {
                        'success': False,
                        'error': f"Failed to restore backup: {result.get('error', 'Unknown error')}"
                    }
                    
        except Exception as e:
            return {
                'success': False,
                'error': f"Error restoring backup: {str(e)}"
            }
    
    def _extract_backup(self, compressed_file: str, extract_dir: str):
        """Extract compressed backup"""
        try:
            import tarfile
            
            with tarfile.open(compressed_file, 'r:gz') as tar:
                tar.extractall(extract_dir)
                
        except Exception as e:
            raise Exception(f"Error extracting backup: {str(e)}")
    
    def delete_backup(self, backup_id: str) -> Dict[str, Any]:
        """
        Delete a backup
        
        Args:
            backup_id: Backup ID to delete
            
        Returns:
            Dict containing deletion results
        """
        try:
            # Get backup metadata
            all_metadata = self._load_all_metadata()
            
            if backup_id not in all_metadata:
                return {
                    'success': False,
                    'error': f"Backup {backup_id} not found"
                }
            
            metadata = all_metadata[backup_id]
            
            # Delete backup files
            if metadata.get('compressed', False):
                # Delete compressed file
                compressed_file = metadata.get('compressed_file')
                if compressed_file and os.path.exists(compressed_file):
                    os.remove(compressed_file)
            else:
                # Delete backup folder
                backup_folder = os.path.join(self.backup_dir, backup_id)
                if os.path.exists(backup_folder):
                    shutil.rmtree(backup_folder)
            
            # Remove from metadata
            del all_metadata[backup_id]
            
            # Save updated metadata
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(all_metadata, f, indent=2, ensure_ascii=False)
            
            return {
                'success': True,
                'message': f"Backup {backup_id} deleted successfully"
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Error deleting backup: {str(e)}"
            }
    
    def cleanup_old_backups(self, max_age_days: int = 30, max_backups_per_layer: int = 5) -> Dict[str, Any]:
        """
        Clean up old backups based on age and count
        
        Args:
            max_age_days: Maximum age in days
            max_backups_per_layer: Maximum backups per layer
            
        Returns:
            Dict containing cleanup results
        """
        try:
            all_metadata = self._load_all_metadata()
            deleted_backups = []
            cutoff_date = datetime.now() - timedelta(days=max_age_days)
            
            # Group backups by layer
            layer_backups = {}
            for backup_id, metadata in all_metadata.items():
                layer_id = metadata.get('layer_id')
                if layer_id not in layer_backups:
                    layer_backups[layer_id] = []
                layer_backups[layer_id].append((backup_id, metadata))
            
            # Clean up each layer's backups
            for layer_id, backups in layer_backups.items():
                # Sort by date (newest first)
                backups.sort(key=lambda x: x[1].get('datetime', ''), reverse=True)
                
                # Keep only the most recent backups
                backups_to_keep = backups[:max_backups_per_layer]
                backups_to_check = backups[max_backups_per_layer:]
                
                # Delete old backups
                for backup_id, metadata in backups_to_check:
                    backup_date = datetime.fromisoformat(metadata.get('datetime', ''))
                    if backup_date < cutoff_date:
                        result = self.delete_backup(backup_id)
                        if result['success']:
                            deleted_backups.append(backup_id)
            
            return {
                'success': True,
                'deleted_count': len(deleted_backups),
                'deleted_backups': deleted_backups
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Error cleaning up backups: {str(e)}"
            }
    
    def get_backup_statistics(self) -> Dict[str, Any]:
        """
        Get backup statistics
        
        Returns:
            Dict containing backup statistics
        """
        try:
            all_metadata = self._load_all_metadata()
            
            stats = {
                'total_backups': len(all_metadata),
                'total_size': 0,
                'layers_backed_up': set(),
                'oldest_backup': None,
                'newest_backup': None,
                'compressed_backups': 0
            }
            
            backup_dates = []
            
            for backup_id, metadata in all_metadata.items():
                # Size
                size = metadata.get('compressed_size', metadata.get('total_size', 0))
                stats['total_size'] += size
                
                # Layers
                layer_id = metadata.get('layer_id')
                if layer_id:
                    stats['layers_backed_up'].add(layer_id)
                
                # Dates
                backup_date = metadata.get('datetime')
                if backup_date:
                    backup_dates.append(backup_date)
                
                # Compression
                if metadata.get('compressed', False):
                    stats['compressed_backups'] += 1
            
            # Date statistics
            if backup_dates:
                backup_dates.sort()
                stats['oldest_backup'] = backup_dates[0]
                stats['newest_backup'] = backup_dates[-1]
            
            stats['layers_backed_up'] = len(stats['layers_backed_up'])
            stats['total_size_formatted'] = self._format_size(stats['total_size'])
            
            return stats
            
        except Exception as e:
            return {
                'error': f"Error getting backup statistics: {str(e)}"
            }
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human readable format"""
        try:
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.1f} {unit}"
                size_bytes /= 1024.0
            return f"{size_bytes:.1f} TB"
        except:
            return "Unknown"
    
    def export_backup_list(self) -> str:
        """
        Export backup list as CSV
        
        Returns:
            CSV string of backup information
        """
        try:
            backups = self.list_backups()
            
            if not backups:
                return "No backups available"
            
            df = pd.DataFrame(backups)
            return df.to_csv(index=False)
            
        except Exception as e:
            return f"Error exporting backup list: {str(e)}"
