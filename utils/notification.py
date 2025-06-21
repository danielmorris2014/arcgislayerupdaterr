import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from typing import Dict, List, Any, Optional
import streamlit as st
from datetime import datetime
import json

class NotificationManager:
    """Manages email notifications for update operations"""
    
    def __init__(self):
        self.smtp_server = None
        self.smtp_port = None
        self.email_from = None
        self.email_password = None
        self.email_to = None
        self.enabled = False
    
    def configure_from_settings(self, settings: Dict[str, Any]):
        """
        Configure notification settings
        
        Args:
            settings: Settings dictionary containing email configuration
        """
        try:
            self.enabled = settings.get('email_enabled', False)
            self.smtp_server = settings.get('smtp_server', 'smtp.gmail.com')
            self.smtp_port = settings.get('smtp_port', 587)
            self.email_from = settings.get('email_from', '')
            self.email_password = settings.get('email_password', '')
            self.email_to = settings.get('email_to', '')
            
            # Also check environment variables and secrets as fallback
            if not self.email_password:
                try:
                    self.email_password = os.getenv('EMAIL_PASSWORD') or st.secrets.get('EMAIL_PASSWORD', '')
                except:
                    self.email_password = os.getenv('EMAIL_PASSWORD', '')
            
            if not self.email_from:
                try:
                    self.email_from = os.getenv('EMAIL_FROM') or st.secrets.get('EMAIL_FROM', '')
                except:
                    self.email_from = os.getenv('EMAIL_FROM', '')
            
            if not self.email_to:
                try:
                    self.email_to = os.getenv('EMAIL_TO') or st.secrets.get('EMAIL_TO', '')
                except:
                    self.email_to = os.getenv('EMAIL_TO', '')
                
        except Exception as e:
            st.error(f"Error configuring notifications: {str(e)}")
            self.enabled = False
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test email server connection
        
        Returns:
            Dict containing test results
        """
        if not self.enabled:
            return {
                'success': False,
                'error': 'Email notifications are disabled'
            }
        
        if not all([self.smtp_server, self.smtp_port, self.email_from, self.email_password]):
            return {
                'success': False,
                'error': 'Missing required email configuration'
            }
        
        try:
            # Create SSL context
            context = ssl.create_default_context()
            
            # Connect to server
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.email_from, self.email_password)
                
                return {
                    'success': True,
                    'message': 'Email connection successful'
                }
                
        except smtplib.SMTPAuthenticationError:
            return {
                'success': False,
                'error': 'SMTP authentication failed. Check username and password.'
            }
        except smtplib.SMTPServerDisconnected:
            return {
                'success': False,
                'error': 'SMTP server disconnected. Check server and port settings.'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Email connection failed: {str(e)}'
            }
    
    def send_update_notification(self, update_results: List[Dict[str, Any]], 
                               user: str = None) -> bool:
        """
        Send notification about update operations
        
        Args:
            update_results: List of update operation results
            user: Username for context
            
        Returns:
            bool: True if notification sent successfully
        """
        if not self.enabled or not update_results:
            return False
        
        try:
            # Calculate summary statistics
            total_updates = len(update_results)
            successful_updates = sum(1 for result in update_results if result['success'])
            failed_updates = total_updates - successful_updates
            success_rate = (successful_updates / total_updates * 100) if total_updates > 0 else 0
            
            # Create email content
            subject = f"ArcGIS Layer Update Summary - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # HTML email body
            html_body = self._create_update_html_body(
                update_results, total_updates, successful_updates, 
                failed_updates, success_rate, user
            )
            
            # Plain text email body
            text_body = self._create_update_text_body(
                update_results, total_updates, successful_updates, 
                failed_updates, success_rate, user
            )
            
            return self._send_email(subject, html_body, text_body)
            
        except Exception as e:
            st.error(f"Error sending update notification: {str(e)}")
            return False
    
    def send_error_notification(self, error_message: str, operation: str = "Unknown", 
                              user: str = None) -> bool:
        """
        Send notification about critical errors
        
        Args:
            error_message: Error message
            operation: Operation that failed
            user: Username for context
            
        Returns:
            bool: True if notification sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            subject = f"ArcGIS Layer Updater Error - {operation}"
            
            html_body = f"""
            <html>
            <body>
                <h2 style="color: #d32f2f;">Error Alert</h2>
                <p><strong>Operation:</strong> {operation}</p>
                <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                {f'<p><strong>User:</strong> {user}</p>' if user else ''}
                
                <h3>Error Details:</h3>
                <div style="background-color: #ffebee; padding: 10px; border-left: 4px solid #d32f2f;">
                    <code>{error_message}</code>
                </div>
                
                <p style="margin-top: 20px; color: #666;">
                    This is an automated message from ArcGIS Layer Updater.
                </p>
            </body>
            </html>
            """
            
            text_body = f"""
            ERROR ALERT - ArcGIS Layer Updater
            
            Operation: {operation}
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            {f'User: {user}' if user else ''}
            
            Error Details:
            {error_message}
            
            This is an automated message from ArcGIS Layer Updater.
            """
            
            return self._send_email(subject, html_body, text_body)
            
        except Exception as e:
            st.error(f"Error sending error notification: {str(e)}")
            return False
    
    def send_backup_notification(self, backup_results: Dict[str, Any], 
                               operation: str = "backup") -> bool:
        """
        Send notification about backup operations
        
        Args:
            backup_results: Backup operation results
            operation: Type of backup operation (backup, restore, delete)
            
        Returns:
            bool: True if notification sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            subject = f"ArcGIS Backup {operation.title()} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            if backup_results.get('success', False):
                status_color = "#4caf50"
                status = "SUCCESS"
            else:
                status_color = "#d32f2f"
                status = "FAILED"
            
            html_body = f"""
            <html>
            <body>
                <h2 style="color: {status_color};">Backup {operation.title()} - {status}</h2>
                <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                
                <h3>Operation Details:</h3>
                <ul>
                    <li><strong>Operation:</strong> {operation.title()}</li>
                    <li><strong>Status:</strong> <span style="color: {status_color};">{status}</span></li>
            """
            
            # Add specific details based on operation type
            if operation == "backup":
                html_body += f"""
                    <li><strong>Backup ID:</strong> {backup_results.get('backup_id', 'N/A')}</li>
                    <li><strong>Records:</strong> {backup_results.get('record_count', 'N/A')}</li>
                    <li><strong>Size:</strong> {backup_results.get('size', 'N/A')}</li>
                """
            elif operation == "restore":
                html_body += f"""
                    <li><strong>Features Restored:</strong> {backup_results.get('features_restored', 'N/A')}</li>
                """
            
            if not backup_results.get('success', False):
                html_body += f"""
                    <li><strong>Error:</strong> <span style="color: #d32f2f;">{backup_results.get('error', 'Unknown error')}</span></li>
                """
            
            html_body += """
                </ul>
                
                <p style="margin-top: 20px; color: #666;">
                    This is an automated message from ArcGIS Layer Updater.
                </p>
            </body>
            </html>
            """
            
            # Plain text version
            text_body = f"""
            Backup {operation.title()} - {status}
            
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            Operation: {operation.title()}
            Status: {status}
            """
            
            if operation == "backup":
                text_body += f"""
            Backup ID: {backup_results.get('backup_id', 'N/A')}
            Records: {backup_results.get('record_count', 'N/A')}
            Size: {backup_results.get('size', 'N/A')}
                """
            elif operation == "restore":
                text_body += f"""
            Features Restored: {backup_results.get('features_restored', 'N/A')}
                """
            
            if not backup_results.get('success', False):
                text_body += f"""
            Error: {backup_results.get('error', 'Unknown error')}
                """
            
            text_body += """
            
            This is an automated message from ArcGIS Layer Updater.
            """
            
            return self._send_email(subject, html_body, text_body)
            
        except Exception as e:
            st.error(f"Error sending backup notification: {str(e)}")
            return False
    
    def _create_update_html_body(self, update_results: List[Dict[str, Any]], 
                               total_updates: int, successful_updates: int,
                               failed_updates: int, success_rate: float, 
                               user: str = None) -> str:
        """Create HTML email body for update notifications"""
        
        # Determine overall status color
        if success_rate == 100:
            status_color = "#4caf50"
            status_text = "ALL SUCCESSFUL"
        elif success_rate >= 80:
            status_color = "#ff9800"
            status_text = "MOSTLY SUCCESSFUL"
        else:
            status_color = "#d32f2f"
            status_text = "ISSUES DETECTED"
        
        html_body = f"""
        <html>
        <body>
            <h2 style="color: {status_color};">Layer Update Summary - {status_text}</h2>
            <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            {f'<p><strong>User:</strong> {user}</p>' if user else ''}
            
            <h3>Summary Statistics</h3>
            <table style="border-collapse: collapse; width: 100%; margin: 10px 0;">
                <tr style="background-color: #f5f5f5;">
                    <td style="border: 1px solid #ddd; padding: 8px;"><strong>Total Updates</strong></td>
                    <td style="border: 1px solid #ddd; padding: 8px;">{total_updates}</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px;"><strong>Successful</strong></td>
                    <td style="border: 1px solid #ddd; padding: 8px; color: #4caf50;">{successful_updates}</td>
                </tr>
                <tr style="background-color: #f5f5f5;">
                    <td style="border: 1px solid #ddd; padding: 8px;"><strong>Failed</strong></td>
                    <td style="border: 1px solid #ddd; padding: 8px; color: #d32f2f;">{failed_updates}</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px;"><strong>Success Rate</strong></td>
                    <td style="border: 1px solid #ddd; padding: 8px;">{success_rate:.1f}%</td>
                </tr>
            </table>
            
            <h3>Detailed Results</h3>
            <table style="border-collapse: collapse; width: 100%; margin: 10px 0;">
                <tr style="background-color: #f5f5f5;">
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Layer</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Source File</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Status</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Message</th>
                </tr>
        """
        
        for result in update_results:
            status_color = "#4caf50" if result['success'] else "#d32f2f"
            status_text = "SUCCESS" if result['success'] else "FAILED"
            
            html_body += f"""
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px;">{result.get('layer_title', 'N/A')}</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">{result.get('filename', 'N/A')}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; color: {status_color};">{status_text}</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">{result.get('message', 'N/A')}</td>
                </tr>
            """
        
        html_body += """
            </table>
            
            <p style="margin-top: 20px; color: #666;">
                This is an automated message from ArcGIS Layer Updater.
            </p>
        </body>
        </html>
        """
        
        return html_body
    
    def _create_update_text_body(self, update_results: List[Dict[str, Any]], 
                               total_updates: int, successful_updates: int,
                               failed_updates: int, success_rate: float, 
                               user: str = None) -> str:
        """Create plain text email body for update notifications"""
        
        text_body = f"""
