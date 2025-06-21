import streamlit as st
import os
import tempfile
import zipfile
import geopandas as gpd
from arcgis.gis import GIS
from arcgis.features import FeatureLayerCollection, FeatureLayer
from arcgis import geometry as arcgis_geometry
import pandas as pd
import json
from typing import Dict, List, Any
from datetime import datetime
import time
import io
import base64
import requests
from bs4 import BeautifulSoup
import re

# Page configuration
st.set_page_config(
    page_title="ArcGISLayerUpdater",
    page_icon="🗺️",
    layout="wide"
)

# Initialize session state
if 'gis' not in st.session_state:
    st.session_state.gis = None
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_settings' not in st.session_state:
    st.session_state.user_settings = {
        'default_sharing_level': 'Private',
        'irth_id': '',
        'batch_size': 1000,
        'auto_reproject': True
    }

def authenticate():
    """Handle ArcGIS Online authentication"""
    st.header("🔐 ArcGIS Online Authentication")
    
    with st.form("auth_form"):
        username = st.text_input("Username", help="Your ArcGIS Online username")
        password = st.text_input("Password", type="password", help="Your ArcGIS Online password")
        portal_url = st.text_input("Portal URL", value="https://www.arcgis.com", help="ArcGIS Online portal URL")
        
        submit = st.form_submit_button("Login", type="primary")
        
        if submit:
            if username and password:
                try:
                    with st.spinner("Authenticating..."):
                        gis = GIS(portal_url, username, password)
                        # Test authentication by accessing user properties
                        user = gis.users.me
                        if user:
                            st.session_state.gis = gis
                            st.session_state.authenticated = True
                            st.success(f"Successfully authenticated as {user.fullName}")
                            st.rerun()
                        else:
                            st.error("Authentication failed - invalid credentials")
                except Exception as e:
                    st.error(f"Authentication failed: {str(e)}")
            else:
                st.warning("Please enter both username and password")

def get_feature_layers():
    """Get user's existing feature layers"""
    try:
        items = st.session_state.gis.content.search(
            query=f"owner:{st.session_state.gis.users.me.username}",
            item_type="Feature Service",
            max_items=100
        )
        return items
    except Exception as e:
        st.error(f"Error fetching feature layers: {str(e)}")
        return []

def get_web_maps():
    """Get user's existing web maps"""
    try:
        items = st.session_state.gis.content.search(
            query=f"owner:{st.session_state.gis.users.me.username}",
            item_type="Web Map",
            max_items=100
        )
        return items
    except Exception as e:
        st.error(f"Error fetching web maps: {str(e)}")
        return []

def validate_zip_file(zip_file):
    """Validate that zip file contains shapefile components"""
    try:
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            
            # Check for required shapefile components
            has_shp = any(f.endswith('.shp') for f in file_list)
            has_shx = any(f.endswith('.shx') for f in file_list)
            has_dbf = any(f.endswith('.dbf') for f in file_list)
            
            if has_shp and has_shx and has_dbf:
                return True, "Valid shapefile archive"
            else:
                missing = []
                if not has_shp: missing.append('.shp')
                if not has_shx: missing.append('.shx')
                if not has_dbf: missing.append('.dbf')
                return False, f"Missing required files: {', '.join(missing)}"
                
    except zipfile.BadZipFile:
        return False, "Invalid zip file format"
    except Exception as e:
        return False, f"Error validating zip file: {str(e)}"

def load_user_settings():
    """Load user settings from file or session state"""
    settings_file = "user_settings.json"
    try:
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                loaded_settings = json.load(f)
                st.session_state.user_settings.update(loaded_settings)
    except Exception:
        pass  # Use default settings
    return st.session_state.user_settings

def save_user_settings():
    """Save user settings to file"""
    settings_file = "user_settings.json"
    try:
        with open(settings_file, 'w') as f:
            json.dump(st.session_state.user_settings, f)
        return True
    except Exception as e:
        st.error(f"Error saving settings: {str(e)}")
        return False

def validate_coordinate_system(gdf, target_layer=None):
    """Enhanced coordinate system validation with detailed reprojection options"""
    if gdf.crs is None:
        st.warning("No coordinate system detected in uploaded data")
        return gdf, False
    
    source_crs = gdf.crs
    st.info(f"Source CRS: {source_crs}")
    
    # Extended CRS options for sublayer updates
    crs_options = {
        "Keep Current": str(source_crs),
        "WGS84 (EPSG:4326)": "EPSG:4326",
        "Web Mercator (EPSG:3857)": "EPSG:3857",
        "NAD83 (EPSG:4269)": "EPSG:4269",
        "NAD83 UTM Zone 10N (EPSG:26910)": "EPSG:26910",
        "NAD83 UTM Zone 11N (EPSG:26911)": "EPSG:26911",
        "NAD83 UTM Zone 12N (EPSG:26912)": "EPSG:26912",
        "State Plane California (EPSG:2154)": "EPSG:2154",
        "State Plane Texas (EPSG:3081)": "EPSG:3081",
        "British National Grid (EPSG:27700)": "EPSG:27700"
    }
    
    target_crs = None
    if target_layer:
        try:
            sr = target_layer.properties.spatialReference
            if sr and hasattr(sr, 'wkid'):
                target_crs = f"EPSG:{sr.wkid}"
                crs_options[f"Target Layer CRS ({target_crs})"] = target_crs
                st.info(f"Target layer CRS: {target_crs}")
                
                # Check for mismatch
                if str(source_crs) != target_crs:
                    st.warning(f"CRS mismatch detected: {source_crs} vs {target_crs}")
        except Exception as e:
            st.warning(f"Could not retrieve target layer CRS: {str(e)}")
    
    # CRS selection interface
    st.subheader("Coordinate System Options")
    selected_crs = st.selectbox(
        "Target Spatial Reference",
        options=list(crs_options.keys()),
        help="Select the coordinate system for the data",
        index=list(crs_options.keys()).index(f"Target Layer CRS ({target_crs})") if target_crs and f"Target Layer CRS ({target_crs})" in crs_options else 0
    )
    
    # Custom EPSG option
    if st.checkbox("Use Custom EPSG Code"):
        custom_epsg = st.text_input(
            "EPSG Code",
            placeholder="e.g., 4326, 3857, 26910",
            help="Enter numeric EPSG code"
        )
        if custom_epsg:
            try:
                target_crs_code = f"EPSG:{int(custom_epsg)}"
                selected_crs = f"Custom ({target_crs_code})"
                crs_options[selected_crs] = target_crs_code
            except ValueError:
                st.error("Enter a valid numeric EPSG code")
                return gdf, False
    
    # Apply reprojection if needed
    if selected_crs != "Keep Current":
        target_crs_code = crs_options[selected_crs]
        
        if str(source_crs) != target_crs_code:
            if st.button("Apply Reprojection", type="primary"):
                with st.spinner(f"Reprojecting to {target_crs_code}..."):
                    try:
                        original_bounds = gdf.total_bounds
                        gdf_reprojected = gdf.to_crs(target_crs_code)
                        new_bounds = gdf_reprojected.total_bounds
                        
                        st.success(f"Reprojected from {source_crs} to {target_crs_code}")
                        
                        # Show bounds comparison
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**Original Bounds:**")
                            st.write(f"X: {original_bounds[0]:.2f} to {original_bounds[2]:.2f}")
                            st.write(f"Y: {original_bounds[1]:.2f} to {original_bounds[3]:.2f}")
                        with col2:
                            st.write("**Reprojected Bounds:**")
                            st.write(f"X: {new_bounds[0]:.2f} to {new_bounds[2]:.2f}")
                            st.write(f"Y: {new_bounds[1]:.2f} to {new_bounds[3]:.2f}")
                        
                        return gdf_reprojected, True
                    except Exception as e:
                        st.error(f"Reprojection failed: {str(e)}")
                        return gdf, False
            else:
                st.info("Click 'Apply Reprojection' to proceed with coordinate transformation")
                return gdf, False
    
    return gdf, True

