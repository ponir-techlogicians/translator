from django.urls import path
from .views import file_translate, price_estimate, create_payment_intent, translation_status, home, translation

urlpatterns = [
    path('', home, name='file-translate-home'),
    path('translation',translation,name="file-translation")
]