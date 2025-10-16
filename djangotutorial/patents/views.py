from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from patents.models import Patent
from users.forms import CustomUserCreationForm
from users.models import User
from .serializers import PatentUploadSerializer


# Create your views here.
def index(request):
    context = {}
    return render(request, 'index.html', context=context)

class UploadPatentView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = PatentUploadSerializer
    permission_classes = [IsAuthenticated] # Add this line

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def signup(request):
    """
    Handles user registration. On a POST request, it validates the form and
    creates a new user, then logs them in. On a GET request, it displays
    a blank registration form.
    """
    if request.method == 'POST':
        # If the form is submitted...
        form = CustomUserCreationForm(request.POST) # Use the custom form
        if form.is_valid():
            # If the form data is valid, save the user
            user = form.save()
            # Log the user in automatically
            login(request, user)
            # Redirect to the homepage (you named this 'index' in your patents/urls.py)
            return redirect('index')
    else:
        # If it's a GET request (user just visiting the page), create a blank form
        form = CustomUserCreationForm() # Use the custom form

    # Render the signup page with the form
    return render(request, 'registration/signup.html', {'form': form})
