from django.http import HttpResponse
from django.contrib.auth import login, logout
from users.forms import CustomUserCreationForm
from django.shortcuts import render, redirect



def signup(request):
    """
    Handles user registration. On a POST request, it validates the form and
    creates a new user, then logs them in. On a GET request, it displays
    a blank registration form.
    """
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')  # Redirect to the main patents page
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

def logout_user(request):
    if request.method == 'POST':
        logout(request)
    return redirect('login')

