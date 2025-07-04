"""
URL configuration for multilang project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns

from app.views import file_translate, price_estimate, translation_status, create_payment_intent

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    # path('', lambda request: redirect('file-translate'), name='home'),
    path('admin/', admin.site.urls),
    path('translate/', file_translate, name='file-translate'),
    path('price-estimate/', price_estimate, name='price-estimate'),

    path("translation-status/<str:task_id>/", translation_status, name="translation_status"),
    path('create-payment-intent/', create_payment_intent, name='create-payment-intent'),
    # path('', include('app.urls')),
]
urlpatterns += i18n_patterns(
   # URLs that should be translated
   path('', include('app.urls')),
)

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