def authenticate_irth(username, password, debug_mode=False):
    """Enhanced irth utilitsphere authentication with robust session handling"""
    session = requests.Session()
    
    # Set browser headers to simulate real browser behavior
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })
    
    try:
        # First, try to access the main irth page to establish session
        main_url = "https://www.irth.com"
        if debug_mode:
            st.write(f"🔍 Accessing main page: {main_url}")
        
        main_response = session.get(main_url, timeout=15)
        if debug_mode:
            st.write(f"Main page status: {main_response.status_code}")
        
        # Look for login form or redirect to login page
        soup = BeautifulSoup(main_response.content, 'html.parser')
        
        # Try to find login form or login page URL
        login_form = soup.find('form', {'id': 'loginForm'}) or soup.find('form', {'name': 'loginForm'})
        login_links = soup.find_all('a', href=True)
        
        login_url = None
        for link in login_links:
            href = link.get('href', '').lower()
            if 'login' in href or 'signin' in href or 'auth' in href:
                if href.startswith('http'):
                    login_url = href
                else:
                    login_url = f"https://www.irth.com{href}" if href.startswith('/') else f"https://www.irth.com/{href}"
                break
        
        # If no specific login URL found, try common endpoints
        if not login_url:
            potential_login_urls = [
                "https://www.irth.com/login",
                "https://www.irth.com/signin",
                "https://www.irth.com/auth/login",
                "https://www.irth.com/Utilisphere/login",
                "https://www.irth.com/Utilisphere/Administration/ManageMapLayers/ManageMapLayers.aspx"
            ]
            
            for test_url in potential_login_urls:
                try:
                    test_response = session.get(test_url, timeout=10)
                    if test_response.status_code == 200:
                        test_soup = BeautifulSoup(test_response.content, 'html.parser')
                        # Look for password input field as indicator of login page
                        if test_soup.find('input', {'type': 'password'}) or test_soup.find('input', {'name': re.compile(r'pass', re.I)}):
                            login_url = test_url
                            if debug_mode:
                                st.write(f"🔍 Found login page: {login_url}")
                            break
                except:
                    continue
        
        if not login_url:
            return None, "Could not locate irth login page"
        
        # Get the login page
        if debug_mode:
            st.write(f"🔍 Accessing login page: {login_url}")
        
        login_response = session.get(login_url, timeout=15)
        if login_response.status_code != 200:
            return None, f"Cannot access login page (Status: {login_response.status_code})"
        
        # Parse login form
        login_soup = BeautifulSoup(login_response.content, 'html.parser')
        
        if debug_mode:
            st.write(f"Login page title: {login_soup.title.string if login_soup.title else 'No title'}")
            st.write(f"Login page size: {len(login_response.content)} bytes")
        
        # Find login form
        login_form = (login_soup.find('form') or 
                     login_soup.find('form', {'method': 'post'}) or
                     login_soup.find('form', {'id': re.compile(r'login', re.I)}) or
                     login_soup.find('form', {'name': re.compile(r'login', re.I)}))
        
        if not login_form:
            if debug_mode:
                st.code(f"No login form found. Page content sample:\n{login_soup.get_text()[:500]}")
            return None, "No login form found on the page"
        
        # Extract form action URL
        form_action = login_form.get('action', '')
        if form_action:
            if form_action.startswith('http'):
                post_url = form_action
            elif form_action.startswith('/'):
                post_url = f"https://www.irth.com{form_action}"
            else:
                post_url = f"{login_url.rsplit('/', 1)[0]}/{form_action}"
        else:
            post_url = login_url
        
        if debug_mode:
            st.write(f"🔍 Form action URL: {post_url}")
        
        # Prepare login data
        login_data = {}
        
        # Add all hidden fields
        for hidden_input in login_form.find_all('input', {'type': 'hidden'}):
            name = hidden_input.get('name')
            value = hidden_input.get('value', '')
            if name:
                login_data[name] = value
        
        # Find username and password field names with enhanced detection
        username_field = None
        password_field = None
        submit_field = None
        
        form_inputs = login_form.find_all('input')
        
        if debug_mode:
            st.write(f"🔍 Form has {len(form_inputs)} input fields:")
            for i, inp in enumerate(form_inputs):
                st.write(f"  Field {i+1}: name='{inp.get('name', '')}', type='{inp.get('type', '')}', id='{inp.get('id', '')}'")
        
        for input_field in form_inputs:
            input_type = input_field.get('type', '').lower()
            input_name = input_field.get('name', '') or ''
            input_id = input_field.get('id', '') or ''
            
            # Password field detection
            if input_type == 'password':
                password_field = input_field.get('name')
                if debug_mode:
                    st.write(f"🔍 Found password field: {password_field}")
            
            # Username field detection (more comprehensive)
            elif input_type in ['text', 'email'] and not username_field:
                name_lower = input_name.lower()
                id_lower = input_id.lower()
                
                username_keywords = ['user', 'login', 'email', 'account', 'name']
                if any(keyword in name_lower or keyword in id_lower for keyword in username_keywords):
                    username_field = input_field.get('name')
                    if debug_mode:
                        st.write(f"🔍 Found username field: {username_field}")
            
            # Submit button detection
            elif input_type in ['submit', 'button']:
                submit_field = input_field.get('name')
        
        # If no specific fields found, try common patterns
        if not username_field:
            common_username_names = ['username', 'user', 'email', 'login', 'loginname', 'userid']
            for common_name in common_username_names:
                if any(inp.get('name', '').lower() == common_name for inp in form_inputs):
                    username_field = common_name
                    break
            
            # Fallback: use first text input
            if not username_field:
                for inp in form_inputs:
                    if inp.get('type', '').lower() in ['text', 'email', '']:
                        username_field = inp.get('name') or 'username'
                        break
        
        if not password_field:
            common_password_names = ['password', 'pass', 'passwd', 'pwd']
            for common_name in common_password_names:
                if any(inp.get('name', '').lower() == common_name for inp in form_inputs):
                    password_field = common_name
                    break
            
            # Fallback
            if not password_field:
                password_field = 'password'
        
        # Add credentials to form data
        if username_field:
            login_data[username_field] = username
        if password_field:
            login_data[password_field] = password
        if submit_field:
            login_data[submit_field] = 'Login'
        
        if debug_mode:
            st.write(f"🔍 Final username field: {username_field}")
            st.write(f"🔍 Final password field: {password_field}")
            st.write(f"🔍 Submit field: {submit_field}")
            st.write(f"🔍 Complete form data: {login_data}")
            
            # Show form HTML for debugging
            st.write("**Form HTML:**")
            st.code(str(login_form)[:1000] + "..." if len(str(login_form)) > 1000 else str(login_form))
        
        # Submit login form
        login_submit_response = session.post(post_url, data=login_data, timeout=15, allow_redirects=True)
        
        if debug_mode:
            st.write(f"🔍 Login response status: {login_submit_response.status_code}")
            st.write(f"🔍 Login response URL: {login_submit_response.url}")
            st.write(f"🔍 Response headers: {dict(login_submit_response.headers)}")
            
            # Show response content sample
            response_text = login_submit_response.text
            st.write(f"🔍 Response size: {len(response_text)} characters")
            st.write("**Response content sample:**")
            st.code(response_text[:2000] + "..." if len(response_text) > 2000 else response_text)
        
        # Enhanced success detection
        response_text_lower = login_submit_response.text.lower()
        response_url_lower = login_submit_response.url.lower()
        
        # Strong success indicators
        strong_success_indicators = [
            'managemaplayers' in response_url_lower,
            'administration' in response_url_lower and 'utilisphere' in response_url_lower,
            'dashboard' in response_url_lower,
            'admin' in response_url_lower and 'irth' in response_url_lower
        ]
        
        # Moderate success indicators
        moderate_success_indicators = [
            'welcome' in response_text_lower,
            'logout' in response_text_lower,
            'sign out' in response_text_lower,
            'administration' in response_text_lower,
            'manage' in response_text_lower and 'layer' in response_text_lower
        ]
        
        # Clear error indicators
        error_indicators = [
            'login failed' in response_text_lower,
            'invalid username' in response_text_lower,
            'invalid password' in response_text_lower,
            'authentication failed' in response_text_lower,
            'incorrect' in response_text_lower and ('password' in response_text_lower or 'username' in response_text_lower),
            'access denied' in response_text_lower,
            'unauthorized' in response_text_lower
        ]
        
        # Check for redirect back to login page
        login_page_indicators = [
            'login' in response_url_lower,
            'signin' in response_url_lower,
            'auth' in response_url_lower and 'login' in response_text_lower
        ]
        
        if debug_mode:
            st.write(f"🔍 Strong success indicators: {[ind for ind in strong_success_indicators if True]}")
            st.write(f"🔍 Moderate success indicators: {[ind for ind in moderate_success_indicators if True]}")
            st.write(f"🔍 Error indicators found: {any(error_indicators)}")
            st.write(f"🔍 Login page indicators: {any(login_page_indicators)}")
        
        # Determine authentication result
        if any(strong_success_indicators):
            if debug_mode:
                st.write("✅ Authentication successful based on URL indicators")
            return session, None
        elif any(error_indicators):
            return None, "Authentication failed - invalid credentials or access denied"
        elif any(login_page_indicators):
            return None, "Authentication failed - redirected back to login page"
        elif any(moderate_success_indicators) and not any(error_indicators):
            if debug_mode:
                st.write("✅ Authentication likely successful based on page content")
            return session, None
        else:
            # Final verification: try to access the target page
            if debug_mode:
                st.write("🔍 Ambiguous result - testing access to management page")
            
            target_url = "https://www.irth.com/Utilisphere/Administration/ManageMapLayers/ManageMapLayers.aspx"
            try:
                test_response = session.get(target_url, timeout=10)
                
                if debug_mode:
                    st.write(f"🔍 Test access - Status: {test_response.status_code}")
                    st.write(f"🔍 Test access - URL: {test_response.url}")
                
                # Check if we can access the management page
                if (test_response.status_code == 200 and 
                    'login' not in test_response.url.lower() and
                    'signin' not in test_response.url.lower()):
                    
                    # Look for management-specific content
                    test_content = test_response.text.lower()
                    if any(keyword in test_content for keyword in ['manage', 'layer', 'administration', 'map']):
                        if debug_mode:
                            st.write("✅ Authentication successful - can access management page")
                        return session, None
                
                return None, "Authentication verification failed - cannot confirm access to management features"
                
            except Exception as e:
                return None, f"Authentication verification error: {str(e)}"
            
    except requests.RequestException as e:
        return None, f"Connection error: {str(e)}"
    except Exception as e:
        return None, f"Authentication error: {str(e)}"

