import json
import os
from typing import Dict, Any, Optional
import streamlit as st
from cryptography.fernet import Fernet
import base64

class SettingsManager:
    """Manages user settings and secure storage"""
    
    def __init__(self, settings_file: str = "user_settings.json"):
        self.settings_file = settings_file
        self.encrypted_fields = ['api_key', 'email_password']
        self._encryption_key = None
    
    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key"""
        if self._encryption_key is None:
            # Try to get key from environment or secrets
            key_string = os.getenv('ENCRYPTION_KEY') or st.secrets.get('ENCRYPTION_KEY', '')
            
            if key_string:
                self._encryption_key = key_string.encode()
            else:
                # Generate a new key (in production, this should be stored securely)
                self._encryption_key = Fernet.generate_key()
        
        return self._encryption_key
    
    def _encrypt_value(self, value: str) -> str:
        """Encrypt a sensitive value"""
        try:
            if not value:
                return value
            
            key = self._get_encryption_key()
            fernet = Fernet(key)
            encrypted_value = fernet.encrypt(value.encode())
            return base64.b64encode(encrypted_value).decode()
            
        except Exception:
            # If encryption fails, return original value (fallback)
            return value
    
    def _decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a sensitive value"""
        try:
            if not encrypted_value:
                return encrypted_value
            
            key = self._get_encryption_key()
            fernet = Fernet(key)
            decoded_value = base64.b64decode(encrypted_value.encode())
            decrypted_value = fernet.decrypt(decoded_value)
            return decrypted_value.decode()
            
        except Exception:
            # If decryption fails, return original value (might be unencrypted)
            return encrypted_value
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """
        Save user settings to file
        
        Args:
            settings: Dictionary of settings to save
            
        Returns:
            bool: True if successful
        """
        try:
            # Create a copy of settings for encryption
            settings_to_save = settings.copy()
            
            # Encrypt sensitive fields
            for field in self.encrypted_fields:
                if field in settings_to_save and settings_to_save[field]:
                    settings_to_save[field] = self._encrypt_value(settings_to_save[field])
            
            # Add metadata
            settings_to_save['_metadata'] = {
                'saved_at': str(pd.Timestamp.now()),
                'version': '1.0',
                'encrypted_fields': self.encrypted_fields
            }
            
            # Save to file
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings_to_save, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            st.error(f"Error saving settings: {str(e)}")
            return False
    
    def load_settings(self) -> Dict[str, Any]:
        """
        Load user settings from file
        
        Returns:
            Dict containing user settings
        """
        try:
            if not os.path.exists(self.settings_file):
                return self._get_default_settings()
            
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            # Decrypt sensitive fields
            encrypted_fields = settings.get('_metadata', {}).get('encrypted_fields', self.encrypted_fields)
            
            for field in encrypted_fields:
                if field in settings and settings[field]:
                    settings[field] = self._decrypt_value(settings[field])
            
            # Remove metadata from returned settings
            settings.pop('_metadata', None)
            
            # Merge with defaults for any missing keys
            default_settings = self._get_default_settings()
            for key, value in default_settings.items():
                if key not in settings:
                    settings[key] = value
            
            return settings
            
        except Exception as e:
            st.error(f"Error loading settings: {str(e)}")
            return self._get_default_settings()
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """Get default settings"""
        return {
            'api_key': '',
            'username': '',
            'portal_url': 'https://www.arcgis.com',
            'auto_save': True,
            'email_enabled': False,
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'email_from': '',
            'email_password': '',
            'email_to': '',
            'monitor_enabled': False,
            'monitor_path': '',
            'max_backups': 5,
            'backup_compression': True,
            'theme': 'light',
            'high_contrast': False,
            'auto_field_mapping': True,
            'default_crs': 'EPSG:4326',
            'batch_size': 1000,
            'retry_attempts': 3,
            'timeout_seconds': 300
        }
    
    def update_setting(self, key: str, value: Any) -> bool:
        """
        Update a single setting
        
        Args:
            key: Setting key
            value: New value
            
        Returns:
            bool: True if successful
        """
        try:
            current_settings = self.load_settings()
            current_settings[key] = value
            return self.save_settings(current_settings)
            
        except Exception as e:
            st.error(f"Error updating setting {key}: {str(e)}")
            return False
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a single setting value
        
        Args:
            key: Setting key
            default: Default value if key not found
            
        Returns:
            Setting value or default
        """
        try:
            settings = self.load_settings()
            return settings.get(key, default)
            
        except Exception:
            return default
    
    def reset_settings(self) -> bool:
        """
        Reset all settings to defaults
        
        Returns:
            bool: True if successful
        """
        try:
            default_settings = self._get_default_settings()
            return self.save_settings(default_settings)
            
        except Exception as e:
            st.error(f"Error resetting settings: {str(e)}")
            return False
    
    def export_settings(self, include_sensitive: bool = False) -> str:
        """
        Export settings as JSON string
        
        Args:
            include_sensitive: Whether to include sensitive data
            
        Returns:
            JSON string of settings
        """
        try:
            settings = self.load_settings()
            
            if not include_sensitive:
                # Remove sensitive fields
                settings_copy = settings.copy()
                for field in self.encrypted_fields:
                    if field in settings_copy:
                        settings_copy[field] = '[REDACTED]'
                settings = settings_copy
            
            return json.dumps(settings, indent=2, ensure_ascii=False)
            
        except Exception as e:
            return f"Error exporting settings: {str(e)}"
    
    def import_settings(self, settings_json: str) -> bool:
        """
        Import settings from JSON string
        
        Args:
            settings_json: JSON string containing settings
            
        Returns:
            bool: True if successful
        """
        try:
            imported_settings = json.loads(settings_json)
            
            # Validate settings
            if not isinstance(imported_settings, dict):
                raise ValueError("Settings must be a dictionary")
            
            # Merge with current settings
            current_settings = self.load_settings()
            current_settings.update(imported_settings)
            
            return self.save_settings(current_settings)
            
        except Exception as e:
            st.error(f"Error importing settings: {str(e)}")
            return False
    
    def backup_settings(self, backup_file: str = None) -> bool:
        """
        Create a backup of current settings
        
        Args:
            backup_file: Optional backup file path
            
        Returns:
            bool: True if successful
        """
        try:
            if backup_file is None:
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_file = f"settings_backup_{timestamp}.json"
            
            settings = self.load_settings()
            
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            st.error(f"Error backing up settings: {str(e)}")
            return False
    
    def restore_settings(self, backup_file: str) -> bool:
        """
        Restore settings from backup file
        
        Args:
            backup_file: Path to backup file
            
        Returns:
            bool: True if successful
        """
        try:
            if not os.path.exists(backup_file):
                raise FileNotFoundError(f"Backup file not found: {backup_file}")
            
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_settings = json.load(f)
            
            return self.save_settings(backup_settings)
            
        except Exception as e:
            st.error(f"Error restoring settings: {str(e)}")
            return False
    
    def validate_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate settings dictionary
        
        Args:
            settings: Settings to validate
            
        Returns:
            Dict containing validation results
        """
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Check required fields
            required_fields = ['username', 'portal_url']
            for field in required_fields:
                if field not in settings or not settings[field]:
                    validation_result['errors'].append(f"Required field '{field}' is missing or empty")
                    validation_result['valid'] = False
            
            # Validate email settings if enabled
            if settings.get('email_enabled', False):
                email_fields = ['smtp_server', 'smtp_port', 'email_from', 'email_to']
                for field in email_fields:
                    if field not in settings or not settings[field]:
                        validation_result['errors'].append(f"Email field '{field}' is required when email is enabled")
                        validation_result['valid'] = False
            
            # Validate numeric fields
            numeric_fields = {
                'smtp_port': (1, 65535),
                'max_backups': (1, 50),
                'batch_size': (1, 5000),
                'retry_attempts': (1, 10),
                'timeout_seconds': (30, 3600)
            }
            
            for field, (min_val, max_val) in numeric_fields.items():
                if field in settings:
                    try:
                        value = int(settings[field])
                        if not (min_val <= value <= max_val):
                            validation_result['warnings'].append(
                                f"Field '{field}' value {value} is outside recommended range {min_val}-{max_val}"
                            )
                    except (ValueError, TypeError):
                        validation_result['errors'].append(f"Field '{field}' must be a number")
                        validation_result['valid'] = False
            
            # Validate URLs
            url_fields = ['portal_url']
            for field in url_fields:
                if field in settings and settings[field]:
                    url = settings[field]
                    if not (url.startswith('http://') or url.startswith('https://')):
                        validation_result['warnings'].append(f"Field '{field}' should start with http:// or https://")
            
            return validation_result
            
        except Exception as e:
            validation_result['valid'] = False
            validation_result['errors'].append(f"Settings validation error: {str(e)}")
            return validation_result
