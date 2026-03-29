import os
import threading
import zipfile
from site import abs_paths

import numpy as np
import trimesh
from PIL import Image, ImageDraw
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from datetime import datetime
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


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
    # add random uuid to ensure unique path
    patent_folder = timestamp + '_' + get_random_string(8)
    return get_storage_path('patents', str(user_id), model_type.lower(), patent_folder)

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
        # Finally, delete the empty directory
        default_storage.delete(directory_path)


def generate_thumbnail_from_glb(patent, glb_file_path, size=(256, 256)):
    abs_path = settings.MEDIA_ROOT + '/' + glb_file_path
    if not os.path.exists(abs_path):
        logger.error(f"GLB file not found: {abs_path}")
        return

    # Calculate output path
    base_name = os.path.splitext(abs_path)[0]
    thumbnail_path = f"{os.path.splitext(glb_file_path)[0]}_thumb.png"
    abs_thumbnail_path = f"{base_name}_thumb.png"

    try:
        # Load the GLB mesh
        logger.info(f"Loading mesh from: {abs_path}")
        scene = trimesh.load(abs_path)

        # Get combined mesh
        if isinstance(scene, trimesh.Scene):
            mesh = scene.dump(concatenate=True)
        else:
            mesh = scene

        if mesh is None or not hasattr(mesh, 'vertices'):
            logger.error("Failed to load valid mesh from GLB")
            return

        # Create isometric-style view using simple projection
        img = Image.new('RGBA', size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)

        # Apply rotation for nice 3D view (45 degrees around Z, 30 degrees tilt)
        rotation_z = trimesh.transformations.rotation_matrix(
            np.radians(45), [0, 0, 1]
        )
        rotation_x = trimesh.transformations.rotation_matrix(
            np.radians(-30), [1, 0, 0]
        )
        mesh.apply_transform(rotation_z)
        mesh.apply_transform(rotation_x)

        # Get bounds and center
        bounds = mesh.bounds
        center = mesh.centroid
        extents = bounds[1] - bounds[0]
        max_extent = np.max(extents)

        # Scale factor to fit in image
        margin = 20
        scale = min(size[0] - 2 * margin, size[1] - 2 * margin) / max_extent

        # Project vertices to 2D (orthographic projection)
        vertices_2d = mesh.vertices[:, :2]  # Take X and Y coordinates

        # Center and scale
        vertices_2d = (vertices_2d - center[:2]) * scale
        vertices_2d[:, 0] += size[0] / 2
        vertices_2d[:, 1] += size[1] / 2
        vertices_2d[:, 1] = size[1] - vertices_2d[:, 1]  # Flip Y

        # Draw faces
        if hasattr(mesh, 'faces') and len(mesh.faces) > 0:
            # Sort faces by depth (Z coordinate) for proper rendering
            face_centers = mesh.vertices[mesh.faces].mean(axis=1)
            face_depths = face_centers[:, 2]
            sorted_faces = np.argsort(face_depths)

            # Draw each face
            for face_idx in sorted_faces:
                face = mesh.faces[face_idx]
                points = vertices_2d[face].tolist()

                # Calculate simple shading based on Z depth
                z_depth = face_depths[face_idx]
                z_normalized = (z_depth - face_depths.min()) / (face_depths.max() - face_depths.min() + 1e-6)

                # Shade from dark to light based on depth
                shade = int(100 + z_normalized * 155)
                color = (shade, shade, shade, 255)

                # Draw filled polygon
                draw.polygon([tuple(p) for p in points], fill=color, outline=(50, 50, 50, 255))
        else:
            # No faces, just draw points
            for vertex in vertices_2d:
                x, y = int(vertex[0]), int(vertex[1])
                if 0 <= x < size[0] and 0 <= y < size[1]:
                    draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(100, 100, 100, 255))

        # Save the image
        img.save(abs_thumbnail_path, 'PNG')

        file_size = os.path.getsize(abs_thumbnail_path)
        logger.info(f"Thumbnail generated: {abs_thumbnail_path} ({file_size} bytes)")
    except Exception as e:
        logger.error(f"Error generating thumbnail: {e}", exc_info=True)

        # Fallback: Create a simple placeholder thumbnail
        try:
            logger.info("Creating fallback placeholder thumbnail")
            img = Image.new('RGBA', size, (240, 240, 240, 255))
            draw = ImageDraw.Draw(img)

            # Draw a simple 3D box icon
            box_color = (100, 100, 100, 255)
            # Front face
            draw.polygon([(64, 96), (192, 96), (192, 224), (64, 224)], fill=box_color, outline=(50, 50, 50))
            # Top face
            draw.polygon([(64, 96), (128, 64), (256, 64), (192, 96)], fill=(150, 150, 150, 255), outline=(50, 50, 50))
            # Right face
            draw.polygon([(192, 96), (256, 64), (256, 192), (192, 224)], fill=(120, 120, 120, 255),
                         outline=(50, 50, 50))

            img.save(abs_thumbnail_path, 'PNG')
            logger.info(f"Fallback thumbnail created: {abs_thumbnail_path}")
        except Exception as fallback_error:
            logger.error(f"Failed to create fallback thumbnail: {fallback_error}")
            return
    patent.thumbnail_path = thumbnail_path
    patent.save()

def generate_thumbnail_async(patent, glb_file_path):
    threading.Thread(target=generate_thumbnail_from_glb, args=(patent, glb_file_path, (512, 512)), daemon=True).start()
