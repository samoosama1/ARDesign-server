from django.urls import path

from patents import views

urlpatterns = [
    path('upload-patent', views.UploadPatentView.as_view(), name='upload-patent'),
    path('', views.index, name='index'),
]