def get_irth_map_layers(session, debug_mode=False):
    """Enhanced retrieval of map layer URLs from irth utilitsphere with multiple parsing strategies"""
    try:
        url = "https://www.irth.com/Utilisphere/Administration/ManageMapLayers/ManageMapLayers.aspx"
        
        if debug_mode:
            st.write(f"🔍 Fetching map layers from: {url}")
        
        response = session.get(url, timeout=15)
        
        if response.status_code == 403:
            return [], "Access forbidden - please check your irth credentials have administrative access"
        elif response.status_code == 404:
            return [], "Map layers page not found - URL may have changed"
        elif response.status_code != 200:
            return [], f"Unable to access map layers page (Status: {response.status_code})"
        
        # Check if redirected to login page
        if 'login' in response.url.lower() or 'signin' in response.url.lower():
            return [], "Session expired - please re-authenticate with irth"
        
        soup = BeautifulSoup(response.content, 'html.parser')
        layers = []
        
        if debug_mode:
            st.write("**Debug Information:**")
            st.write(f"Page title: {soup.title.string if soup.title else 'No title found'}")
            st.write(f"Page size: {len(response.content)} bytes")
            st.write(f"Final URL: {response.url}")
        
        # Strategy 1: Look for tables with layer data
        tables = soup.find_all('table')
        if debug_mode:
            st.write(f"Found {len(tables)} tables")
        
        for i, table in enumerate(tables):
            # Look for table headers that suggest layer data
            headers = table.find_all(['th', 'thead'])
            header_text = ' '.join([h.get_text().lower() for h in headers])
            
            if any(keyword in header_text for keyword in ['layer', 'url', 'service', 'map']):
                rows = table.find_all('tr')[1:]  # Skip header row
                
                for j, row in enumerate(rows):
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        cell_texts = [cell.get_text(strip=True) for cell in cells]
                        
                        # Look for URLs in cells
                        for k, cell_text in enumerate(cell_texts):
                            if any(pattern in cell_text.lower() for pattern in 
                                  ['http', 'featureserver', 'mapserver', 'arcgis', 'rest/services']):
                                layer_name = cell_texts[0] if k > 0 else f"Layer_{len(layers)+1}"
                                
                                # Also check for links within cells
                                cell = cells[k]
                                links = cell.find_all('a', href=True)
                                for link in links:
                                    href = link.get('href')
                                    if href and any(pattern in href.lower() for pattern in 
                                                  ['featureserver', 'mapserver', 'rest/services']):
                                        layers.append({
                                            'name': layer_name,
                                            'url': href,
                                            'id': len(layers) + 1,
                                            'source': f'Table {i+1}, Row {j+1} (link)'
                                        })
                                
                                # Add text-based URL if found
                                if cell_text != layer_name:
                                    layers.append({
                                        'name': layer_name,
                                        'url': cell_text,
                                        'id': len(layers) + 1,
                                        'source': f'Table {i+1}, Row {j+1} (text)'
                                    })
        
        # Strategy 2: Look for ASP.NET controls and form elements
        inputs = soup.find_all('input')
        textareas = soup.find_all('textarea')
        selects = soup.find_all('select')
        
        all_form_elements = inputs + textareas + selects
        
        if debug_mode:
            st.write(f"Found {len(all_form_elements)} form elements")
        
        for element in all_form_elements:
            value = element.get('value', '') or element.get_text(strip=True)
            name = element.get('name', '') or element.get('id', '')
            
            if value and any(pattern in value.lower() for pattern in 
                           ['http', 'featureserver', 'mapserver', 'rest/services', 'arcgis']):
                layers.append({
                    'name': name or f'Form_Element_{len(layers)+1}',
                    'url': value,
                    'id': len(layers) + 1,
                    'source': f'Form element: {element.name} ({name})'
                })
        
        # Strategy 3: Look for hyperlinks
        links = soup.find_all('a', href=True)
        if debug_mode:
            st.write(f"Found {len(links)} links")
        
        for link in links:
            href = link.get('href')
            link_text = link.get_text(strip=True)
            
            if href and any(pattern in href.lower() for pattern in 
                          ['featureserver', 'mapserver', 'rest/services']):
                layers.append({
                    'name': link_text or f'Link_{len(layers)+1}',
                    'url': href,
                    'id': len(layers) + 1,
                    'source': 'Hyperlink'
                })
        
        # Strategy 4: Look for JavaScript variables or configuration
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.get_text()
            if script_text:
                # Look for common patterns in JavaScript
                js_patterns = [
                    r'["\']https?://[^"\']*(?:featureserver|mapserver|rest/services)[^"\']*["\']',
                    r'serviceUrl\s*[:=]\s*["\'][^"\']+["\']',
                    r'layerUrl\s*[:=]\s*["\'][^"\']+["\']'
                ]
                
                for pattern in js_patterns:
                    matches = re.findall(pattern, script_text, re.IGNORECASE)
                    for match in matches:
                        clean_url = match.strip('"\'')
                        if not any(layer['url'] == clean_url for layer in layers):
                            layers.append({
                                'name': f'JS_Config_{len(layers)+1}',
                                'url': clean_url,
                                'id': len(layers) + 1,
                                'source': 'JavaScript configuration'
                            })
        
        # Strategy 5: Regular expression scan of entire page
        url_pattern = re.compile(
            r'https?://[^\s<>"\']+(?:featureserver|mapserver|rest/services)[^\s<>"\']*',
            re.IGNORECASE
        )
        
        page_text = soup.get_text()
        all_urls = url_pattern.findall(page_text)
        
        for url_match in all_urls:
            if not any(layer['url'] == url_match for layer in layers):
                layers.append({
                    'name': f'Pattern_Match_{len(layers)+1}',
                    'url': url_match,
                    'id': len(layers) + 1,
                    'source': 'Pattern matching'
                })
        
        # Remove duplicates based on URL
        unique_layers = []
        seen_urls = set()
        for layer in layers:
            if layer['url'] not in seen_urls:
                seen_urls.add(layer['url'])
                unique_layers.append(layer)
        
        layers = unique_layers
        
        if debug_mode:
            st.write(f"**Total unique layers found: {len(layers)}**")
            
            if not layers:
                st.write("**Debugging - No layers found. Page analysis:**")
                
                # Show page structure
                st.write("Page structure:")
                structure_info = []
                for tag in ['table', 'form', 'input', 'a', 'script']:
                    count = len(soup.find_all(tag))
                    structure_info.append(f"{tag}: {count}")
                st.write(", ".join(structure_info))
                
                # Show page content sample
                page_sample = soup.get_text()[:1000]
                if page_sample:
                    st.text_area("Page content sample", page_sample, height=200)
                
                # Show form details
                forms = soup.find_all('form')
                if forms:
                    st.write(f"**Form details ({len(forms)} forms):**")
                    for i, form in enumerate(forms):
                        st.write(f"Form {i+1}:")
                        st.write(f"  - Action: {form.get('action', 'None')}")
                        st.write(f"  - Method: {form.get('method', 'None')}")
                        st.write(f"  - Inputs: {len(form.find_all('input'))}")
        
        return layers, None
        
    except requests.RequestException as e:
        return [], f"Connection error: {str(e)}"
    except Exception as e:
        return [], f"Error retrieving layers: {str(e)}"

def update_irth_layer_url(session, layer_id, new_url, layer_name=None):
    """Update a specific layer URL in irth utilitsphere"""
    try:
        url = "https://www.irth.com/Utilisphere/Administration/ManageMapLayers/ManageMapLayers.aspx"
        
        # Get the current page to retrieve form data
        page_response = session.get(url, timeout=10)
        soup = BeautifulSoup(page_response.content, 'html.parser')
        
        # Prepare update data
        update_data = {}
        
        # Preserve hidden form fields
        for input_field in soup.find_all('input', type='hidden'):
            name = input_field.get('name')
            value = input_field.get('value', '')
            if name:
                update_data[name] = value
        
        # Add the new URL data (field names may need adjustment)
        if layer_name:
            update_data[f'layer_{layer_id}_name'] = layer_name
        update_data[f'layer_{layer_id}_url'] = new_url
        update_data['action'] = 'update'
        update_data['layer_id'] = str(layer_id)
        
        # Submit the update
        response = session.post(url, data=update_data, timeout=10)
        
        if response.status_code == 200:
            # Check for success indicators in the response
            if "success" in response.text.lower() or "updated" in response.text.lower():
                return True, "Layer URL updated successfully"
            else:
                return False, "Update submitted but success not confirmed"
        else:
            return False, f"Update failed with status code: {response.status_code}"
            
    except requests.RequestException as e:
        return False, f"Connection error: {str(e)}"
    except Exception as e:
        return False, f"Update error: {str(e)}"

