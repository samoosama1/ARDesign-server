from django.urls import path, include

from . import views

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path("", include("django.contrib.auth.urls")),
    path('logout_user/', views.logout_user, name='logout_user'),
]