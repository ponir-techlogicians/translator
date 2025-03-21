from django.urls import path
from .views import file_translate

urlpatterns = [
    path('translate/', file_translate, name='file-translate'),
]