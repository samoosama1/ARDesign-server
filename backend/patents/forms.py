import os
import zipfile
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

class PatentUploadForm(forms.Form):
    MODEL_TYPES = {
        '.obj': 'OBJ',
        '.stl': 'STL',
        '.stp': 'STP',
        '.iges': 'IGES',
        '.glb' : 'GLB'
    }

    patent_file = forms.FileField(
        allow_empty_file=False,
        help_text=_('Upload a ZIP file containing your patent model files.')
    )

    def clean_patent_file(self):
        """
        Validates the uploaded file and returns a tuple of:
        (file, model_type, model_filename)
        """
        file = self.cleaned_data.get('patent_file')
        if not file:
            raise ValidationError(_('No file uploaded'))

        if file.size > 500 * 1024 * 1024:
            raise ValidationError(_('File size cannot exceed 500MB'))

        ext = os.path.splitext(file.name)[1].lower()
        if ext != '.zip':
            raise ValidationError(_('Only ZIP files are allowed. Please compress your model files into a ZIP archive.'))

        try:
            with zipfile.ZipFile(file) as z:
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

            file.seek(0)
            return file, model_type, model_filename

        except zipfile.BadZipFile:
            raise ValidationError(_('Invalid or corrupted ZIP file'))

