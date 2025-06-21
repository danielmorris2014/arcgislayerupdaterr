import logging
import os
from datetime import datetime
from typing import List, Optional
import streamlit as st

class Logger:
    """Handles logging operations for the application"""
    
    def __init__(self, log_file: str = "update_log.txt"):
        self.log_file = log_file
        self.setup_logging()
    
    def setup_logging(self):
        """Setup logging configuration"""
        try:
            # Create logs directory if it doesn't exist
            log_dir = os.path.dirname(self.log_file) if os.path.dirname(self.log_file) else '.'
            os.makedirs(log_dir, exist_ok=True)
            
            # Configure logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(self.log_file, encoding='utf-8'),
                    logging.StreamHandler()
                ]
            )
            
            self.logger = logging.getLogger('ArcGISLayerUpdater')
            
        except Exception as e:
            st.error(f"Error setting up logging: {str(e)}")
            # Fallback to basic logging
            self.logger = logging.getLogger('ArcGISLayerUpdater')
    
    def log(self, level: str, message: str, user: str = None):
        """
        Log a message with specified level
        
        Args:
            level: Log level (info, warning, error, debug)
            message: Message to log
            user: Optional username for context
        """
        try:
            # Add user context if provided
            if user:
                message = f"[User: {user}] {message}"
            
            # Log based on level
            if level.lower() == 'info':
                self.logger.info(message)
            elif level.lower() == 'warning':
                self.logger.warning(message)
            elif level.lower() == 'error':
                self.logger.error(message)
            elif level.lower() == 'debug':
                self.logger.debug(message)
            else:
                self.logger.info(f"[{level.upper()}] {message}")
                
        except Exception as e:
            print(f"Logging error: {str(e)}")
    
    def log_update_operation(self, operation_type: str, layer_id: str, layer_title: str, 
                           success: bool, details: str = None, user: str = None):
        """
        Log update operation with structured format
        
        Args:
            operation_type: Type of operation (update, backup, restore)
            layer_id: Layer ID
            layer_title: Layer title
            success: Whether operation was successful
            details: Additional details
            user: Username
        """
        try:
            status = "SUCCESS" if success else "FAILED"
            message = f"{operation_type.upper()} - {layer_title} ({layer_id}) - {status}"
            
            if details:
                message += f" - {details}"
            
            level = 'info' if success else 'error'
            self.log(level, message, user)
            
        except Exception as e:
            self.log('error', f"Error logging update operation: {str(e)}")
    
    def log_file_operation(self, filename: str, operation: str, success: bool, 
                          details: str = None, user: str = None):
        """
        Log file operation
        
        Args:
            filename: Name of file
            operation: Operation type (upload, validate, process)
            success: Whether operation was successful
            details: Additional details
            user: Username
        """
        try:
            status = "SUCCESS" if success else "FAILED"
            message = f"FILE {operation.upper()} - {filename} - {status}"
            
            if details:
                message += f" - {details}"
            
            level = 'info' if success else 'error'
            self.log(level, message, user)
            
        except Exception as e:
            self.log('error', f"Error logging file operation: {str(e)}")
    
    def log_authentication(self, username: str, success: bool, details: str = None):
        """
        Log authentication attempt
        
        Args:
            username: Username
            success: Whether authentication was successful
            details: Additional details
        """
        try:
            status = "SUCCESS" if success else "FAILED"
            message = f"AUTHENTICATION - {username} - {status}"
            
            if details:
                message += f" - {details}"
            
            level = 'info' if success else 'warning'
            self.log(level, message)
            
        except Exception as e:
            self.log('error', f"Error logging authentication: {str(e)}")
    
    def get_logs(self, level: str = None, lines: int = 100) -> List[str]:
        """
        Get recent log entries
        
        Args:
            level: Filter by log level (optional)
            lines: Number of lines to return
            
        Returns:
            List of log lines
        """
        try:
            if not os.path.exists(self.log_file):
                return ["No logs available"]
            
            with open(self.log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            
            # Get last N lines
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            # Filter by level if specified
            if level:
                filtered_lines = []
                for line in recent_lines:
                    if f" - {level.upper()} - " in line:
                        filtered_lines.append(line.strip())
                return filtered_lines
            
            return [line.strip() for line in recent_lines]
            
        except Exception as e:
            return [f"Error reading logs: {str(e)}"]
    
    def get_log_statistics(self) -> dict:
        """
        Get log statistics
        
        Returns:
            Dict containing log statistics
        """
        try:
            if not os.path.exists(self.log_file):
                return {
                    'total_entries': 0,
                    'info_count': 0,
                    'warning_count': 0,
                    'error_count': 0,
                    'file_size': 0
                }
            
            stats = {
                'total_entries': 0,
                'info_count': 0,
                'warning_count': 0,
                'error_count': 0,
                'file_size': os.path.getsize(self.log_file)
            }
            
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    stats['total_entries'] += 1
                    if ' - INFO - ' in line:
                        stats['info_count'] += 1
                    elif ' - WARNING - ' in line:
                        stats['warning_count'] += 1
                    elif ' - ERROR - ' in line:
                        stats['error_count'] += 1
            
            return stats
            
        except Exception as e:
            return {'error': f"Error getting log statistics: {str(e)}"}
    
    def clear_logs(self):
        """Clear all logs"""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'w', encoding='utf-8') as f:
                    f.write("")
                self.log('info', "Log file cleared")
                return True
            return False
            
        except Exception as e:
            print(f"Error clearing logs: {str(e)}")
            return False
    
    def export_logs(self, start_date: datetime = None, end_date: datetime = None) -> str:
        """
        Export logs for a specific date range
        
        Args:
            start_date: Start date for export
            end_date: End date for export
            
        Returns:
            String containing filtered logs
        """
        try:
            if not os.path.exists(self.log_file):
                return "No logs available"
            
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if not start_date and not end_date:
                return ''.join(lines)
            
            filtered_lines = []
            
            for line in lines:
                try:
                    # Extract timestamp from log line
                    timestamp_str = line.split(' - ')[0]
                    log_datetime = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                    
                    # Check if within date range
                    include_line = True
                    
                    if start_date and log_datetime < start_date:
                        include_line = False
                    
                    if end_date and log_datetime > end_date:
                        include_line = False
                    
                    if include_line:
                        filtered_lines.append(line)
                        
                except:
                    # If timestamp parsing fails, include the line
                    filtered_lines.append(line)
            
            return ''.join(filtered_lines)
            
        except Exception as e:
            return f"Error exporting logs: {str(e)}"
    
    def log_system_info(self):
        """Log system information"""
        try:
            import platform
            import sys
            
            system_info = {
                'platform': platform.platform(),
                'python_version': sys.version,
                'working_directory': os.getcwd(),
                'log_file': os.path.abspath(self.log_file)
            }
            
            self.log('info', f"System Info: {system_info}")
            
        except Exception as e:
            self.log('error', f"Error logging system info: {str(e)}")
