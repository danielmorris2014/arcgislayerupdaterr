import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

def safe_dataframe_conversion(data, operation_name="operation"):
    """
    Safely convert various data types to DataFrame and handle CSV operations
    Args:
        data: Input data (dict, list, DataFrame, etc.)
        operation_name: Name of operation for error reporting
    Returns:
        (success, dataframe, error_message)
    """
    try:
        if isinstance(data, pd.DataFrame):
            return True, data, None
        elif isinstance(data, dict):
            # Handle dictionary data
            if not data:
                return False, None, "Dictionary is empty"
            
            # Check if all values are lists/arrays of same length
            lengths = []
            for key, value in data.items():
                if isinstance(value, (list, tuple, np.ndarray)):
                    lengths.append(len(value))
                else:
                    # Single values - convert to list
                    data[key] = [value]
                    lengths.append(1)
            
            if lengths and all(l == lengths[0] for l in lengths):
                df = pd.DataFrame(data)
                return True, df, None
            else:
                return False, None, f"Dictionary values have inconsistent lengths: {lengths}"
                
        elif isinstance(data, (list, tuple)):
            if not data:
                return False, None, "List is empty"
            
            # Handle list of dictionaries
            if all(isinstance(item, dict) for item in data):
                df = pd.DataFrame(data)
                return True, df, None
            else:
                # Handle simple list
                df = pd.DataFrame({'value': data})
                return True, df, None
        else:
            return False, None, f"Unsupported data type: {type(data)}"
            
    except Exception as e:
        return False, None, f"Error converting data for {operation_name}: {str(e)}"


def safe_csv_export(data, filename=None, operation_name="CSV export"):
    """
    Safely export data to CSV with proper error handling
    Args:
        data: Input data to export
        filename: Optional filename
        operation_name: Name of operation for error reporting
    Returns:
        (success, csv_string, error_message)
    """
    try:
        # Convert to DataFrame if needed
        success, df, error = safe_dataframe_conversion(data, operation_name)
        if not success:
            return False, None, error
        
        # Generate CSV string
        csv_string = df.to_csv(index=False)
        
        # Optionally save to file
        if filename:
            df.to_csv(filename, index=False)
            
        return True, csv_string, None
        
    except Exception as e:
        return False, None, f"Error during {operation_name}: {str(e)}"


def create_layer_with_safe_handling(data, layer_name="test_layer"):
    """
    Safely create a layer from data with proper error handling
    This replaces the problematic create_layer function
    """
    try:
        st.write(f"Processing data for layer: {layer_name}")
        st.write(f"Input data type: {type(data)}")
        
        # Safely convert to DataFrame
        success, df, error = safe_dataframe_conversion(data, f"layer creation ({layer_name})")
        
        if not success:
            st.error(f"Failed to process data: {error}")
            return False
        
        st.success(f"Successfully converted data to DataFrame with shape: {df.shape}")
        st.dataframe(df.head())
        
        # Safely export to CSV
        success, csv_data, error = safe_csv_export(df, operation_name=f"CSV export for {layer_name}")
        
        if success:
            st.success("CSV export successful!")
            st.download_button(
                label=f"Download {layer_name} CSV",
                data=csv_data,
                file_name=f"{layer_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.error(f"CSV export failed: {error}")
            return False
        
        # Here you would integrate with ArcGIS Online
        st.success(f"Layer '{layer_name}' ready for ArcGIS Online upload!")
        return True
        
    except Exception as e:
        st.error(f"Unexpected error in layer creation: {str(e)}")
        return False


# Streamlit Demo App
st.title("Fixed Data Handling Demo for ArcGISLayerUpdater")
st.write("This demonstrates the fixed data handling that prevents the 'dict' object has no attribute 'to_csv' error.")

# Test cases
st.header("Test Cases")

# Test 1: Dictionary data (your original problem case)
st.subheader("1. Dictionary Data (Original Problem)")
test_data_dict = {'id': [1, 2, 3], 'name': ['Point A', 'Point B', 'Point C'], 'lat': [34.05, 34.06, 34.07]}
st.code(str(test_data_dict))

if st.button("Test Dictionary Data"):
    create_layer_with_safe_handling(test_data_dict, "dictionary_layer")

# Test 2: List of dictionaries
st.subheader("2. List of Dictionaries")
test_data_list = [
    {'id': 1, 'name': 'Point A', 'lat': 34.05},
    {'id': 2, 'name': 'Point B', 'lat': 34.06}
]
st.code(str(test_data_list))

if st.button("Test List Data"):
    create_layer_with_safe_handling(test_data_list, "list_layer")

# Test 3: Already a DataFrame
st.subheader("3. DataFrame Data")
test_data_df = pd.DataFrame({'id': [1, 2], 'name': ['Point A', 'Point B'], 'lat': [34.05, 34.06]})
st.code("pd.DataFrame({'id': [1, 2], 'name': ['Point A', 'Point B'], 'lat': [34.05, 34.06]})")

if st.button("Test DataFrame Data"):
    create_layer_with_safe_handling(test_data_df, "dataframe_layer")

# Test 4: Error case - inconsistent dictionary
st.subheader("4. Error Case - Inconsistent Dictionary")
bad_data = {'id': [1, 2, 3], 'name': ['Point A', 'Point B'], 'lat': [34.05]}  # Different lengths
st.code(str(bad_data))

if st.button("Test Bad Data"):
    create_layer_with_safe_handling(bad_data, "error_layer")

st.header("Implementation Summary")
st.write("""
The fix includes:
- **safe_dataframe_conversion()**: Handles dict, list, DataFrame, and other data types
- **safe_csv_export()**: Safely exports any data type to CSV with error handling
- **create_layer_with_safe_handling()**: Replacement for the problematic create_layer function
- Comprehensive error handling and user feedback
- Support for various data formats from shapefile processing
""")