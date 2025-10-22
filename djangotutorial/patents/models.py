import os
import zipfile
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils.text import slugify
from datetime import datetime


def get_upload_path(instance, filename):
    """
    Generate the upload path for patent files.
    Creates a path structure: patents/user_id/file_type/timestamp/filename
    """
    # Get file extension and determine file type
    ext = os.path.splitext(filename)[1].lower()
    file_type = 'misc'
    if ext in ['.obj', '.stl', '.stp', '.iges']:
        file_type = ext[1:]  # Remove the dot
    elif ext == '.zip':
        file_type = 'zip'

    # Create timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Generate path
    return os.path.join(
        'patents',
        str(instance.user.id),
        file_type,
        timestamp,
        filename
    )


def validate_patent_file(file):
    """Validate uploaded patent files"""
    ext = os.path.splitext(file.name)[1].lower()
    allowed_extensions = ['.obj', '.stl', '.stp', '.iges', '.zip']

    if ext not in allowed_extensions:
        raise ValidationError(
            f'Unsupported file type. Allowed types are: {", ".join(allowed_extensions)}'
        )

    if ext == '.zip':
        try:
            with zipfile.ZipFile(file) as z:
                has_valid_file = False
                has_obj = False
                for filename in z.namelist():
                    file_ext = os.path.splitext(filename)[1].lower()
                    if file_ext == '.obj':
                        has_obj = True
                        has_valid_file = True
                        break
                    elif file_ext in ['.stl', '.stp', '.iges']:
                        has_valid_file = True
                        break

                if not has_valid_file:
                    raise ValidationError('ZIP file must contain at least one valid 3D model file')

                if has_obj:
                    has_mtl = any(filename.lower().endswith('.mtl') for filename in z.namelist())
                    if not has_mtl:
                        raise ValidationError('ZIP file with OBJ must include an MTL file')

        except zipfile.BadZipFile:
            raise ValidationError('Invalid ZIP file')


class Patent(models.Model):
    FILE_TYPES = [
        ('OBJ', 'Wavefront OBJ'),
        ('STL', 'Stereolithography'),
        ('STP', 'STEP File'),
        ('IGES', 'IGES File'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # patent_file = models.FileField(
    #    upload_to=get_upload_path,
    #    validators=[validate_patent_file],
    #    storage=default_storage,
    #    help_text='Upload a 3D model file (.obj, .stl, .stp, .iges) or a ZIP containing an OBJ with its MTL and texture files'
    # )
    storage_path = models.CharField(
        max_length=255,
        null = True,  # <-- Add this
        blank = True,  # <-- Add this (good for admin)
        help_text='folder containing model files',
    )

    file_type = models.CharField(
        max_length=4,
        choices=FILE_TYPES,
        null=True,
        help_text='Type of the 3D model file'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Store related files (for OBJ+MTL or extracted ZIP contents)
    related_files = models.JSONField(
        null=True,
        blank=True,
        help_text='Paths to related files (MTL, textures, etc.)'
    )

    def __str__(self):
        return f"Patent {self.id} by {self.user.username}"

    #def clean(self):
    #    super().clean()
    #    if self.patent_file:
    #        if self.patent_file.size > 100 * 1024 * 1024:  # 100MB
    #            raise ValidationError('File size cannot exceed 100MB')
#
    #def save(self, *args, **kwargs):
    #    # For new records, process the file
    #    if not self.pk and self.patent_file:
    #        ext = os.path.splitext(self.patent_file.name)[1].lower()
#
    #        # Set file type based on extension
    #        ext_to_type = {
    #            '.obj': 'OBJ',
    #            '.stl': 'STL',
    #            '.stp': 'STP',
    #            '.iges': 'IGES'
    #        }
#
    #        if ext != '.zip':
    #            self.file_type = ext_to_type.get(ext)
#
    #    super().save(*args, **kwargs)
