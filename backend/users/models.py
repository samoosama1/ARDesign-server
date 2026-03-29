from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.
class User(AbstractUser):
    date_of_birth = models.DateField(null=True, blank=True)
