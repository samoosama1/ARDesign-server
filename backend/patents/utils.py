import os
import zipfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.crypto import get_random_string
from datetime import datetime

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
    # add random uuid to ensure unique path
    patent_folder = timestamp + '_' + get_random_string(8)
    return get_storage_path('patents', str(user_id), model_type.lower(), patent_folder)

def sanitize_filename(filename):
    basename = os.path.basename(filename)
    if not basename or basename.startswith('.'):
        raise ValueError(f"Invalid filename: {filename}")
    if '..' in basename or '\x00' in basename:
        raise ValueError(f"Unsafe filename: {filename}")
    return basename


def store_file(file_content, base_path, filename):
    safe_name = sanitize_filename(filename)
    storage_path = get_storage_path(base_path, safe_name)
    return default_storage.save(storage_path, ContentFile(file_content))

def handle_zip_contents(zip_file, user_id, model_type):
    """
    Process pre-validated ZIP file contents and store in user's directory
    Returns: (base_path, stored_files)
    
    Args:
        zip_file: The validated ZIP file object
        user_id: The ID of the user uploading the file
        model_type: The type of the model file (e.g., 'OBJ', 'STL')
    """
    stored_files = []
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        # Get storage base path based on model type
        base_path = get_model_storage_path(user_id, model_type, timestamp)

        # Extract and store all files from the ZIP
        with zipfile.ZipFile(zip_file) as z:
            for info in z.infolist():
                if info.filename.endswith('/') or info.is_dir():
                    continue

                with z.open(info) as file:
                    content = file.read()
                    stored_path = store_file(content, base_path, info.filename)
                    stored_files.append(stored_path)

        return base_path, stored_files
        
    except (zipfile.BadZipFile, OSError) as e:
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
        base_path, stored_files = handle_zip_contents(patent_file, user_id, model_type)
        return model_type, base_path, stored_files
    except ValueError as e:
        raise ValueError(f"Failed to process upload: {str(e)}")

def delete_directory(directory_path):
    directories, files = default_storage.listdir(directory_path)

    for item in directories:
        item_path = os.path.join(directory_path, item)
        if default_storage.exists(item_path):
            # Recursively delete subdirectories
            delete_directory(item_path)

    for item in files:
        item_path = os.path.join(directory_path, item)
        if default_storage.exists(item_path):
            # Delete files
            default_storage.delete(item_path)

    if default_storage.exists(directory_path):
        default_storage.delete(directory_path)
