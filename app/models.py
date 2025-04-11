from django.db import models

# Create your models here.
class Usage(models.Model):
    price = models.FloatField()
    total_bytes = models.IntegerField()
    total_token = models.IntegerField(null=True)
    number_of_languages = models.IntegerField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

