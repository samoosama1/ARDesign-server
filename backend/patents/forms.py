import logging
import os
import stat
import zipfile

import magic
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .zipbomb import has_overlapping_entries

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 500 * 1024 * 1024       # 500MB compressed
MAX_EXTRACTED_SIZE = 1500 * 1024 * 1024   # 1.5GB total uncompressed
MAX_FILE_SIZE = MAX_EXTRACTED_SIZE        # single file can be up to the total limit
MAX_COMPRESSION_RATIO = MAX_EXTRACTED_SIZE / MAX_UPLOAD_SIZE  # 3x
MAX_ENTRY_COUNT = 50

# MIME types that are clearly not 3D model data
BLOCKED_MIME_TYPES = {
    'application/x-executable', 'application/x-dosexec', 'application/x-msdos-program',
    'application/x-sharedlib', 'application/x-pie-executable',
    'application/java-archive', 'application/x-java-class',
    'application/javascript', 'text/javascript',
    'text/html', 'text/xml', 'application/xml',
    'application/pdf',
    'application/zip', 'application/gzip', 'application/x-tar',
    'application/x-rar-compressed', 'application/x-7z-compressed',
    'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp', 'image/svg+xml',
    'audio/mpeg', 'audio/wav', 'audio/ogg',
    'video/mp4', 'video/mpeg', 'video/webm',
}


def _validate_zip_security(z, compressed_size):
    members = z.infolist()

    if len(members) > MAX_ENTRY_COUNT:
        logger.warning("ZIP rejected: %d entries exceeds limit of %d", len(members), MAX_ENTRY_COUNT)
        raise ValidationError(
            _('ZIP contains too many files (maximum %(max)d)') % {'max': MAX_ENTRY_COUNT}
        )

    total_uncompressed = 0
    for info in members:
        # Symlink check
        if stat.S_ISLNK(info.external_attr >> 16):
            logger.warning("ZIP rejected: symlink entry '%s'", info.filename)
            raise ValidationError(_('ZIP contains symbolic links'))

        # Path traversal check (defense-in-depth alongside utils.sanitize_filename)
        if '..' in info.filename or info.filename.startswith('/'):
            logger.warning("ZIP rejected: path traversal in entry '%s'", info.filename)
            raise ValidationError(_('ZIP contains path traversal attack'))

        # Per-file size check
        if info.file_size > MAX_FILE_SIZE:
            logger.warning("ZIP rejected: entry '%s' size %d exceeds limit %d", info.filename, info.file_size, MAX_FILE_SIZE)
            raise ValidationError(
                _('ZIP contains a file exceeding %(limit)s MB')
                % {'limit': MAX_FILE_SIZE // (1024 * 1024)}
            )

        total_uncompressed += info.file_size

    if total_uncompressed > MAX_EXTRACTED_SIZE:
        logger.warning("ZIP rejected: total uncompressed %d exceeds limit %d", total_uncompressed, MAX_EXTRACTED_SIZE)
        raise ValidationError(
            _('Total uncompressed size exceeds %(limit)s MB')
            % {'limit': MAX_EXTRACTED_SIZE // (1024 * 1024)}
        )

    if compressed_size > 0 and total_uncompressed / compressed_size > MAX_COMPRESSION_RATIO:
        logger.warning("ZIP rejected: compression ratio %.1f exceeds limit %.1f", total_uncompressed / compressed_size, MAX_COMPRESSION_RATIO)
        raise ValidationError(_('ZIP file failed security scan'))


class PatentUploadForm(forms.Form):
    MODEL_TYPES = {
        '.obj': 'OBJ',
        '.stl': 'STL',
        '.stp': 'STP',
        '.iges': 'IGES',
        '.glb': 'GLB',
    }

    patent_file = forms.FileField(
        allow_empty_file=False,
        help_text=_('Upload a ZIP file containing your patent model files.')
    )

    def clean_patent_file(self):
        file = self.cleaned_data.get('patent_file')
        if not file:
            raise ValidationError(_('No file uploaded'))

        if file.size > MAX_UPLOAD_SIZE:
            raise ValidationError(
                _('File size cannot exceed %(limit)s MB')
                % {'limit': MAX_UPLOAD_SIZE // (1024 * 1024)}
            )

        ext = os.path.splitext(file.name)[1].lower()
        if ext != '.zip':
            raise ValidationError(_('Only ZIP files are allowed. Please compress your model files into a ZIP archive.'))

        # Overlapping entry detection (catches zip bombs that bypass ratio checks)
        file.seek(0)
        result = has_overlapping_entries(file)
        if result is True:
            logger.warning("ZIP rejected: overlapping entries detected (zip bomb)")
            raise ValidationError(_('ZIP file failed security scan'))
        if result is None:
            logger.warning("ZIP rejected: could not parse structure (invalid/unsupported)")
            raise ValidationError(_('Invalid or corrupted ZIP file'))

        file.seek(0)
        try:
            with zipfile.ZipFile(file) as z:
                # Structural security checks
                _validate_zip_security(z, file.size)

                # Model file identification
                model_files = {ext: [] for ext in self.MODEL_TYPES.keys()}
                mtl_files = []

                for filename in z.namelist():
                    if filename.endswith('/'):
                        continue

                    file_ext = os.path.splitext(filename)[1].lower()

                    if file_ext in model_files:
                        model_files[file_ext].append(filename)
                    elif file_ext == '.mtl':
                        mtl_files.append(filename)

                model_type = None
                model_filename = None
                for ext, files in model_files.items():
                    if files:
                        if model_type is not None:
                            raise ValidationError(_('ZIP must contain exactly one model file (.obj, .stl, .stp, or .iges)'))
                        model_type = self.MODEL_TYPES[ext]
                        model_filename = files[0]

                if model_type is None:
                    raise ValidationError(_('ZIP must contain exactly one model file (.obj, .stl, .stp, or .iges)'))

                if model_type == 'OBJ':
                    if len(mtl_files) != 1:
                        raise ValidationError(_('OBJ files must be accompanied by exactly one MTL file'))

                # Content validation: reject known-bad MIME types
                with z.open(model_filename) as model_file:
                    header = model_file.read(2048)
                    mime_type = magic.from_buffer(header, mime=True)
                    if mime_type in BLOCKED_MIME_TYPES:
                        logger.warning("ZIP rejected: model file '%s' has blocked MIME type '%s'", model_filename, mime_type)
                        raise ValidationError(
                            _('File content does not match expected model format (detected: %(mime)s)')
                            % {'mime': mime_type}
                        )

            file.seek(0)
            return file, model_type, model_filename

        except zipfile.BadZipFile:
            raise ValidationError(_('Invalid or corrupted ZIP file'))
