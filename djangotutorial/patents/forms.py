import os
import zipfile
from django import forms
from django.core.exceptions import ValidationError

class PatentUploadForm(forms.Form):
    # Map of file extensions to their type names
    MODEL_TYPES = {
        '.obj': 'OBJ',
        '.stl': 'STL',
        '.stp': 'STP',
        '.iges': 'IGES'
    }

    patent_file = forms.FileField(
        allow_empty_file=False,
        help_text='Upload a ZIP file containing your patent model files.'
    )

    def clean_patent_file(self):
        """
        Validates the uploaded file and returns a tuple of:
        (file, model_type, model_filename)
        """
        file = self.cleaned_data.get('patent_file')
        if not file:
            raise ValidationError('No file uploaded')

        # File size validation (500MB limit)
        if file.size > 500 * 1024 * 1024:
            raise ValidationError('File size cannot exceed 500MB')

        # Check file extension
        ext = os.path.splitext(file.name)[1].lower()
        if ext != '.zip':
            raise ValidationError('Only ZIP files are allowed. Please compress your model files into a ZIP archive.')

        # Validate ZIP contents
        try:
            with zipfile.ZipFile(file) as z:
                # Track files by extension
                model_files = {ext: [] for ext in self.MODEL_TYPES.keys()}
                mtl_files = []

                for filename in z.namelist():
                    if filename.endswith('/'):  # Skip directories
                        continue
                    
                    file_ext = os.path.splitext(filename)[1].lower()
                    
                    # Track model files
                    if file_ext in model_files:
                        model_files[file_ext].append(filename)
                    # Track MTL files
                    elif file_ext == '.mtl':
                        mtl_files.append(filename)

                # Find the model file
                model_type = None
                model_filename = None
                for ext, files in model_files.items():
                    if files:
                        if model_type is not None:  # Already found a model file
                            raise ValidationError('ZIP must contain exactly one model file (.obj, .stl, .stp, or .iges)')
                        model_type = self.MODEL_TYPES[ext]
                        model_filename = files[0]

                if model_type is None:
                    raise ValidationError('ZIP must contain exactly one model file (.obj, .stl, .stp, or .iges)')

                # Validate MTL requirement for OBJ files
                if model_type == 'OBJ':
                    if len(mtl_files) != 1:
                        raise ValidationError('OBJ files must be accompanied by exactly one MTL file')

            # Reset file pointer for later use
            file.seek(0)
            return file, model_type, model_filename

        except zipfile.BadZipFile:
            raise ValidationError('Invalid or corrupted ZIP file')

