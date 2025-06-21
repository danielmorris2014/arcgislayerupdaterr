import geopandas as gpd
import pandas as pd
from typing import Dict, List, Any, Optional
import pyproj
from pyproj import CRS, Transformer
import warnings

class Validator:
    """Handles validation operations for shapefiles and schemas"""
    
    def __init__(self):
        self.supported_geometry_types = [
            'Point', 'MultiPoint', 'LineString', 'MultiLineString',
            'Polygon', 'MultiPolygon'
        ]
        self.arcgis_field_types = {
            'esriFieldTypeOID': 'object_id',
            'esriFieldTypeString': 'string',
            'esriFieldTypeInteger': 'integer',
            'esriFieldTypeDouble': 'double',
            'esriFieldTypeDate': 'date',
            'esriFieldTypeGeometry': 'geometry',
            'esriFieldTypeGUID': 'guid',
            'esriFieldTypeGlobalID': 'global_id'
        }
    
    def validate_geometry(self, gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
        """
        Validate geometry in GeoDataFrame
        
        Args:
            gdf: GeoDataFrame to validate
            
        Returns:
            Dict containing validation results
        """
        validation_results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'statistics': {}
        }
        
        try:
            if 'geometry' not in gdf.columns:
                validation_results['valid'] = False
                validation_results['errors'].append("No geometry column found")
                return validation_results
            
            # Check for null geometries
            null_count = gdf.geometry.isna().sum()
            if null_count > 0:
                validation_results['warnings'].append(f"{null_count} features have null geometry")
            
            # Check for invalid geometries
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                invalid_mask = ~gdf.geometry.is_valid
                invalid_count = invalid_mask.sum()
                
                if invalid_count > 0:
                    validation_results['warnings'].append(f"{invalid_count} features have invalid geometry")
                    validation_results['invalid_indices'] = gdf[invalid_mask].index.tolist()
            
            # Check geometry types
            geom_types = gdf.geom_type.unique()
            unsupported_types = [gt for gt in geom_types if gt not in self.supported_geometry_types]
            
            if unsupported_types:
                validation_results['errors'].append(f"Unsupported geometry types: {unsupported_types}")
                validation_results['valid'] = False
            
            # Calculate statistics
            validation_results['statistics'] = {
                'total_features': len(gdf),
                'null_geometries': null_count,
                'invalid_geometries': invalid_count,
                'geometry_types': geom_types.tolist(),
                'bounds': gdf.total_bounds.tolist() if not gdf.empty else None
            }
            
            return validation_results
            
        except Exception as e:
            validation_results['valid'] = False
            validation_results['errors'].append(f"Geometry validation error: {str(e)}")
            return validation_results
    
    def validate_coordinate_system(self, gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
        """
        Validate and analyze coordinate reference system
        
        Args:
            gdf: GeoDataFrame to validate
            
        Returns:
            Dict containing CRS validation results
        """
        crs_info = {
            'has_crs': False,
            'crs_string': None,
            'crs_name': None,
            'is_geographic': False,
            'is_projected': False,
            'units': None,
            'recommendations': []
        }
        
        try:
            if gdf.crs is not None:
                crs_info['has_crs'] = True
                crs_info['crs_string'] = gdf.crs.to_string()
                
                # Get CRS details
                if hasattr(gdf.crs, 'name'):
                    crs_info['crs_name'] = gdf.crs.name
                
                # Check if geographic or projected
                crs_info['is_geographic'] = gdf.crs.is_geographic
                crs_info['is_projected'] = gdf.crs.is_projected
                
                # Get units
                if hasattr(gdf.crs, 'axis_info'):
                    units = [axis.unit_name for axis in gdf.crs.axis_info]
                    crs_info['units'] = units
                
                # Provide recommendations
                if gdf.crs.to_epsg() == 4326:
                    crs_info['recommendations'].append("WGS84 - Good for web mapping")
                elif gdf.crs.to_epsg() == 3857:
                    crs_info['recommendations'].append("Web Mercator - Optimized for web mapping")
                elif crs_info['is_geographic']:
                    crs_info['recommendations'].append("Consider reprojecting to Web Mercator (EPSG:3857) for web mapping")
                elif crs_info['is_projected']:
                    crs_info['recommendations'].append("Consider the coordinate system compatibility with your target layers")
            else:
                crs_info['recommendations'].append("No CRS defined - consider setting to WGS84 (EPSG:4326)")
            
            return crs_info
            
        except Exception as e:
            crs_info['error'] = f"CRS validation error: {str(e)}"
            return crs_info
    
    def compare_schemas(self, source_fields: List[str], target_schema: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare source and target schemas
        
        Args:
            source_fields: List of source field names
            target_schema: List of target field dictionaries
            
        Returns:
            Dict containing schema comparison results
        """
        comparison = {
            'compatible': True,
            'missing_in_target': [],
            'missing_in_source': [],
            'type_mismatches': [],
            'recommendations': []
        }
        
        try:
            # Extract target field names
            target_fields = [field['name'] for field in target_schema if field['name'] not in ['OBJECTID', 'GlobalID']]
            
            # Find missing fields
            source_set = set(field for field in source_fields if field != 'geometry')
            target_set = set(target_fields)
            
            comparison['missing_in_target'] = list(source_set - target_set)
            comparison['missing_in_source'] = list(target_set - source_set)
            
            # Check for required fields in target that are missing in source
            required_target_fields = [field for field in target_schema 
                                    if not field.get('nullable', True) and field['name'] not in ['OBJECTID', 'GlobalID']]
            
            missing_required = [field['name'] for field in required_target_fields 
                              if field['name'] not in source_fields]
            
            if missing_required:
                comparison['missing_required'] = missing_required
                comparison['compatible'] = False
            
            # Determine overall compatibility
            if comparison['missing_in_target'] or comparison['missing_in_source']:
                comparison['compatible'] = False
            
            # Generate recommendations
            if comparison['missing_in_target']:
                comparison['recommendations'].append("Consider field mapping or adding missing fields to target layer")
            
            if comparison['missing_in_source']:
                comparison['recommendations'].append("Source data is missing some target fields - they will be set to null")
            
            if comparison['compatible']:
                comparison['recommendations'].append("Schemas are compatible for direct update")
            
            return comparison
            
        except Exception as e:
            comparison['compatible'] = False
            comparison['error'] = f"Schema comparison error: {str(e)}"
            return comparison
    
    def apply_field_mapping(self, gdf: gpd.GeoDataFrame, field_mapping: Dict[str, str]) -> gpd.GeoDataFrame:
        """
        Apply field mapping to GeoDataFrame
        
        Args:
            gdf: Source GeoDataFrame
            field_mapping: Dict mapping source fields to target fields
            
        Returns:
            GeoDataFrame with mapped fields
        """
        try:
            # Create a copy to avoid modifying original
            mapped_gdf = gdf.copy()
            
            # Apply field mapping
            for source_field, target_field in field_mapping.items():
                if source_field in mapped_gdf.columns and source_field != target_field:
                    mapped_gdf = mapped_gdf.rename(columns={source_field: target_field})
            
            # Remove unmapped fields (except geometry)
            mapped_fields = list(field_mapping.values()) + ['geometry']
            columns_to_keep = [col for col in mapped_gdf.columns if col in mapped_fields]
            mapped_gdf = mapped_gdf[columns_to_keep]
            
            return mapped_gdf
            
        except Exception as e:
            raise Exception(f"Error applying field mapping: {str(e)}")
    
    def transform_coordinate_system(self, gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
        """
        Transform GeoDataFrame to target coordinate system
        
        Args:
            gdf: Source GeoDataFrame
            target_crs: Target CRS (e.g., "EPSG:4326", "Web Mercator")
            
        Returns:
            Transformed GeoDataFrame
        """
        try:
            # Handle common CRS names
            if target_crs == "WGS84 (EPSG:4326)":
                target_crs = "EPSG:4326"
            elif target_crs == "Web Mercator (EPSG:3857)":
                target_crs = "EPSG:3857"
            
            # If no CRS is set, assume WGS84
            if gdf.crs is None:
                gdf = gdf.set_crs('EPSG:4326')
            
            # Transform if different from target
            if gdf.crs.to_string() != target_crs:
                transformed_gdf = gdf.to_crs(target_crs)
                return transformed_gdf
            else:
                return gdf.copy()
                
        except Exception as e:
            raise Exception(f"Error transforming coordinate system: {str(e)}")
    
    def validate_data_quality(self, gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
        """
        Perform comprehensive data quality validation
        
        Args:
            gdf: GeoDataFrame to validate
            
        Returns:
            Dict containing data quality results
        """
        quality_report = {
            'overall_score': 0,
            'issues': [],
            'recommendations': [],
            'statistics': {}
        }
        
        try:
            total_features = len(gdf)
            issues_count = 0
            
            # Check for duplicate records
            if gdf.duplicated().any():
                duplicate_count = gdf.duplicated().sum()
                quality_report['issues'].append(f"{duplicate_count} duplicate records found")
                quality_report['recommendations'].append("Consider removing duplicate records")
                issues_count += duplicate_count
            
            # Check for empty/null attributes
            for column in gdf.columns:
                if column != 'geometry':
                    null_count = gdf[column].isna().sum()
                    if null_count > 0:
                        null_percentage = (null_count / total_features) * 100
                        if null_percentage > 50:
                            quality_report['issues'].append(
                                f"Field '{column}' has {null_percentage:.1f}% null values"
                            )
                            issues_count += null_count
            
            # Geometry validation
            geom_validation = self.validate_geometry(gdf)
            if not geom_validation['valid']:
                quality_report['issues'].extend(geom_validation['errors'])
                issues_count += geom_validation['statistics'].get('invalid_geometries', 0)
            
            # CRS validation
            crs_validation = self.validate_coordinate_system(gdf)
            if not crs_validation['has_crs']:
                quality_report['issues'].append("No coordinate reference system defined")
                quality_report['recommendations'].extend(crs_validation['recommendations'])
                issues_count += 1
            
            # Calculate overall quality score
            if total_features > 0:
                quality_score = max(0, 100 - ((issues_count / total_features) * 100))
                quality_report['overall_score'] = round(quality_score, 1)
            
            # General recommendations
            if quality_report['overall_score'] >= 90:
                quality_report['recommendations'].append("Data quality is excellent")
            elif quality_report['overall_score'] >= 70:
                quality_report['recommendations'].append("Data quality is good with minor issues")
            else:
                quality_report['recommendations'].append("Data quality needs improvement before upload")
            
            # Statistics
            quality_report['statistics'] = {
                'total_features': total_features,
                'total_issues': issues_count,
                'fields_with_nulls': sum(1 for col in gdf.columns if col != 'geometry' and gdf[col].isna().any()),
                'geometry_issues': geom_validation['statistics'].get('invalid_geometries', 0)
            }
            
            return quality_report
            
        except Exception as e:
            quality_report['issues'].append(f"Data quality validation error: {str(e)}")
            return quality_report
    
    def suggest_field_mapping(self, source_fields: List[str], target_schema: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Suggest automatic field mapping based on field names
        
        Args:
            source_fields: List of source field names
            target_schema: Target schema
            
        Returns:
            Dict containing suggested field mappings
        """
        suggestions = {}
        
        try:
            target_fields = [field['name'] for field in target_schema]
            
            for source_field in source_fields:
                if source_field == 'geometry':
                    continue
                
                # Direct match
                if source_field in target_fields:
                    suggestions[source_field] = source_field
                    continue
                
                # Case-insensitive match
                source_lower = source_field.lower()
                for target_field in target_fields:
                    if source_lower == target_field.lower():
                        suggestions[source_field] = target_field
                        break
                
                # Partial match (common field name patterns)
                if source_field not in suggestions:
                    for target_field in target_fields:
                        # Remove common prefixes/suffixes and compare
                        source_clean = source_lower.replace('_', '').replace('-', '')
                        target_clean = target_field.lower().replace('_', '').replace('-', '')
                        
                        if source_clean in target_clean or target_clean in source_clean:
                            suggestions[source_field] = target_field
                            break
            
            return suggestions
            
        except Exception as e:
            return {}
