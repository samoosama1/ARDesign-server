import os
from pathlib import Path
import zipfile
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from datetime import datetime

def get_safe_filename(filename):
    """
    Generate a safe filename that works with any storage backend
    """
    name, ext = os.path.splitext(filename)
    slugified_name = slugify(name)
    # Add random string to prevent filename collisions
    safe_name = f"{slugified_name}_{get_random_string(7)}{ext.lower()}"
    return safe_name

def get_storage_path(*parts):
    """
    Safely join path parts for any storage backend
    """
    # Convert all parts to strings and clean them
    clean_parts = [str(part).strip('/') for part in parts if part]
    # Join with forward slashes
    return '/'.join(clean_parts)

def get_model_storage_path(user_id, model_type, timestamp=None):
    """
    Generate storage path for model files
    """
    if timestamp is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return get_storage_path('patents', str(user_id), model_type.lower(), timestamp)

def store_file(file_content, base_path, filename):
    """
    Store a file using Django's storage backend
    """
    safe_name = filename #get_safe_filename(filename)
    storage_path = get_storage_path(base_path, safe_name)
    return default_storage.save(storage_path, ContentFile(file_content))

def handle_zip_contents(zip_file, user_id, model_type, model_filename):
    """
    Process pre-validated ZIP file contents and store in user's directory
    Returns: (base_path, stored_files)
    
    Args:
        zip_file: The validated ZIP file object
        user_id: The ID of the user uploading the file
        model_type: The type of the model file (e.g., 'OBJ', 'STL')
        model_filename: The filename of the main model file in the ZIP
    """
    stored_files = []
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        # Get storage base path based on model type
        base_path = get_model_storage_path(user_id, model_type, timestamp)

        # Extract and store all files from the ZIP
        with zipfile.ZipFile(zip_file) as z:
            for filename in z.namelist():
                # Skip directories
                if filename.endswith('/'):
                    continue

                with z.open(filename) as file:
                    content = file.read()
                    stored_path = store_file(content, base_path, filename)
                    stored_files.append(stored_path)

        return base_path, stored_files
        
    except (zipfile.BadZipFile, OSError) as e:
        # Log the error here if needed
        raise ValueError(f"Failed to process ZIP file: {str(e)}")

def handle_uploaded_file(patent_file, user_id, model_type, model_filename):
    """
    Handle pre-validated file upload using Django's storage API
    Returns: (model_type, base_path, stored_files)
    
    Args:
        patent_file: The validated ZIP file
        user_id: The ID of the user uploading the file
        model_type: The type of model file (from form validation)
        model_filename: The filename of the main model file
    """
    try:
        base_path, stored_files = handle_zip_contents(patent_file, user_id, model_type, model_filename)
        return model_type, base_path, stored_files
    except ValueError as e:
        # Re-raise with more context if needed
        raise ValueError(f"Failed to process upload: {str(e)}")