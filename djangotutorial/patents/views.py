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

        output_file_path, result = convert_to_glb(base_path, main_file_rel_path)

        if result.returncode == 0:
            logger.debug(f"Successfully converted file to glb, path is: {output_file_path}")
            patent.related_files.append(output_file_path + '/' + 'out.glb')
            patent.save()
            return redirect('home')
        else:
            logger.debug(f"Failed to convert file to glb, path is: {output_file_path}")
            form.add_error(None, f"File saved, but GLB conversion failed. {result.stderr[:100]}")

    except Exception as e:
        form.add_error(None, f"An unexpected error occurred: {e}")

def convert_to_glb(base_path, main_file_rel_path):
    input_file_path_in_container = MEDIA_ROOT + '/' + main_file_rel_path
    output_file_path = MEDIA_ROOT + '/' + base_path
    command = ['xvfb-run', '-a', '/app/converter/venv/bin/python3.11',
               '/app/converter/main.py',
               f'{input_file_path_in_container}']

    result = subprocess.run(command, cwd=output_file_path, capture_output=True, text=True)
    return output_file_path, result

class UploadPatentView(LoginRequiredMixin, View):
    def post(self, request):
        form = PatentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            save_patent_and_convert(form, request)


        patents = Patent.objects.all().order_by('-uploaded_at')
        context = {
            'patents': patents,
            'form': form,
        }

        return render(request, 'index.html', context=context)