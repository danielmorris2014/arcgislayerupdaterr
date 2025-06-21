import zipfile
import tempfile
import os
import geopandas as gpd
import pandas as pd
from typing import Dict, List, Any, Optional
import streamlit as st

class FileHandler:
    """Handles file operations for shapefile processing"""
    
    def __init__(self):
        self.required_extensions = ['.shp', '.shx', '.dbf']
        self.optional_extensions = ['.prj', '.cpg', '.sbn', '.sbx']
    
    def validate_zip_file(self, zip_file) -> Dict[str, Any]:
        """
        Validate that zip file contains required shapefile components
        
        Args:
            zip_file: Uploaded zip file
            
        Returns:
            Dict containing validation results
        """
        try:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                
                # Find shapefile base names
                shapefiles = {}
                for file_path in file_list:
                    if file_path.endswith('.shp'):
                        base_name = os.path.splitext(os.path.basename(file_path))[0]
                        shapefiles[base_name] = {'found_extensions': ['.shp']}
                
                # Check for required components for each shapefile
                for base_name in shapefiles.keys():
                    for file_path in file_list:
                        file_base = os.path.splitext(os.path.basename(file_path))[0]
                        if file_base == base_name:
                            ext = os.path.splitext(file_path)[1].lower()
                            if ext in self.required_extensions + self.optional_extensions:
                                shapefiles[base_name]['found_extensions'].append(ext)
                
                # Validate each shapefile
                valid_shapefiles = []
                invalid_shapefiles = []
                
                for base_name, info in shapefiles.items():
                    missing_required = [ext for ext in self.required_extensions 
                                     if ext not in info['found_extensions']]
                    
                    if not missing_required:
                        valid_shapefiles.append(base_name)
                    else:
                        invalid_shapefiles.append({
                            'name': base_name,
                            'missing': missing_required
                        })
                
                return {
                    'valid': len(valid_shapefiles) > 0,
                    'valid_shapefiles': valid_shapefiles,
                    'invalid_shapefiles': invalid_shapefiles,
                    'missing_files': [item['missing'] for item in invalid_shapefiles] if invalid_shapefiles else []
                }
                
        except zipfile.BadZipFile:
            return {
                'valid': False,
                'error': 'Invalid zip file format',
                'missing_files': []
            }
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'missing_files': []
            }
    
    def extract_zip_file(self, zip_file, extract_path: str) -> Dict[str, str]:
        """
        Extract zip file and return paths to shapefile components
        
        Args:
            zip_file: Uploaded zip file
            extract_path: Directory to extract files to
            
        Returns:
            Dict mapping file types to their paths
        """
        try:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
                
                # Find shapefile components
                extracted_files = {}
                
                for root, dirs, files in os.walk(extract_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        ext = os.path.splitext(file)[1].lower()
                        
                        if ext == '.shp':
                            extracted_files['shp'] = file_path
                        elif ext == '.shx':
                            extracted_files['shx'] = file_path
                        elif ext == '.dbf':
                            extracted_files['dbf'] = file_path
                        elif ext == '.prj':
                            extracted_files['prj'] = file_path
                        elif ext == '.cpg':
                            extracted_files['cpg'] = file_path
                
                return extracted_files
                
        except Exception as e:
            raise Exception(f"Error extracting zip file: {str(e)}")
    
    def read_shapefile(self, shapefile_path: str) -> gpd.GeoDataFrame:
        """
        Read shapefile into GeoDataFrame
        
        Args:
            shapefile_path: Path to .shp file
            
        Returns:
            GeoDataFrame containing shapefile data
        """
        try:
            gdf = gpd.read_file(shapefile_path)
            
            # Handle encoding issues
            if gdf.empty:
                # Try different encodings
                encodings = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']
                for encoding in encodings:
                    try:
                        gdf = gpd.read_file(shapefile_path, encoding=encoding)
                        if not gdf.empty:
                            break
                    except:
                        continue
            
            # Clean column names
            gdf.columns = [col.strip() for col in gdf.columns]
            
            return gdf
            
        except Exception as e:
            raise Exception(f"Error reading shapefile: {str(e)}")
    
    def get_shapefile_info(self, gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
        """
        Extract information from GeoDataFrame
        
        Args:
            gdf: GeoDataFrame
            
        Returns:
            Dict containing shapefile information
        """
        try:
            info = {
                'record_count': len(gdf),
                'fields': list(gdf.columns),
                'geometry_types': gdf.geom_type.unique().tolist(),
                'crs': gdf.crs.to_string() if gdf.crs else None,
                'bounds': gdf.total_bounds.tolist() if not gdf.empty else None,
                'has_geometry': 'geometry' in gdf.columns and not gdf.geometry.isna().all()
            }
            
            # Field type information
            field_types = {}
            for column in gdf.columns:
                if column != 'geometry':
                    dtype = str(gdf[column].dtype)
                    field_types[column] = dtype
            
            info['field_types'] = field_types
            
            return info
            
        except Exception as e:
            raise Exception(f"Error getting shapefile info: {str(e)}")
    
    def validate_field_types(self, gdf: gpd.GeoDataFrame) -> Dict[str, List[str]]:
        """
        Validate field types and identify potential issues
        
        Args:
            gdf: GeoDataFrame
            
        Returns:
            Dict containing validation results
        """
        issues = {
            'invalid_geometries': [],
            'empty_fields': [],
            'potential_encoding_issues': []
        }
        
        try:
            # Check for invalid geometries
            if 'geometry' in gdf.columns:
                invalid_geoms = gdf[~gdf.geometry.is_valid]
                if not invalid_geoms.empty:
                    issues['invalid_geometries'] = invalid_geoms.index.tolist()
            
            # Check for empty fields
            for column in gdf.columns:
                if column != 'geometry':
                    if gdf[column].isna().all():
                        issues['empty_fields'].append(column)
            
            # Check for potential encoding issues
            for column in gdf.columns:
                if column != 'geometry' and gdf[column].dtype == 'object':
                    # Look for common encoding issue patterns
                    sample_values = gdf[column].dropna().head(100)
                    for value in sample_values:
                        if isinstance(value, str):
                            # Check for garbled characters that might indicate encoding issues
                            if any(char in str(value) for char in ['Ã', 'â', '¿', '�']):
                                if column not in issues['potential_encoding_issues']:
                                    issues['potential_encoding_issues'].append(column)
                                break
            
            return issues
            
        except Exception as e:
            raise Exception(f"Error validating field types: {str(e)}")
    
    def prepare_for_upload(self, gdf: gpd.GeoDataFrame, target_crs: str = None) -> gpd.GeoDataFrame:
        """
        Prepare GeoDataFrame for upload to ArcGIS Online
        
        Args:
            gdf: Source GeoDataFrame
            target_crs: Target coordinate reference system
            
        Returns:
            Prepared GeoDataFrame
        """
        try:
            # Make a copy to avoid modifying original
            prepared_gdf = gdf.copy()
            
            # Reproject if needed
            if target_crs and prepared_gdf.crs != target_crs:
                prepared_gdf = prepared_gdf.to_crs(target_crs)
            
            # Clean invalid geometries
            if 'geometry' in prepared_gdf.columns:
                # Fix invalid geometries
                invalid_mask = ~prepared_gdf.geometry.is_valid
                if invalid_mask.any():
                    prepared_gdf.loc[invalid_mask, 'geometry'] = prepared_gdf.loc[invalid_mask, 'geometry'].buffer(0)
                
                # Remove null geometries
                prepared_gdf = prepared_gdf[prepared_gdf.geometry.notna()]
            
            # Clean field names (ArcGIS Online field name restrictions)
            new_columns = {}
            for col in prepared_gdf.columns:
                if col != 'geometry':
                    # Remove special characters and limit length
                    clean_name = ''.join(c for c in col if c.isalnum() or c == '_')[:64]
                    if clean_name != col:
                        new_columns[col] = clean_name
            
            if new_columns:
                prepared_gdf = prepared_gdf.rename(columns=new_columns)
            
            # Handle data types
            for column in prepared_gdf.columns:
                if column != 'geometry':
                    # Convert problematic data types
                    if prepared_gdf[column].dtype == 'object':
                        # Try to convert to string, handling encoding issues
                        prepared_gdf[column] = prepared_gdf[column].astype(str)
                        prepared_gdf[column] = prepared_gdf[column].replace('nan', '')
            
            return prepared_gdf
            
        except Exception as e:
            raise Exception(f"Error preparing data for upload: {str(e)}")
