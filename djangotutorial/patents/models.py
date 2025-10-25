from django.db import models
from django.conf import settings

class Patent(models.Model):
    FILE_TYPES = [
        ('OBJ', 'Wavefront OBJ'),
        ('STL', 'Stereolithography'),
        ('STP', 'STEP File'),
        ('IGES', 'IGES File'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    storage_path = models.CharField(
        max_length=255,
        null = True,
        blank = True,
        help_text='folder containing model files',
    )

    file_type = models.CharField(
        max_length=4,
        choices=FILE_TYPES,
        null=True,
        help_text='Type of the 3D model file'
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    related_files = models.JSONField(
        null=True,
        blank=True,
        help_text='Paths to related files (MTL, textures, etc.)'
    )

    def __str__(self):
        return f"Patent {self.id} by {self.user.username}"