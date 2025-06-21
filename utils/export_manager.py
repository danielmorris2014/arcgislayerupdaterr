import pandas as pd
import csv
import json
import os
from io import StringIO, BytesIO
from datetime import datetime
from typing import Dict, List, Any, Optional
import streamlit as st

# PDF generation imports
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

class ExportManager:
    """Manages data export operations in various formats"""
    
    def __init__(self):
        self.supported_formats = ['csv', 'json', 'xlsx']
        if PDF_AVAILABLE:
            self.supported_formats.append('pdf')
    
    def create_update_summary(self, update_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create comprehensive update summary in multiple formats
        
        Args:
            update_results: List of update operation results
            
        Returns:
            Dict containing export data in multiple formats
        """
        try:
            # Prepare data
            summary_data = []
            
            for result in update_results:
                summary_data.append({
                    'Timestamp': result.get('timestamp', ''),
                    'Layer_Title': result.get('layer_title', ''),
                    'Layer_ID': result.get('layer_id', ''),
                    'Source_File': result.get('filename', ''),
                    'Status': 'SUCCESS' if result.get('success', False) else 'FAILED',
                    'Message': result.get('message', ''),
                    'Features_Added': result.get('features_added', ''),
                    'Errors': result.get('errors', '')
                })
            
            # Calculate summary statistics
            total_updates = len(update_results)
            successful_updates = sum(1 for result in update_results if result.get('success', False))
            failed_updates = total_updates - successful_updates
            success_rate = (successful_updates / total_updates * 100) if total_updates > 0 else 0
            
            stats = {
                'Total_Updates': total_updates,
                'Successful_Updates': successful_updates,
                'Failed_Updates': failed_updates,
                'Success_Rate_Percent': round(success_rate, 2),
                'Export_Date': datetime.now().isoformat()
            }
            
            # Create exports
            export_data = {}
            
            # CSV format
            export_data['csv'] = self._create_csv_export(summary_data, stats)
            
            # JSON format
            export_data['json'] = self._create_json_export(summary_data, stats)
            
            # Excel format
            try:
                export_data['xlsx'] = self._create_excel_export(summary_data, stats)
            except Exception as e:
                st.warning(f"Excel export not available: {str(e)}")
            
            # PDF format
            if PDF_AVAILABLE:
                try:
                    export_data['pdf'] = self._create_pdf_export(summary_data, stats)
                except Exception as e:
                    st.warning(f"PDF export not available: {str(e)}")
            
            return export_data
            
        except Exception as e:
            st.error(f"Error creating update summary: {str(e)}")
            return {}
    
    def _create_csv_export(self, data: List[Dict[str, Any]], stats: Dict[str, Any]) -> str:
        """Create CSV export"""
        try:
            output = StringIO()
            
            # Write summary statistics
            output.write("# ArcGIS Layer Update Summary\n")
            output.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            output.write("#\n")
            
            for key, value in stats.items():
                output.write(f"# {key}: {value}\n")
            
            output.write("#\n")
            output.write("# Detailed Results:\n")
            output.write("#\n")
            
            # Write data
            if data:
                df = pd.DataFrame(data)
                df.to_csv(output, index=False)
            else:
                output.write("No data available\n")
            
            return output.getvalue()
            
        except Exception as e:
            return f"Error creating CSV export: {str(e)}"
    
    def _create_json_export(self, data: List[Dict[str, Any]], stats: Dict[str, Any]) -> str:
        """Create JSON export"""
        try:
            export_data = {
                'metadata': {
                    'export_type': 'arcgis_layer_update_summary',
                    'generated_at': datetime.now().isoformat(),
                    'version': '1.0'
                },
                'summary_statistics': stats,
                'detailed_results': data
            }
            
            return json.dumps(export_data, indent=2, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({'error': f'Error creating JSON export: {str(e)}'})
    
    def _create_excel_export(self, data: List[Dict[str, Any]], stats: Dict[str, Any]) -> bytes:
        """Create Excel export"""
        try:
            output = BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Summary sheet
                stats_df = pd.DataFrame([stats])
                stats_df.to_excel(writer, sheet_name='Summary', index=False)
                
                # Detailed results sheet
                if data:
                    results_df = pd.DataFrame(data)
                    results_df.to_excel(writer, sheet_name='Detailed_Results', index=False)
                
                # Metadata sheet
                metadata = {
                    'Export_Type': 'ArcGIS Layer Update Summary',
                    'Generated_At': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'Version': '1.0',
                    'Total_Records': len(data)
                }
                metadata_df = pd.DataFrame([metadata])
                metadata_df.to_excel(writer, sheet_name='Metadata', index=False)
            
            return output.getvalue()
            
        except Exception as e:
            raise Exception(f"Error creating Excel export: {str(e)}")
    
    def _create_pdf_export(self, data: List[Dict[str, Any]], stats: Dict[str, Any]) -> bytes:
        """Create PDF export"""
        if not PDF_AVAILABLE:
            raise Exception("PDF export requires reportlab library")
        
        try:
            output = BytesIO()
            doc = SimpleDocTemplate(output, pagesize=A4)
            story = []
            
            # Get styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                textColor=colors.darkblue,
                alignment=1  # Center alignment
            )
            
            # Title
            title = Paragraph("ArcGIS Layer Update Summary", title_style)
            story.append(title)
            story.append(Spacer(1, 20))
            
            # Generation info
            gen_info = Paragraph(
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                styles['Normal']
            )
            story.append(gen_info)
            story.append(Spacer(1, 20))
            
            # Summary statistics
            story.append(Paragraph("Summary Statistics", styles['Heading2']))
            
            stats_data = [['Metric', 'Value']]
            for key, value in stats.items():
                # Format key for display
                display_key = key.replace('_', ' ').title()
                stats_data.append([display_key, str(value)])
            
            stats_table = Table(stats_data)
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(stats_table)
            story.append(Spacer(1, 30))
            
            # Detailed results
            if data:
                story.append(Paragraph("Detailed Results", styles['Heading2']))
                story.append(Spacer(1, 10))
                
                # Prepare table data
                table_data = [['Layer Title', 'Source File', 'Status', 'Message']]
                
                for result in data:
                    row = [
                        result.get('Layer_Title', 'N/A')[:30],  # Truncate long names
                        result.get('Source_File', 'N/A')[:20],
                        result.get('Status', 'N/A'),
                        result.get('Message', 'N/A')[:40]  # Truncate long messages
                    ]
                    table_data.append(row)
                
                # Create table
                results_table = Table(table_data, colWidths=[2*inch, 1.5*inch, 1*inch, 2.5*inch])
                results_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP')
                ]))
                
                # Color code status column
                for i, result in enumerate(data, 1):
                    if result.get('Status') == 'SUCCESS':
                        results_table.setStyle(TableStyle([
                            ('BACKGROUND', (2, i), (2, i), colors.lightgreen)
                        ]))
                    elif result.get('Status') == 'FAILED':
                        results_table.setStyle(TableStyle([
                            ('BACKGROUND', (2, i), (2, i), colors.lightcoral)
                        ]))
                
                story.append(results_table)
            
            # Build PDF
            doc.build(story)
            return output.getvalue()
            
        except Exception as e:
            raise Exception(f"Error creating PDF export: {str(e)}")
    
    def export_backup_list(self, backups: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Export backup list in multiple formats
        
        Args:
            backups: List of backup information
            
        Returns:
            Dict containing exports in different formats
        """
        try:
            exports = {}
            
            if not backups:
                exports['csv'] = "No backups available"
                exports['json'] = json.dumps({'message': 'No backups available'})
                return exports
            
            # CSV export
            df = pd.DataFrame(backups)
            exports['csv'] = df.to_csv(index=False)
            
            # JSON export
            export_data = {
                'metadata': {
                    'export_type': 'backup_list',
                    'generated_at': datetime.now().isoformat(),
                    'total_backups': len(backups)
                },
                'backups': backups
            }
            exports['json'] = json.dumps(export_data, indent=2, ensure_ascii=False)
            
            return exports
            
        except Exception as e:
            error_msg = f"Error exporting backup list: {str(e)}"
            return {
                'csv': error_msg,
                'json': json.dumps({'error': error_msg})
            }
    
    def export_logs(self, logs: List[str], log_level: str = None) -> Dict[str, str]:
        """
        Export logs in multiple formats
        
        Args:
            logs: List of log entries
            log_level: Optional filter level
            
        Returns:
            Dict containing exports in different formats
        """
        try:
            exports = {}
            
            # Prepare log data
            log_entries = []
            for log in logs:
                if log.strip():
                    # Try to parse log entry
                    parts = log.split(' - ', 3)
                    if len(parts) >= 3:
                        log_entries.append({
                            'timestamp': parts[0],
                            'level': parts[1],
                            'message': ' - '.join(parts[2:]) if len(parts) > 3 else parts[2]
                        })
                    else:
                        log_entries.append({
                            'timestamp': '',
                            'level': '',
                            'message': log
                        })
            
            # CSV export
            if log_entries:
                df = pd.DataFrame(log_entries)
                csv_output = StringIO()
                csv_output.write(f"# ArcGIS Layer Updater Logs\n")
                csv_output.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                if log_level:
                    csv_output.write(f"# Filtered by level: {log_level}\n")
                csv_output.write("#\n")
                df.to_csv(csv_output, index=False)
                exports['csv'] = csv_output.getvalue()
            else:
                exports['csv'] = "No log entries available"
            
            # JSON export
            export_data = {
                'metadata': {
                    'export_type': 'log_export',
                    'generated_at': datetime.now().isoformat(),
                    'total_entries': len(log_entries),
                    'filter_level': log_level
                },
                'log_entries': log_entries
            }
            exports['json'] = json.dumps(export_data, indent=2, ensure_ascii=False)
            
            # Raw text export
            exports['txt'] = '\n'.join(logs)
            
            return exports
            
        except Exception as e:
            error_msg = f"Error exporting logs: {str(e)}"
            return {
                'csv': error_msg,
                'json': json.dumps({'error': error_msg}),
                'txt': error_msg
            }
    
    def export_layer_statistics(self, layer_stats: Dict[str, Any]) -> Dict[str, str]:
        """
        Export layer statistics
        
        Args:
            layer_stats: Layer statistics data
            
        Returns:
            Dict containing exports in different formats
        """
        try:
            exports = {}
            
            # CSV export
            stats_df = pd.DataFrame([layer_stats])
            exports['csv'] = stats_df.to_csv(index=False)
            
            # JSON export
            export_data = {
                'metadata': {
                    'export_type': 'layer_statistics',
                    'generated_at': datetime.now().isoformat()
                },
                'statistics': layer_stats
            }
            exports['json'] = json.dumps(export_data, indent=2, ensure_ascii=False)
            
            return exports
            
        except Exception as e:
            error_msg = f"Error exporting layer statistics: {str(e)}"
            return {
                'csv': error_msg,
                'json': json.dumps({'error': error_msg})
            }
    
    def create_validation_report(self, validation_results: Dict[str, Any], 
                               filename: str) -> Dict[str, str]:
        """
        Create validation report in multiple formats
        
        Args:
            validation_results: Validation results data
            filename: Source filename
            
        Returns:
            Dict containing reports in different formats
        """
        try:
            reports = {}
            
            # Prepare report data
            report_data = {
                'filename': filename,
                'validation_timestamp': datetime.now().isoformat(),
                'overall_valid': validation_results.get('valid', False),
                'geometry_validation': validation_results.get('geometry_validation', {}),
                'schema_validation': validation_results.get('schema_validation', {}),
                'data_quality': validation_results.get('data_quality', {}),
                'recommendations': validation_results.get('recommendations', [])
            }
            
            # JSON report
            reports['json'] = json.dumps(report_data, indent=2, ensure_ascii=False)
            
            # CSV report (flattened)
            csv_data = []
            csv_data.append({
                'Category': 'General',
                'Metric': 'Filename',
                'Value': filename,
                'Status': 'INFO'
            })
            csv_data.append({
                'Category': 'General',
                'Metric': 'Overall Valid',
                'Value': str(validation_results.get('valid', False)),
                'Status': 'PASS' if validation_results.get('valid', False) else 'FAIL'
            })
            
            # Add geometry validation details
            geom_val = validation_results.get('geometry_validation', {})
            if geom_val:
                for key, value in geom_val.items():
                    csv_data.append({
                        'Category': 'Geometry',
                        'Metric': key.replace('_', ' ').title(),
                        'Value': str(value),
                        'Status': 'INFO'
                    })
            
            # Convert to CSV
            if csv_data:
                df = pd.DataFrame(csv_data)
                reports['csv'] = df.to_csv(index=False)
            
            return reports
            
        except Exception as e:
            error_msg = f"Error creating validation report: {str(e)}"
            return {
                'json': json.dumps({'error': error_msg}),
                'csv': error_msg
            }
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported export formats"""
        return self.supported_formats.copy()
    
    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format"""
        try:
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.1f} {unit}"
                size_bytes /= 1024.0
            return f"{size_bytes:.1f} TB"
        except:
            return "Unknown"
