import os
import subprocess

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, FileResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View

from django.conf import settings
from .forms import PatentUploadForm, MAX_UPLOAD_SIZE
from .models import Patent
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext as _

import logging

logger = logging.getLogger(__name__)


@login_required(login_url='login')
def index(request):
    patents = Patent.objects.all().order_by('-uploaded_at')
    form = PatentUploadForm()
    context = {
        'patents': patents,
        'form': form,
        'MEDIA_URL': settings.MEDIA_URL,
        'MAX_UPLOAD_SIZE_MB': MAX_UPLOAD_SIZE // (1024 * 1024),
        'MAX_UPLOAD_SIZE_BYTES': MAX_UPLOAD_SIZE,
    }
    return render(request, 'index.html', context=context)


from .utils import handle_uploaded_file, delete_directory


def save_patent_and_convert(form, request):
    try:
        uploaded_file, model_type, model_filename = form.cleaned_data['patent_file']
        logger.info(f"uploaded_file {uploaded_file.name}, model_type {model_type}, model_filename {model_filename}")
        file_type, base_path, stored_files = handle_uploaded_file(
            uploaded_file,
            request.user.id,
            model_type,
            model_filename
        )
        logger.info(f"creating patent record with user {request.user.id}, storage_path {base_path}, file_type {file_type}, stored_files {stored_files}")
        patent = Patent.objects.create(
            user=request.user,
            storage_path=base_path,
            file_type=file_type,
            related_files=stored_files,
            model_filename=os.path.splitext(model_filename)[0],
        )

        try:
            main_file_rel_path = [p for p in stored_files if p.endswith(patent.file_type.lower())][0]
        except IndexError:
            raise ValueError("Could not determine file path for converter.")

        if main_file_rel_path.endswith('.glb'):
            patent.glb_file_path = main_file_rel_path
            patent.save()
            logger.info(f"Uploaded file is already a GLB, skipping conversion. GLB path: {main_file_rel_path}")
            return patent, main_file_rel_path

        output_folder, result = convert_to_glb(base_path, main_file_rel_path)

        if result.returncode == 0:
            logger.info(f"conversion success, output: {result.stdout}")
            glb_file_path = base_path + '/' + 'out.glb'
            return patent, glb_file_path

        # conversion failed, delete patent record, remove folder.
        patent.delete()
        delete_directory(output_folder)
        logger.error(f"Failed to convert file to glb, deleted folder: {output_folder}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    return None, None

def convert_to_glb(base_path, main_file_rel_path):
    input_file_path_in_container = settings.MEDIA_ROOT + '/' + main_file_rel_path
    output_folder = settings.MEDIA_ROOT + '/' + base_path
    command = ['xvfb-run', '-a', '/app/converter/venv/bin/python3.11',
               '/app/converter/main.py',
               f'{input_file_path_in_container}']

    result = subprocess.run(command, cwd=output_folder, capture_output=True, text=True)
    return output_folder, result

class UploadPatentView(LoginRequiredMixin, View):
    def get(self, request):
        patents = Patent.objects.all().order_by('-uploaded_at')
        context = {
            'patents': patents,
            'form': PatentUploadForm(),
            'MEDIA_URL': settings.MEDIA_URL,
            'MAX_UPLOAD_SIZE_MB': MAX_UPLOAD_SIZE // (1024 * 1024),
            'MAX_UPLOAD_SIZE_BYTES': MAX_UPLOAD_SIZE,
        }
        return render(request, 'index.html', context=context)

    def post(self, request):
        form = PatentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            logger.info(f"calling save_patent_and_convert")
            patent, glb_file_path = save_patent_and_convert(form, request)

            if patent and glb_file_path:
                logger.info(f"Successfully converted file to glb, path is: {glb_file_path}")
                patent.related_files.append(glb_file_path)
                patent.glb_file_path = glb_file_path
                patent.save()
            else:
                logger.error("Patent saving and conversion failed.")

        return redirect(reverse('index'))

class ServeQRCodeView(View):
    def get(self, request, patent_id):
        try:
            patent = Patent.objects.get(id=patent_id)
        except Patent.DoesNotExist:
            return HttpResponse(_("Patent not found"), status=404)
        abs_path = os.path.join(settings.MEDIA_ROOT, patent.glb_file_path)
        logger.info(f"Serving glb file for patent id: {patent_id}")
        if not os.path.exists(abs_path):
            logger.error(f"glb_file_path does not exist: {abs_path}")
            return HttpResponse(_("GLB file not found"), status=404)
        logger.info("file exists, preparing response")
        response = FileResponse(open(abs_path, 'rb'), content_type='model/gltf-binary')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(abs_path)}"'
        return response