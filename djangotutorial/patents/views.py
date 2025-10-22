from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from .forms import PatentUploadForm
from .models import Patent  # Add the Patent model import


# Create your views here.
from django.contrib.auth.decorators import login_required

@login_required(login_url='login')
def index(request):
    patents = Patent.objects.all().order_by('-uploaded_at')
    form = PatentUploadForm()
    context = {
        'patents': patents,
        'form': form,
    }
    return render(request, 'index.html', context=context)

from .utils import handle_uploaded_file

class UploadPatentView(LoginRequiredMixin, View):
    def post(self, request):
        form = PatentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Get the validated data from the form
                uploaded_file, model_type, model_filename = form.cleaned_data['patent_file']
                # Handle file upload and get file type and related files
                file_type, base_path, stored_files = handle_uploaded_file(
                    uploaded_file,
                    request.user.id,
                    model_type,
                    model_filename
                )
                Patent.objects.create(
                    user=request.user,
                    storage_path=base_path,
                    file_type=file_type,
                    related_files=stored_files
                )
                return redirect('home')
            except ValueError as e:
                form.add_error('patent_file', str(e))
        patents = Patent.objects.all().order_by('-uploaded_at')
        context = {
            'patents': patents,
            'form': form,
        }
        return render(request, 'index.html', context=context)