ArcGIS Layer Update Summary

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{f'User: {user}' if user else ''}

SUMMARY STATISTICS
==================
Total Updates: {total_updates}
Successful: {successful_updates}
Failed: {failed_updates}
Success Rate: {success_rate:.1f}%

DETAILED RESULTS
================
        """
        
        for result in update_results:
            status_text = "SUCCESS" if result['success'] else "FAILED"
            text_body += f"""
Layer: {result.get('layer_title', 'N/A')}
Source File: {result.get('filename', 'N/A')}
Status: {status_text}
Message: {result.get('message', 'N/A')}
---
            """
        
        text_body += """

This is an automated message from ArcGIS Layer Updater.
        """
        
        return text_body
    
    def _send_email(self, subject: str, html_body: str, text_body: str, 
                   attachment_path: str = None) -> bool:
        """
        Send email with HTML and text content
        
        Args:
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body
            attachment_path: Optional file attachment
            
        Returns:
            bool: True if email sent successfully
        """
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.email_from
            message["To"] = self.email_to
            
            # Create text and HTML parts
            text_part = MIMEText(text_body, "plain")
            html_part = MIMEText(html_body, "html")
            
            # Add parts to message
            message.attach(text_part)
            message.attach(html_part)
            
            # Add attachment if provided
            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, "rb") as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {os.path.basename(attachment_path)}'
                )
                message.attach(part)
            
            # Create SSL context and send email
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.email_from, self.email_password)
                
                # Send email
                text = message.as_string()
                server.sendmail(self.email_from, self.email_to, text)
                
                return True
                
        except Exception as e:
            st.error(f"Error sending email: {str(e)}")
            return False
    
    def send_test_email(self) -> Dict[str, Any]:
        """
        Send a test email to verify configuration
        
        Returns:
            Dict containing test results
        """
        try:
            subject = "ArcGIS Layer Updater - Test Email"
            
            html_body = """
            <html>
            <body>
                <h2 style="color: #4caf50;">Test Email Successful!</h2>
                <p>This is a test email from ArcGIS Layer Updater.</p>
                <p><strong>Time:</strong> """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
                <p>If you received this email, your notification settings are configured correctly.</p>
                
                <p style="margin-top: 20px; color: #666;">
                    This is an automated test message from ArcGIS Layer Updater.
                </p>
            </body>
            </html>
            """
            
            text_body = f"""
            ArcGIS Layer Updater - Test Email
            
            This is a test email from ArcGIS Layer Updater.
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            If you received this email, your notification settings are configured correctly.
            
            This is an automated test message from ArcGIS Layer Updater.
            """
            
            success = self._send_email(subject, html_body, text_body)
            
            if success:
                return {
                    'success': True,
                    'message': 'Test email sent successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to send test email'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Test email failed: {str(e)}'
            }
