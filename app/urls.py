from django.urls import path
from .views import file_translate, price_estimate, create_payment_intent

urlpatterns = [
    path('translate/', file_translate, name='file-translate'),
    path('price-estimate/', price_estimate, name='price-estimate'),
    path('create-payment-intent/', create_payment_intent, name='create-payment-intent'),
]