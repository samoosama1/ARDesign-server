import os
import subprocess

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.api import success
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.shortcuts import render, redirect
from django.utils.termcolors import background
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


from .utils import handle_uploaded_file, get_storage_path, delete_directory


def save_patent_and_convert(form, request):
    try:
        uploaded_file, model_type, model_filename = form.cleaned_data['patent_file']

        file_type, base_path, stored_files = handle_uploaded_file(
            uploaded_file,
            request.user.id,
            model_type,
            model_filename
        )

        patent = Patent.objects.create(
            user=request.user,
            storage_path=base_path,
            file_type=file_type,
            related_files=stored_files
        )

        try:
            main_file_rel_path = [p for p in stored_files if p.endswith(patent.file_type.lower())][0]
        except IndexError:
            raise ValueError("Could not determine file path for converter.")

        output_folder, result = convert_to_glb(base_path, main_file_rel_path)

        if result.returncode == 0:
            glb_file_path = output_folder + '/' + 'out.glb'
            return patent, glb_file_path
        # conversion failed, delete patent record, remove folder.
        patent.delete()
        delete_directory(base_path)

        logger.debug(f"Failed to convert file to glb, path is: {output_folder}")
        form.add_error(None, f"File saved, but GLB conversion failed. {result.stderr[:100]}")

    except Exception as e:
        form.add_error(None, f"An unexpected error occurred: {e}")
    return None, None

def convert_to_glb(base_path, main_file_rel_path):
    input_file_path_in_container = MEDIA_ROOT + '/' + main_file_rel_path
    output_folder = MEDIA_ROOT + '/' + base_path
    command = ['xvfb-run', '-a', '/app/converter/venv/bin/python3.11',
               '/app/converter/main.py',
               f'{input_file_path_in_container}']

    result = subprocess.run(command, cwd=output_folder, capture_output=True, text=True)
    return output_folder, result


def generate_thumbnail_from_glb(glb_file_path):
    """
    Executes the separate thumbnail script using the friend's Blender-enabled venv.

    Args:
        glb_file_path (str): Absolute path to the generated 'out.glb'.
    """

    command = ['xvfb-run', '-a', '/app/converter/venv/bin/python3.11',
               '/app/thumbnail_generator/generator.py',
               f'{glb_file_path}']


    print(f"Executing thumbnail command: {' '.join(command)}")

    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )

        # Calculate expected output path
        base_name = os.path.splitext(glb_file_path)[0]
        thumbnail_path = f"{base_name}_thumb.png"

        print(f"Thumbnail created successfully at: {thumbnail_path}")
        return thumbnail_path

    except subprocess.CalledProcessError as e:
        print("--- THUMBNAIL GENERATION FAILED ---")
        print(f"Error executing thumbnail script. STDERR:\n{e.stderr}")
        return None

class UploadPatentView(LoginRequiredMixin, View):
    def post(self, request):
        form = PatentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            patent, glb_file_path = save_patent_and_convert(form, request)
            thumbnail_path = None
            if patent:
                logger.debug(f"Successfully converted file to glb, path is: {os.path.dirname(glb_file_path)}")
                patent.related_files.append(glb_file_path)
                patent.save()
                thumbnail_path = generate_thumbnail_from_glb(glb_file_path)
            else:
                logger.debug("Patent saving and conversion failed.")
            if thumbnail_path:
                logger.debug(f"Successfully generated thumbnail at: {thumbnail_path}")
                patent.related_files.append(thumbnail_path)
                patent.save()
            else:
                logger.debug("Thumbnail generation failed.")

        patents = Patent.objects.all().order_by('-uploaded_at')
        context = {
            'patents': patents,
            'form': form,
        }

        return render(request, 'index.html', context=context)