import os
import subprocess

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.shortcuts import render, redirect
from django.views import View

from mysite.settings import MEDIA_ROOT
from .forms import PatentUploadForm
from .models import Patent  # Add the Patent model import
# Create your views here.
from django.contrib.auth.decorators import login_required

import logging

logger = logging.getLogger(__name__)


@login_required(login_url='login')
def index(request):
    patents = Patent.objects.all().order_by('-uploaded_at')
    form = PatentUploadForm()
    context = {
        'patents': patents,
        'form': form,
    }
    return render(request, 'index.html', context=context)


from .utils import handle_uploaded_file, get_storage_path


class UploadPatentView(LoginRequiredMixin, View):
    def post(self, request):
        form = PatentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Get the validated data from the form
                uploaded_file, model_type, model_filename = form.cleaned_data['patent_file']

                # Handle file upload and get file type and related files
                # This function (handle_uploaded_file) already saves the files
                file_type, base_path, stored_files = handle_uploaded_file(
                    uploaded_file,
                    request.user.id,
                    model_type,
                    model_filename
                )

                # 1. Create the Patent object
                patent = Patent.objects.create(
                    user=request.user,
                    storage_path=base_path,
                    file_type=file_type,
                    related_files=stored_files
                )

                # --- START CONVERSION ---

                # 2. Find the relative path of the main model file
                try:
                    main_file_rel_path = [p for p in stored_files if p.endswith(patent.file_type.lower())][0]
                except IndexError:
                    raise ValueError("Could not determine file path for converter.")

                # 3. Define paths FOR THE CONTAINERS
                # Both containers see the file at '/data/...'
                input_file_path_in_container = MEDIA_ROOT + '/' + main_file_rel_path

                # glb_filename = f"{os.path.splitext(model_filename)[0]}.glb"
                # glb_rel_path = get_storage_path(base_path, glb_filename)
                output_file_path = MEDIA_ROOT + '/' + base_path

                # 4. Build the Docker command
                # command = [
                #     'pkill Xvfb || true && '
                #     'rm -f /tmp/.X99-lock && rm -rf /tmp/.X11-unix/X99 && '
                #     'Xvfb :99 -screen 0 1024x768x24 & '
                #     'export DISPLAY=:99 && '
                #     '/app/converter/venv/bin/python3 /app/converter/main.py '
                #     f'{input_file_path_in_container}'
                # ]

                command = ['xvfb-run', '-a', '/app/converter/venv/bin/python3.11',
                           '/app/converter/main.py',
                           f'{input_file_path_in_container}']
                # 5. Execute the command
                result = subprocess.run(command, cwd=output_file_path, capture_output=True, text=True)

                if result.returncode == 0:
                    # 6. Success! Add the new GLB file to the patent's file list
                    logger.debug(f"Successfully converted file to glb, path is: {output_file_path}")
                    try:
                        patent.related_files.append(output_file_path + '/' + 'out.glb')
                        patent.save()
                    except Exception as e:
                        form.add_error(None, f"Failed to save glb file to storage at path: {output_file_path}")
                else:
                    # 7. Failure: Log the error
                    print(f"GLB Conversion Failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
                    form.add_error(None, f"File saved, but GLB conversion failed. {result.stderr[:100]}")

                # --- END CONVERSION ---

                if result.returncode == 0:
                    return redirect('home')
            except Exception as e:
                form.add_error(None, f"An unexpected error occurred: {e}")

        # Re-render page if form is invalid or conversion failed
        patents = Patent.objects.all().order_by('-uploaded_at')
        context = {
            'patents': patents,
            'form': form,
        }
        return render(request, 'index.html', context=context)

