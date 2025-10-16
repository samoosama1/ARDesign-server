from django.db import models
from django.conf import settings

class Patent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    patent_file = models.FileField(upload_to='patents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Patent {self.id} by {self.user.username}"
