from django.urls import path

from patents import views
from patents.views import ServeQRCodeView

urlpatterns = [
    path('upload-patent/', views.UploadPatentView.as_view(), name='upload-patent'),
    path('', views.index, name='index'),
    path('download-model/<int:patent_id>/', ServeQRCodeView.as_view(), name= 'download-model'),
]