def irth_integration():
    """irth utilitsphere integration interface"""
    st.header("🔗 irth Integration")
    
    st.write("""
    This section allows you to view and update map layer URLs in irth utilitsphere directly from the ArcGISLayerUpdater app.
    
    **Requirements:**
    - Your irth credentials must have administrative access to Manage Map Layers
    - For manual verification, visit: [irth Manage Map Layers](https://www.irth.com/Utilisphere/Administration/ManageMapLayers/ManageMapLayers.aspx)
    """)
    
    # irth Authentication Section
    st.subheader("🔐 irth Authentication")
    
    # Debug mode toggle
    debug_mode = st.checkbox("Enable Debug Mode", help="Show detailed authentication and parsing information")
    
    with st.form("irth_auth_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            irth_username = st.text_input(
                "irth Username",
                help="Enter your irth utilitsphere username"
            )
        
        with col2:
            irth_password = st.text_input(
                "irth Password",
                type="password",
                help="Enter your irth utilitsphere password"
            )
        
        st.write("**Important:** Ensure your irth credentials have administrative access to Manage Map Layers")
        st.write("Manual verification: [irth Manage Map Layers](https://www.irth.com/Utilisphere/Administration/ManageMapLayers/ManageMapLayers.aspx)")
        
        authenticate_button = st.form_submit_button("Authenticate with irth", type="primary")
        
        if authenticate_button:
            if irth_username and irth_password:
                with st.spinner("Authenticating with irth utilitsphere..."):
                    session, error = authenticate_irth(irth_username, irth_password, debug_mode)
                    
                    if session:
                        st.session_state.irth_session = session
                        st.session_state.irth_authenticated = True
                        st.session_state.irth_debug_mode = debug_mode
                        st.success("Successfully authenticated with irth utilitsphere!")
                    else:
                        st.error(f"Failed to log in to irth: {error}")
                        st.session_state.irth_authenticated = False
                        
                        if debug_mode:
                            st.write("**Troubleshooting Tips:**")
                            st.write("- Verify your username and password are correct")
                            st.write("- Check that your account has administrative privileges")
                            st.write("- Try accessing the irth website manually first")
                            st.write("- The page structure may have changed - contact support if issue persists")
            else:
                st.warning("Please enter both username and password")
    
    # Display irth Map Layers (if authenticated)
    if st.session_state.get('irth_authenticated', False) and 'irth_session' in st.session_state:
        st.subheader("📋 View irth Map Layer URLs")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Refresh irth Layer List", type="secondary"):
                debug_mode = st.session_state.get('irth_debug_mode', False)
                with st.spinner("Retrieving irth map layers..."):
                    layers, error = get_irth_map_layers(st.session_state.irth_session, debug_mode)
                    
                    if error:
                        if "403" in error:
                            st.error("Access forbidden - please check your irth credentials have administrative access")
                        elif "404" in error:
                            st.error("No layer URLs detected on page - page structure may have changed")
                        elif "expired" in error.lower():
                            st.error("Session expired - please re-authenticate with irth")
                        else:
                            st.error(f"No layer URLs detected: {error}")
                        
                        if debug_mode:
                            st.write("**Troubleshooting:**")
                            st.write("- Verify page structure hasn't changed")
                            st.write("- Check if JavaScript is loading layer data dynamically")
                            st.write("- Try the demo mode to test the interface")
                    else:
                        st.session_state.irth_layers = layers
                        if layers:
                            st.success(f"Successfully retrieved {len(layers)} layer URLs from irth")
                        else:
                            st.warning("Connected to irth but no layer URLs found on the page")
        
        with col2:
            if st.button("Use Demo Mode", type="secondary", help="Test with sample data"):
                # Provide demo data for testing
                demo_layers = [
                    {
                        'name': 'Water Utilities Layer',
                        'url': 'https://services.arcgis.com/example/ArcGIS/rest/services/WaterUtilities/FeatureServer/0',
                        'id': 1,
                        'source': 'Demo data'
                    },
                    {
                        'name': 'Electric Grid Layer',
                        'url': 'https://services.arcgis.com/example/ArcGIS/rest/services/ElectricGrid/FeatureServer/0',
                        'id': 2,
                        'source': 'Demo data'
                    },
                    {
                        'name': 'Gas Infrastructure',
                        'url': 'https://services.arcgis.com/example/ArcGIS/rest/services/GasInfra/FeatureServer/0',
                        'id': 3,
                        'source': 'Demo data'
                    }
                ]
                st.session_state.irth_layers = demo_layers
                st.success("Demo mode activated with sample layer data")
        
        # Display current irth layers
        if 'irth_layers' in st.session_state and st.session_state.irth_layers:
            st.write("**Current irth Map Layers:**")
            df = pd.DataFrame(st.session_state.irth_layers)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Click 'Refresh irth Layer List' to load current map layers")
        
        # Update irth Map Layer URLs
        st.subheader("🔄 Update irth Map Layer URLs")
        
        # Get ArcGIS feature layers
        feature_layers = get_feature_layers()
        
        if feature_layers:
            with st.form("update_irth_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    # Select ArcGIS layer
                    arcgis_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
                    selected_arcgis_key = st.selectbox(
                        "Select ArcGIS Online Feature Layer",
                        options=list(arcgis_options.keys()),
                        help="Choose the ArcGIS layer whose URL you want to sync with irth"
                    )
                    
                    if selected_arcgis_key:
                        selected_arcgis_layer = arcgis_options[selected_arcgis_key]
                        st.info(f"FeatureServer URL: {selected_arcgis_layer.url}")
                
                with col2:
                    # irth layer identification
                    irth_layer_id = st.text_input(
                        "irth Layer ID or Name",
                        help="Enter the irth layer ID or name to update"
                    )
                    
                    irth_layer_name = st.text_input(
                        "irth Layer Display Name (Optional)",
                        help="Optional: Update the display name for the layer"
                    )
                
                update_irth_button = st.form_submit_button("Sync URL with irth", type="primary")
                
                if update_irth_button:
                    if selected_arcgis_key and irth_layer_id:
                        selected_layer = arcgis_options[selected_arcgis_key]
                        new_url = selected_layer.url
                        
                        with st.spinner("Updating irth layer URL..."):
                            success, message = update_irth_layer_url(
                                st.session_state.irth_session,
                                irth_layer_id,
                                new_url,
                                irth_layer_name
                            )
                            
                            if success:
                                st.success(message)
                                st.info(f"Updated irth layer '{irth_layer_id}' with URL: {new_url}")
                                
                                # Generate update log for IRTH integration
                                update_info = {
                                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'arcgis_layer': selected_layer.title,
                                    'arcgis_id': selected_layer.id,
                                    'irth_layer_id': irth_layer_id,
                                    'new_url': new_url,
                                    'status': 'success'
                                }
                                
                                # Offer download of update log
                                log_df = pd.DataFrame([update_info])
                                csv_data = log_df.to_csv(index=False)
                                
                                st.download_button(
                                    label="Download Update Log (CSV)",
                                    data=csv_data,
                                    file_name=f"irth_update_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv"
                                )
                            else:
                                st.error(message)
                    else:
                        st.warning("Please select an ArcGIS layer and enter an irth layer ID")
        else:
            st.warning("No ArcGIS feature layers found. Please ensure you're authenticated with ArcGIS Online.")
        
        # Manual verification section
        st.subheader("🔍 Manual Verification")
        st.write("""
        To manually verify the updates:
        1. Visit the [irth Manage Map Layers page](https://www.irth.com/Utilisphere/Administration/ManageMapLayers/ManageMapLayers.aspx)
        2. Check that the layer URLs have been updated correctly
        3. Test the layer functionality in your irth applications
        """)
        
        # Logout button
        if st.button("Logout from irth", type="secondary"):
            if 'irth_session' in st.session_state:
                del st.session_state.irth_session
            st.session_state.irth_authenticated = False
            st.info("Logged out from irth utilitsphere")
            st.rerun()
    
    else:
        st.info("Please authenticate with irth utilitsphere to view and update map layers")
        
        # Add demo mode for testing without authentication
        st.subheader("🧪 Demo Mode")
        st.write("Test the irth integration interface with sample data (no authentication required)")
        
        if st.button("Enable Demo Mode", type="secondary"):
            st.session_state.irth_authenticated = True
            st.session_state.irth_session = "demo_session"
            demo_layers = [
                {
                    'name': 'Water Distribution Network',
                    'url': 'https://services.arcgis.com/demo/ArcGIS/rest/services/WaterDistribution/FeatureServer/0',
                    'id': 1,
                    'source': 'Demo data'
                },
                {
                    'name': 'Electric Transmission Lines',
                    'url': 'https://services.arcgis.com/demo/ArcGIS/rest/services/ElectricTransmission/FeatureServer/0',
                    'id': 2,
                    'source': 'Demo data'
                },
                {
                    'name': 'Gas Pipeline Infrastructure',
                    'url': 'https://services.arcgis.com/demo/ArcGIS/rest/services/GasPipeline/FeatureServer/0',
                    'id': 3,
                    'source': 'Demo data'
                }
            ]
            st.session_state.irth_layers = demo_layers
            st.success("Demo mode enabled! You can now test the irth integration features.")
            st.rerun()

def apply_sharing_settings(item, sharing_level):
    """Apply sharing settings to an item"""
    try:
        if sharing_level == "Public":
            item.share(everyone=True)
        elif sharing_level == "Organization":
            item.share(org=True)
        # Private is default, no sharing needed
        return True
    except Exception as e:
        st.error(f"Error applying sharing settings: {str(e)}")
        return False

def generate_irth_export(layer_info, operation_type="update"):
    """Generate CSV export for irth integration"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    export_data = {
        'operation_type': [operation_type],
        'layer_title': [layer_info.get('title', '')],
        'layer_id': [layer_info.get('id', '')],
        'feature_server_url': [layer_info.get('url', '')],
        'owner': [layer_info.get('owner', '')],
        'sharing_level': [layer_info.get('sharing', 'Private')],
        'timestamp': [timestamp],
        'irth_id': [st.session_state.user_settings.get('irth_id', '')]
    }
    
    df = pd.DataFrame(export_data)
    return df

def batch_edit_features(layer, features, operation='add', batch_size=None):
    """Apply edits in batches for better performance"""
    if not batch_size:
        batch_size = st.session_state.user_settings.get('batch_size', 1000)
    
    total_features = len(features)
    success_count = 0
    
    # Create progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(0, total_features, batch_size):
        batch = features[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_features + batch_size - 1) // batch_size
        
        status_text.text(f"Processing batch {batch_num}/{total_batches}...")
        
        try:
            if operation == 'add':
                result = layer.edit_features(adds=batch)
                batch_success = sum(1 for r in result.get('addResults', []) if r.get('success', False))
            elif operation == 'update':
                result = layer.edit_features(updates=batch)
                batch_success = sum(1 for r in result.get('updateResults', []) if r.get('success', False))
            elif operation == 'delete':
                # For delete, batch contains where clauses
                result = layer.delete_features(where=batch)
                batch_success = sum(1 for r in result.get('deleteResults', []) if r.get('success', False))
            else:
                batch_success = 0
                
            success_count += batch_success
            
        except Exception as e:
            st.error(f"Error in batch {batch_num}: {str(e)}")
        
        # Update progress
        progress = min((i + batch_size) / total_features, 1.0)
        progress_bar.progress(progress)
        time.sleep(0.1)  # Small delay for UI responsiveness
    
    status_text.text(f"Completed: {success_count}/{total_features} features processed successfully")
    return success_count

def get_layer_sublayers(feature_layer):
    """Get sublayers from a feature layer"""
    try:
        flc = FeatureLayerCollection.fromitem(feature_layer)
        sublayers = []
        for layer in flc.layers:
            sublayers.append({
                'id': layer.properties.id,
                'name': layer.properties.name,
                'layer': layer
            })
        return sublayers
    except Exception as e:
        st.error(f"Error getting sublayers: {str(e)}")
        return []

def load_shapefile_data(zip_file):
    """Load shapefile data from zip file"""
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_zip_path = os.path.join(temp_dir, "temp.zip")
            with open(temp_zip_path, "wb") as f:
                f.write(zip_file.getbuffer())
            
            # Extract zip file
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find the .shp file
            shp_files = [f for f in os.listdir(temp_dir) if f.endswith('.shp')]
            if shp_files:
                shp_path = os.path.join(temp_dir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                return gdf
            else:
                st.error("No shapefile found in zip archive")
                return None
    except Exception as e:
        st.error(f"Error loading shapefile: {str(e)}")
        return None

def display_enhanced_editable_table(gdf, target_layer=None, key_suffix=""):
    """Display form-based table editing interface with ArcGIS API integration"""
    if gdf is None or gdf.empty:
        st.warning("No data to display")
        return None, None
    
    st.subheader("Feature Data Editor")
    
    # Convert geometry to string for display
    display_df = gdf.copy()
    if 'geometry' in display_df.columns:
        display_df['geometry'] = display_df['geometry'].astype(str)
    
    # Initialize session state for edit tracking
    if f'editing_row_{key_suffix}' not in st.session_state:
        st.session_state[f'editing_row_{key_suffix}'] = None
    if f'delete_confirmation_{key_suffix}' not in st.session_state:
        st.session_state[f'delete_confirmation_{key_suffix}'] = None
    if f'changes_applied_{key_suffix}' not in st.session_state:
        st.session_state[f'changes_applied_{key_suffix}'] = []
    
    # Display summary info
    st.info(f"Total Features: {len(display_df)} | Columns: {len(display_df.columns)}")
    
    # Progress tracking for applied changes
    if st.session_state[f'changes_applied_{key_suffix}']:
        st.success(f"Changes applied: {len(st.session_state[f'changes_applied_{key_suffix}'])}")
    
    # Form-based row display and editing
    for idx, row in display_df.iterrows():
        # Create unique container for each row
        with st.container():
            st.markdown(f"### Row {idx + 1}")
            
            # Create form for each row
            with st.form(f"row_form_{idx}_{key_suffix}"):
                # Display fields in a grid layout
                cols = st.columns(min(3, len(display_df.columns)))
                edited_values = {}
                
                for col_idx, column in enumerate(display_df.columns):
                    with cols[col_idx % 3]:
                        current_value = row[column]
                        # Handle different data types appropriately
                        if pd.isna(current_value):
                            current_value = ""
                        
                        edited_values[column] = st.text_input(
                            label=f"{column}",
                            value=str(current_value),
                            key=f"field_{column}_{idx}_{key_suffix}",
                            help=f"Edit {column} for row {idx + 1}"
                        )
                
                # Action buttons for each row
                col1, col2, col3 = st.columns([1, 1, 2])
                
                with col1:
                    save_edit = st.form_submit_button(
                        "Save Edit",
                        type="primary",
                        help="Save changes to this row"
                    )
                
                with col2:
                    delete_row = st.form_submit_button(
                        "Delete",
                        help="Delete this row"
                    )
                
                # Handle Save Edit action
                if save_edit:
                    try:
                        with st.spinner(f"Saving changes to row {idx + 1}..."):
                            if target_layer:
                                # Apply changes to ArcGIS layer
                                feature_attributes = {k: v for k, v in edited_values.items() if k != 'geometry'}
                                
                                # Get OBJECTID for update (assuming it exists)
                                if 'OBJECTID' in row:
                                    feature_attributes['OBJECTID'] = row['OBJECTID']
                                    
                                    # Create feature for update
                                    update_feature = {
                                        'attributes': feature_attributes
                                    }
                                    
                                    # Add geometry if present
                                    if 'geometry' in edited_values and edited_values['geometry']:
                                        try:
                                            from shapely import wkt
                                            geom = wkt.loads(edited_values['geometry'])
                                            update_feature['geometry'] = json.loads(geom.__geo_interface__)
                                        except:
                                            pass
                                    
                                    # Apply update to ArcGIS layer
                                    result = target_layer.edit_features(updates=[update_feature])
                                    
                                    if result.get('updateResults') and result['updateResults'][0].get('success'):
                                        # Update local dataframe
                                        for col, value in edited_values.items():
                                            display_df.loc[idx, col] = value
                                        
                                        st.session_state[f'changes_applied_{key_suffix}'].append(f"Updated row {idx + 1}")
                                        st.success(f"Row {idx + 1} updated successfully!")
                                        st.rerun()
                                    else:
                                        error_msg = result.get('updateResults', [{}])[0].get('error', {}).get('description', 'Unknown error')
                                        st.error(f"Failed to update row {idx + 1}: {error_msg}")
                                else:
                                    st.error("Cannot update row: OBJECTID not found")
                            else:
                                # Local update only (for preview mode)
                                for col, value in edited_values.items():
                                    display_df.loc[idx, col] = value
                                st.success(f"Row {idx + 1} updated locally!")
                                st.rerun()
                                
                    except Exception as e:
                        st.error(f"Error updating row {idx + 1}: {str(e)}")
                
                # Handle Delete action with confirmation
                if delete_row:
                    st.session_state[f'delete_confirmation_{key_suffix}'] = idx
                    st.rerun()
            
            # Display delete confirmation dialog
            if st.session_state[f'delete_confirmation_{key_suffix}'] == idx:
                st.warning(f"⚠️ Are you sure you want to delete Row {idx + 1}?")
                st.write("This action cannot be undone.")
                
                # Show row data for confirmation
                with st.expander("Row data to be deleted"):
                    for col, val in row.items():
                        st.write(f"**{col}:** {val}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"Confirm Delete Row {idx + 1}", type="primary", key=f"confirm_del_{idx}_{key_suffix}"):
                        try:
                            with st.spinner(f"Deleting row {idx + 1}..."):
                                if target_layer and 'OBJECTID' in row:
                                    # Delete from ArcGIS layer
                                    where_clause = f"OBJECTID = {row['OBJECTID']}"
                                    result = target_layer.delete_features(where=where_clause)
                                    
                                    if result.get('deleteResults') and result['deleteResults'][0].get('success'):
                                        # Remove from local dataframe
                                        display_df = display_df.drop(idx).reset_index(drop=True)
                                        st.session_state[f'changes_applied_{key_suffix}'].append(f"Deleted row {idx + 1}")
                                        st.session_state[f'delete_confirmation_{key_suffix}'] = None
                                        st.success(f"Row {idx + 1} deleted successfully!")
                                        st.rerun()
                                    else:
                                        error_msg = result.get('deleteResults', [{}])[0].get('error', {}).get('description', 'Unknown error')
                                        st.error(f"Failed to delete row {idx + 1}: {error_msg}")
                                else:
                                    # Local delete only
                                    display_df = display_df.drop(idx).reset_index(drop=True)
                                    st.session_state[f'delete_confirmation_{key_suffix}'] = None
                                    st.success(f"Row {idx + 1} deleted locally!")
                                    st.rerun()
                                    
                        except Exception as e:
                            st.error(f"Error deleting row {idx + 1}: {str(e)}")
                
                with col2:
                    if st.button(f"Cancel Delete", key=f"cancel_del_{idx}_{key_suffix}"):
                        st.session_state[f'delete_confirmation_{key_suffix}'] = None
                        st.rerun()
            
            st.divider()  # Visual separator between rows
    
    # Add new row functionality
    st.subheader("Add New Row")
    with st.form(f"add_new_row_{key_suffix}"):
        st.write("Enter values for new feature:")
        new_values = {}
        
        cols = st.columns(min(3, len(display_df.columns)))
        for col_idx, column in enumerate(display_df.columns):
            if column != 'OBJECTID':  # Don't allow editing OBJECTID for new rows
                with cols[col_idx % 3]:
                    new_values[column] = st.text_input(
                        f"{column}",
                        key=f"new_{column}_{key_suffix}",
                        help=f"Enter value for {column}"
                    )
        
        if st.form_submit_button("Add New Row", type="primary"):
            try:
                with st.spinner("Adding new row..."):
                    if target_layer:
                        # Add to ArcGIS layer
                        feature_attributes = {k: v for k, v in new_values.items() if k != 'geometry' and v}
                        
                        new_feature = {
                            'attributes': feature_attributes
                        }
                        
                        # Add geometry if present
                        if 'geometry' in new_values and new_values['geometry']:
                            try:
                                from shapely import wkt
                                geom = wkt.loads(new_values['geometry'])
                                new_feature['geometry'] = json.loads(geom.__geo_interface__)
                            except:
                                pass
                        
                        # Apply addition to ArcGIS layer
                        result = target_layer.edit_features(adds=[new_feature])
                        
                        if result.get('addResults') and result['addResults'][0].get('success'):
                            # Add to local dataframe
                            new_row = pd.Series(new_values, name=len(display_df))
                            display_df = pd.concat([display_df, new_row.to_frame().T], ignore_index=True)
                            st.session_state[f'changes_applied_{key_suffix}'].append("Added new row")
                            st.success("New row added successfully!")
                            st.rerun()
                        else:
                            error_msg = result.get('addResults', [{}])[0].get('error', {}).get('description', 'Unknown error')
                            st.error(f"Failed to add new row: {error_msg}")
                    else:
                        # Local add only
                        new_row = pd.Series(new_values, name=len(display_df))
                        display_df = pd.concat([display_df, new_row.to_frame().T], ignore_index=True)
                        st.success("New row added locally!")
                        st.rerun()
                        
            except Exception as e:
                st.error(f"Error adding new row: {str(e)}")
    
    return display_df, {'added': [], 'deleted': [], 'modified': []}

def display_editable_table(gdf):
    """Backward compatibility wrapper"""
    return display_enhanced_editable_table(gdf, "default")

def apply_edits_to_layer(feature_layer, original_gdf, edited_df, changes):
    """Apply edits to the feature layer"""
    try:
        if not changes['added'] and not changes['deleted'] and not changes['modified']:
            st.info("No changes to apply")
            return True
        
        # Convert edited_df back to GeoDataFrame if needed
        if 'geometry' in edited_df.columns and isinstance(edited_df['geometry'].iloc[0], str):
            from shapely import wkt
            edited_df['geometry'] = edited_df['geometry'].apply(wkt.loads)
            edited_gdf = gpd.GeoDataFrame(edited_df, geometry='geometry')
        else:
            edited_gdf = edited_df
        
        # Apply edits using ArcGIS API
        if changes['deleted']:
            # Delete features
            delete_ids = [str(i) for i in changes['deleted']]
            if hasattr(feature_layer, 'delete_features'):
                result = feature_layer.delete_features(where=f"OBJECTID IN ({','.join(delete_ids)})")
                if not result.get('deleteResults', [{}])[0].get('success', False):
                    st.error("Failed to delete some features")
        
        if changes['added']:
            # Add new features
            new_features = []
            for idx in changes['added']:
                if idx < len(edited_gdf):
                    row = edited_gdf.iloc[idx]
                    feature = {
                        'attributes': {col: val for col, val in row.items() if col != 'geometry'},
                        'geometry': json.loads(row['geometry'].__geo_interface__) if 'geometry' in row else None
                    }
                    new_features.append(feature)
            
            if new_features and hasattr(feature_layer, 'edit_features'):
                result = feature_layer.edit_features(adds=new_features)
                if not all(r.get('success', False) for r in result.get('addResults', [])):
                    st.error("Failed to add some features")
        
        if changes['modified']:
            # Update existing features
            update_features = []
            for idx in changes['modified']:
                if idx < len(edited_gdf):
                    row = edited_gdf.iloc[idx]
                    feature = {
                        'attributes': {col: val for col, val in row.items() if col != 'geometry'},
                        'geometry': json.loads(row['geometry'].__geo_interface__) if 'geometry' in row else None
                    }
                    update_features.append(feature)
            
            if update_features and hasattr(feature_layer, 'edit_features'):
                result = feature_layer.edit_features(updates=update_features)
                if not all(r.get('success', False) for r in result.get('updateResults', [])):
                    st.error("Failed to update some features")
        
        return True
    except Exception as e:
        st.error(f"Error applying edits: {str(e)}")
        return False

def update_existing_layer():
    """Update an existing feature layer"""
    st.header("🔄 Update Existing Layer")
    
    # Get existing feature layers
    feature_layers = get_feature_layers()
    
    if not feature_layers:
        st.warning("No feature layers found in your account")
        return
    
    # Create layer selection options
    layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
    
    # Layer selection outside form for sublayer detection
    selected_layer_key = st.selectbox(
        "Select Feature Layer to Update",
        options=list(layer_options.keys()),
        help="Choose the feature layer you want to update",
        key="layer_selector"
    )
    
    selected_layer = layer_options[selected_layer_key] if selected_layer_key else None
    
    # Get sublayers if available
    sublayers = []
    selected_sublayer = None
    if selected_layer:
        sublayers = get_layer_sublayers(selected_layer)
        
        if len(sublayers) > 1:
            st.subheader("Sublayer Selection")
            sublayer_options = {f"{sub['name']} (ID: {sub['id']})": sub for sub in sublayers}
            selected_sublayer_key = st.selectbox(
                "Select Sublayer to Update",
                options=list(sublayer_options.keys()),
                help="Choose the specific sublayer to update",
                key="sublayer_selector"
            )
            selected_sublayer = sublayer_options[selected_sublayer_key] if selected_sublayer_key else None
        elif len(sublayers) == 1:
            selected_sublayer = sublayers[0]
            st.info(f"Single sublayer detected: {selected_sublayer['name']}")
    
    with st.form("update_layer_form"):
        # File upload
        uploaded_file = st.file_uploader(
            "Upload Shapefile (.zip)",
            type=['zip'],
            help="Upload a .zip file containing the updated shapefile"
        )
        
        # Sharing level
        sharing_level = st.radio(
            "Sharing Level",
            options=["Private", "Organization", "Public"],
            help="Set the sharing level for the updated layer"
        )
        
        update_button = st.form_submit_button("Update Layer", type="primary")
        
        if update_button:
            if uploaded_file and selected_layer:
                # Validate zip file
                is_valid, message = validate_zip_file(uploaded_file)
                if not is_valid:
                    st.error(f"Invalid zip file: {message}")
                    return
                
                try:
                    # Load and validate new data first
                    st.subheader("Data Validation and Preparation")
                    gdf = load_shapefile_data(uploaded_file)
                    if gdf is None:
                        st.error("Failed to load shapefile data")
                        return
                    
                    # Determine target layer for validation
                    target_layer = selected_sublayer['layer'] if selected_sublayer else selected_layer.layers[0]
                    
                    # Get current layer data for comparison
                    with st.spinner("Loading current layer data..."):
                        current_features = target_layer.query()
                        current_count = len(current_features.features) if current_features.features else 0
                        
                        # Get layer schema
                        layer_fields = target_layer.properties.fields
                        layer_field_names = [field['name'] for field in layer_fields]
                        layer_geometry_type = target_layer.properties.geometryType
                    
                    # Validate coordinate system with enhanced options
                    gdf, crs_valid = validate_coordinate_system(gdf, target_layer)
                    if not crs_valid:
                        st.error("Coordinate system validation failed")
                        return
                    
                    # Schema validation
                    st.subheader("Schema Validation")
                    new_field_names = list(gdf.columns)
                    if 'geometry' in new_field_names:
                        new_field_names.remove('geometry')
                    
                    # Check field compatibility
                    missing_fields = set(layer_field_names) - set(new_field_names) - {'OBJECTID', 'Shape_Length', 'Shape_Area'}
                    extra_fields = set(new_field_names) - set(layer_field_names)
                    
                    schema_col1, schema_col2 = st.columns(2)
                    with schema_col1:
                        st.write("**Target Layer Fields:**")
                        for field in layer_field_names:
                            if field not in ['OBJECTID', 'Shape_Length', 'Shape_Area']:
                                st.write(f"• {field}")
                    
                    with schema_col2:
                        st.write("**New Data Fields:**")
                        for field in new_field_names:
                            st.write(f"• {field}")
                    
                    if missing_fields:
                        st.warning(f"Missing fields in new data: {', '.join(missing_fields)}")
                    if extra_fields:
                        st.info(f"Extra fields in new data: {', '.join(extra_fields)}")
                    
                    # Geometry type validation
                    if hasattr(gdf.geometry.iloc[0], 'geom_type'):
                        new_geometry_type = gdf.geometry.iloc[0].geom_type
                        geometry_compatible = (
                            (layer_geometry_type == 'esriGeometryPoint' and new_geometry_type in ['Point', 'MultiPoint']) or
                            (layer_geometry_type == 'esriGeometryPolyline' and new_geometry_type in ['LineString', 'MultiLineString']) or
                            (layer_geometry_type == 'esriGeometryPolygon' and new_geometry_type in ['Polygon', 'MultiPolygon'])
                        )
                        
                        if not geometry_compatible:
                            st.error(f"Geometry type mismatch: Layer expects {layer_geometry_type}, data contains {new_geometry_type}")
                            return
                        else:
                            st.success(f"Geometry type compatible: {new_geometry_type}")
                    
                    # Before/After comparison
                    st.subheader("Before/After Comparison")
                    comparison_col1, comparison_col2 = st.columns(2)
                    
                    with comparison_col1:
                        st.write("**Current State:**")
                        st.metric("Feature Count", current_count)
                        if current_count > 0:
                            sample_feature = current_features.features[0]
                            st.write("**Sample Attributes:**")
                            for key, value in list(sample_feature.attributes.items())[:5]:
                                if key not in ['OBJECTID', 'Shape_Length', 'Shape_Area']:
                                    st.write(f"• {key}: {value}")
                    
                    with comparison_col2:
                        st.write("**New State:**")
                        st.metric("Feature Count", len(gdf))
                        st.write("**Sample Attributes:**")
                        sample_row = gdf.iloc[0] if len(gdf) > 0 else None
                        if sample_row is not None:
                            for col in list(gdf.columns)[:5]:
                                if col != 'geometry':
                                    st.write(f"• {col}: {sample_row[col]}")
                    
                    # Update method selection
                    update_method = st.radio(
                        "Update Method",
                        ["Truncate and Append", "Overwrite Entire Layer"],
                        help="Choose how to update the layer"
                    )
                    
                    # Confirmation and execution
                    if st.button("Confirm and Execute Update", type="primary"):
                        with st.spinner("Executing update..."):
                            if update_method == "Truncate and Append" and selected_sublayer:
                                # Precise sublayer targeting
                                progress_bar = st.progress(0)
                                status_text = st.empty()
                                
                                # Step 1: Truncate
                                status_text.text("Step 1/3: Truncating sublayer...")
                                progress_bar.progress(0.33)
                                
                                truncate_result = target_layer.manager.truncate()
                                if not truncate_result.get('success', False):
                                    st.error("Failed to truncate sublayer")
                                    return
                                
                                # Step 2: Prepare features
                                status_text.text("Step 2/3: Preparing new features...")
                                progress_bar.progress(0.66)
                                
                                features = []
                                batch_size = st.session_state.user_settings.get('batch_size', 1000)
                                
                                for _, row in gdf.iterrows():
                                    feature = {
                                        'attributes': {col: val for col, val in row.items() if col != 'geometry' and not pd.isna(val)}
                                    }
                                    
                                    if 'geometry' in row and hasattr(row['geometry'], '__geo_interface__'):
                                        feature['geometry'] = row['geometry'].__geo_interface__
                                    
                                    features.append(feature)
                                
                                # Step 3: Append in batches
                                status_text.text("Step 3/3: Adding new features...")
                                progress_bar.progress(1.0)
                                
                                success_count = 0
                                total_batches = (len(features) + batch_size - 1) // batch_size
                                
                                for i in range(0, len(features), batch_size):
                                    batch = features[i:i + batch_size]
                                    batch_num = (i // batch_size) + 1
                                    status_text.text(f"Adding batch {batch_num}/{total_batches} ({len(batch)} features)...")
                                    
                                    result = target_layer.edit_features(adds=batch)
                                    batch_success = sum(1 for r in result.get('addResults', []) if r.get('success', False))
                                    success_count += batch_success
                                    
                                    if batch_success != len(batch):
                                        st.warning(f"Batch {batch_num}: {batch_success}/{len(batch)} features added successfully")
                                
                                status_text.text("Update completed!")
                                
                                if success_count == len(features):
                                    st.success(f"Sublayer '{selected_sublayer['name']}' updated successfully!")
                                    st.info(f"Added {success_count} features")
                                else:
                                    st.warning(f"Partial success: {success_count}/{len(features)} features added")
                                
                            else:
                                # Overwrite entire layer
                                with tempfile.TemporaryDirectory() as temp_dir:
                                    temp_zip_path = os.path.join(temp_dir, "update.zip")
                                    with open(temp_zip_path, "wb") as f:
                                        f.write(uploaded_file.getbuffer())
                                    
                                    flc = FeatureLayerCollection.fromitem(selected_layer)
                                    result = flc.manager.overwrite(temp_zip_path)
                                    
                                    if result:
                                        st.success("Layer updated successfully!")
                                    else:
                                        st.error("Failed to update layer")
                            
                            # Apply sharing settings
                            apply_sharing_settings(selected_layer, sharing_level)
                            
                            # Generate IRTH export
                            layer_info = {
                                'title': selected_layer.title,
                                'id': selected_layer.id,
                                'url': selected_layer.url,
                                'sublayer': selected_sublayer['name'] if selected_sublayer else None,
                                'method': update_method,
                                'features_updated': len(gdf)
                            }
                            
                            irth_df = generate_irth_export(layer_info, "update")
                            csv_data = irth_df.to_csv(index=False)
                            
                            # Final results display
                            st.subheader("Update Results")
                            results_col1, results_col2 = st.columns(2)
                            
                            with results_col1:
                                st.write("**Layer Information:**")
                                st.write(f"• Title: {selected_layer.title}")
                                st.write(f"• ID: {selected_layer.id}")
                                st.write(f"• Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                                if selected_sublayer:
                                    st.write(f"• Sublayer: {selected_sublayer['name']}")
                            
                            with results_col2:
                                st.write("**Update Summary:**")
                                st.write(f"• Method: {update_method}")
                                st.write(f"• Features: {len(gdf)}")
                                st.write(f"• Sharing: {sharing_level}")
                                
                                # IRTH download
                                st.download_button(
                                    label="Download IRTH Export (CSV)",
                                    data=csv_data,
                                    file_name=f"irth_update_{selected_layer.title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv"
                                )
                            
                            st.info(f"FeatureServer URL: {selected_layer.url}")
                                
                except Exception as e:
                    st.error(f"Error updating layer: {str(e)}")
                    if "schema" in str(e).lower():
                        st.info("Make sure the uploaded shapefile has compatible schema with the existing layer")
            else:
                st.warning("Please select a layer and upload a zip file")

def create_new_layer():
    """Create a new feature layer"""
    st.header("➕ Create New Layer")
    
    # Initialize session state for data editing
    if 'shapefile_data' not in st.session_state:
        st.session_state.shapefile_data = None
    if 'edited_data' not in st.session_state:
        st.session_state.edited_data = None
    if 'show_editor' not in st.session_state:
        st.session_state.show_editor = False
    
    # File upload section
    st.subheader("Upload Shapefile")
    uploaded_file = st.file_uploader(
        "Upload Shapefile (.zip)",
        type=['zip'],
        help="Upload a .zip file containing the shapefile",
        key="create_file_uploader"
    )
    
    if uploaded_file:
        # Validate zip file
        is_valid, message = validate_zip_file(uploaded_file)
        if not is_valid:
            st.error(f"Invalid zip file: {message}")
        else:
            st.success(f"Valid shapefile: {message}")
            
            # Load shapefile data
            if st.button("Load and Preview Data", key="load_preview"):
                with st.spinner("Loading shapefile data..."):
                    gdf = load_shapefile_data(uploaded_file)
                    if gdf is not None:
                        # Validate coordinate system
                        gdf, crs_valid = validate_coordinate_system(gdf)
                        
                        st.session_state.shapefile_data = gdf
                        st.session_state.show_editor = True
                        st.success(f"Loaded {len(gdf)} features with {len(gdf.columns)} attributes")
                        
                        # Display CRS info
                        if gdf.crs:
                            st.info(f"Coordinate System: {gdf.crs}")
                        else:
                            st.warning("No coordinate system detected")
    
    # Data editing section
    if st.session_state.show_editor and st.session_state.shapefile_data is not None:
        st.subheader("Edit Shapefile Data")
        st.info("You can edit, add, or delete rows in the table below. Changes will be applied when creating the layer.")
        
        edited_df, changes = display_editable_table(st.session_state.shapefile_data)
        st.session_state.edited_data = edited_df
        
        if changes and (changes['added'] or changes['deleted'] or changes['modified']):
            st.info(f"Changes detected: {len(changes['added'])} added, {len(changes['modified'])} modified, {len(changes['deleted'])} deleted")
    
    # Layer creation form
    if st.session_state.shapefile_data is not None:
        st.subheader("Create Layer")
        with st.form("create_layer_form"):
            # Layer title
            layer_title = st.text_input(
                "Layer Title",
                help="Enter a title for the new feature layer"
            )
            
            # Sharing level - use default from settings
            default_sharing = st.session_state.user_settings.get('default_sharing_level', 'Private')
            sharing_level = st.radio(
                "Sharing Level",
                options=["Private", "Organization", "Public"],
                index=["Private", "Organization", "Public"].index(default_sharing),
                help="Set the sharing level for the new layer"
            )
            
            # Web maps selection
            web_maps = get_web_maps()
            if web_maps:
                selected_maps = st.multiselect(
                    "Add to Web Maps (Optional)",
                    options=[f"{wm.title} ({wm.id})" for wm in web_maps],
                    help="Select web maps to add this new layer to"
                )
            else:
                selected_maps = []
                st.info("No web maps found in your account")
            
            create_button = st.form_submit_button("Create Layer", type="primary")
            
            if create_button:
                if layer_title:
                    try:
                        with st.spinner("Creating new layer..."):
                            # Use edited data if available, otherwise use original data
                            data_to_use = st.session_state.edited_data if st.session_state.edited_data is not None else st.session_state.shapefile_data
                            
                            # Convert edited data back to GeoDataFrame if needed
                            if 'geometry' in data_to_use.columns and isinstance(data_to_use['geometry'].iloc[0], str):
                                from shapely import wkt
                                data_to_use = data_to_use.copy()
                                data_to_use['geometry'] = data_to_use['geometry'].apply(wkt.loads)
                                data_to_use = gpd.GeoDataFrame(data_to_use, geometry='geometry')
                            
                            # Save edited data to temporary shapefile
                            with tempfile.TemporaryDirectory() as temp_dir:
                                import pathlib
                                temp_shp_path = str(pathlib.Path(temp_dir) / "edited_layer.shp")
                                data_to_use.to_file(temp_shp_path)
                                
                                # Create zip from edited shapefile
                                temp_zip_path = os.path.join(temp_dir, "edited_layer.zip")
                                with zipfile.ZipFile(temp_zip_path, 'w') as zipf:
                                    for ext in ['.shp', '.shx', '.dbf', '.prj']:
                                        file_path = temp_shp_path.replace('.shp', ext)
                                        if os.path.exists(file_path):
                                            zipf.write(file_path, f"edited_layer{ext}")
                                
                                # Add the zip file as an item
                                zip_item = st.session_state.gis.content.add({
                                    'title': layer_title,
                                    'type': 'Shapefile'
                                }, data=temp_zip_path)
                                
                                # Publish as feature layer
                                feature_layer = zip_item.publish()
                                
                                # Apply sharing settings
                                apply_sharing_settings(feature_layer, sharing_level)
                                
                                # Add to web maps if selected
                                if selected_maps:
                                    for map_title in selected_maps:
                                        map_id = map_title.split('(')[-1].replace(')', '')
                                        try:
                                            web_map = st.session_state.gis.content.get(map_id)
                                            # Add layer to web map
                                            web_map_obj = web_map.get_data()
                                            web_map_obj['operationalLayers'].append({
                                                'id': feature_layer.id,
                                                'title': feature_layer.title,
                                                'url': feature_layer.url,
                                                'layerType': 'ArcGISFeatureLayer',
                                                'visibility': True
                                            })
                                            web_map.update(data=web_map_obj)
                                            st.success(f"Added to web map: {web_map.title}")
                                        except Exception as e:
                                            st.warning(f"Could not add to web map {map_title}: {str(e)}")
                                
                                st.success("✅ New layer created successfully!")
                                st.info(f"**FeatureServer URL:** {feature_layer.url}")
                                
                                # Generate IRTH export
                                layer_info = {
                                    'title': feature_layer.title,
                                    'id': feature_layer.id,
                                    'url': feature_layer.url,
                                    'owner': feature_layer.owner,
                                    'sharing': sharing_level
                                }
                                
                                irth_df = generate_irth_export(layer_info, "create")
                                csv_data = irth_df.to_csv(index=False)
                                
                                # Display layer details with IRTH download
                                st.subheader("New Layer Details")
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**Title:** {feature_layer.title}")
                                    st.write(f"**Type:** {feature_layer.type}")
                                    st.write(f"**Sharing:** {sharing_level}")
                                with col2:
                                    st.write(f"**Owner:** {feature_layer.owner}")
                                    st.write(f"**Created:** {feature_layer.created}")
                                    st.write(f"**ID:** {feature_layer.id}")
                                
                                # IRTH integration download
                                st.subheader("IRTH Integration")
                                st.download_button(
                                    label="📥 Download IRTH Export (CSV)",
                                    data=csv_data,
                                    file_name=f"irth_export_{feature_layer.title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv",
                                    help="Download layer metadata for IRTH system integration"
                                )
                                
                                # Clean up the temporary zip item
                                zip_item.delete()
                                
                                # Reset session state
                                st.session_state.shapefile_data = None
                                st.session_state.edited_data = None
                                st.session_state.show_editor = False
                                
                    except Exception as e:
                        st.error(f"Error creating layer: {str(e)}")
                else:
                    st.warning("Please enter a layer title")
    elif uploaded_file is None:
        st.info("Please upload a shapefile to begin creating a new layer")

def edit_layer_data():
    """Edit existing layer data"""
    st.header("✏️ Edit Layer Data")
    
    # Get existing feature layers
    feature_layers = get_feature_layers()
    
    if not feature_layers:
        st.warning("No feature layers found in your account")
        return
    
    # Create layer selection options
    layer_options = {f"{layer.title} ({layer.id})": layer for layer in feature_layers}
    
    # Layer selection
    selected_layer_key = st.selectbox(
        "Select Feature Layer to Edit",
        options=list(layer_options.keys()),
        help="Choose the feature layer you want to edit",
        key="edit_layer_selector"
    )
    
    if not selected_layer_key:
        return
        
    selected_layer = layer_options[selected_layer_key]
    
    # Get sublayers if available
    sublayers = get_layer_sublayers(selected_layer)
    selected_sublayer = None
    
    if len(sublayers) > 1:
        st.subheader("Sublayer Selection")
        sublayer_options = {f"{sub['name']} (ID: {sub['id']})": sub for sub in sublayers}
        selected_sublayer_key = st.selectbox(
            "Select Sublayer to Edit",
            options=list(sublayer_options.keys()),
            help="Choose the specific sublayer to edit",
            key="edit_sublayer_selector"
        )
        selected_sublayer = sublayer_options[selected_sublayer_key] if selected_sublayer_key else None
    elif len(sublayers) == 1:
        selected_sublayer = sublayers[0]
        st.info(f"Editing sublayer: {selected_sublayer['name']}")
    
    if selected_sublayer:
        target_layer = selected_sublayer['layer']
        
        # Load current layer data
        if st.button("Load Current Layer Data", key="load_layer_data"):
            try:
                with st.spinner("Loading layer data..."):
                    # Query features from the layer
                    feature_set = target_layer.query()
                    features = feature_set.features
                    
                    if features:
                        # Convert to DataFrame
                        data_rows = []
                        for feature in features:
                            row = feature.attributes.copy()
                            if feature.geometry:
                                row['geometry'] = str(feature.geometry)
                            data_rows.append(row)
                        
                        df = pd.DataFrame(data_rows)
                        st.session_state.current_layer_data = df
                        st.session_state.target_layer = target_layer
                        st.success(f"Loaded {len(df)} features from layer")
                    else:
                        st.warning("No features found in this layer")
                        
            except Exception as e:
                st.error(f"Error loading layer data: {str(e)}")
        
        # Display editable data if loaded
        if 'current_layer_data' in st.session_state and st.session_state.current_layer_data is not None:
            st.subheader("Edit Layer Features")
            st.info("Use the form-based editor below. Changes are applied immediately to ArcGIS Online.")
            
            # Use the enhanced form-based editing interface
            edited_df, changes = display_enhanced_editable_table(
                st.session_state.current_layer_data,
                target_layer=target_layer,
                key_suffix="edit_layer"
            )
            
            # Update session state with any changes
            if edited_df is not None:
                st.session_state.current_layer_data = edited_df
            
            # Additional controls
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Refresh Layer Data", key="refresh_data", type="secondary"):
                    st.session_state.current_layer_data = None
                    st.success("Data refreshed! Click 'Load Current Layer Data' to reload.")
                    st.rerun()
            
            with col2:
                if st.button("Reset Changes Tracker", key="reset_tracker"):
                    if f'changes_applied_edit_layer' in st.session_state:
                        st.session_state[f'changes_applied_edit_layer'] = []
                    st.success("Changes tracker reset!")
                    st.rerun()

def user_settings():
    """User settings and preferences management"""
    st.header("⚙️ Settings")
    
    # Load current settings
    load_user_settings()
    
    st.subheader("General Preferences")
    
    with st.form("settings_form"):
        # Default sharing level
        default_sharing = st.selectbox(
            "Default Sharing Level",
            options=["Private", "Organization", "Public"],
            index=["Private", "Organization", "Public"].index(
                st.session_state.user_settings.get('default_sharing_level', 'Private')
            ),
            help="Default sharing level for new layers"
        )
        
        # IRTH integration settings
        st.subheader("IRTH Integration")
        irth_id = st.text_input(
            "IRTH ID/Tag",
            value=st.session_state.user_settings.get('irth_id', ''),
            help="Optional IRTH identifier for layer tracking"
        )
        
        # Performance settings
        st.subheader("Performance Settings")
        batch_size = st.number_input(
            "Batch Size for Large Operations",
            min_value=100,
            max_value=10000,
            value=st.session_state.user_settings.get('batch_size', 1000),
            step=100,
            help="Number of features processed in each batch"
        )
        
        # Coordinate system settings
        auto_reproject = st.checkbox(
            "Auto-reproject coordinate systems",
            value=st.session_state.user_settings.get('auto_reproject', True),
            help="Automatically offer reprojection for mismatched coordinate systems"
        )
        
        # Save settings button
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.form_submit_button("Save Settings", type="primary"):
                st.session_state.user_settings.update({
                    'default_sharing_level': default_sharing,
                    'irth_id': irth_id,
                    'batch_size': batch_size,
                    'auto_reproject': auto_reproject
                })
                
                if save_user_settings():
                    st.success("Settings saved successfully!")
                else:
                    st.error("Failed to save settings")
        
        with col2:
            if st.form_submit_button("Reset to Defaults"):
                st.session_state.user_settings = {
                    'default_sharing_level': 'Private',
                    'irth_id': '',
                    'batch_size': 1000,
                    'auto_reproject': True
                }
                save_user_settings()
                st.success("Settings reset to defaults!")
                st.rerun()
        
        with col3:
            if st.form_submit_button("Export Settings"):
                settings_json = json.dumps(st.session_state.user_settings, indent=2)
                st.download_button(
                    label="Download Settings",
                    data=settings_json,
                    file_name="arcgis_layer_updater_settings.json",
                    mime="application/json"
                )
    
    # Import settings
    st.subheader("Import Settings")
    uploaded_settings = st.file_uploader(
        "Upload Settings File",
        type=['json'],
        help="Upload a previously exported settings file"
    )
    
    if uploaded_settings:
        try:
            settings_data = json.load(uploaded_settings)
            st.session_state.user_settings.update(settings_data)
            save_user_settings()
            st.success("Settings imported successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Error importing settings: {str(e)}")
    
    # Display current settings
    st.subheader("Current Settings")
    st.json(st.session_state.user_settings)

def view_content():
    """Display user's existing content"""
    st.header("📋 Your ArcGIS Online Content")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Feature Layers")
        feature_layers = get_feature_layers()
        
        if feature_layers:
            for layer in feature_layers:
                with st.expander(f"📊 {layer.title}"):
                    st.write(f"**Type:** {layer.type}")
                    st.write(f"**Owner:** {layer.owner}")
                    st.write(f"**Modified:** {layer.modified}")
                    st.write(f"**URL:** {layer.url}")
                    st.write(f"**ID:** {layer.id}")
        else:
            st.info("No feature layers found")
    
    with col2:
        st.subheader("Web Maps")
        web_maps = get_web_maps()
        
        if web_maps:
            for web_map in web_maps:
                with st.expander(f"🗺️ {web_map.title}"):
                    st.write(f"**Type:** {web_map.type}")
                    st.write(f"**Owner:** {web_map.owner}")
                    st.write(f"**Modified:** {web_map.modified}")
                    st.write(f"**ID:** {web_map.id}")
        else:
            st.info("No web maps found")

def main():
    """Main application"""
    st.title("🗺️ ArcGISLayerUpdater")
    st.markdown("**Manage your ArcGIS Online hosted feature layers**")
    
    # Check authentication
    if not st.session_state.authenticated:
        authenticate()
        return
    
    # Display user info
    try:
        user = st.session_state.gis.users.me
        st.sidebar.success(f"Logged in as: **{user.fullName}**")
        st.sidebar.info(f"Organization: {st.session_state.gis.properties.name}")
        
        if st.sidebar.button("Logout"):
            st.session_state.gis = None
            st.session_state.authenticated = False
            st.rerun()
    except:
        st.session_state.authenticated = False
        st.rerun()
    
    # Navigation
    st.sidebar.header("Navigation")
    page = st.sidebar.selectbox(
        "Select Action",
        ["View Content", "Update Existing Layer", "Create New Layer", "Edit Layer Data", "irth Integration", "Settings"]
    )
    
    # Display selected page
    if page == "View Content":
        view_content()
    elif page == "Update Existing Layer":
        update_existing_layer()
    elif page == "Create New Layer":
        create_new_layer()
    elif page == "Edit Layer Data":
        edit_layer_data()
    elif page == "irth Integration":
        irth_integration()
    elif page == "Settings":
        user_settings()

if __name__ == "__main__":
    main()