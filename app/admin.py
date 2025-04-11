from django.contrib import admin
from .models import Usage

@admin.register(Usage)
class UsageAdmin(admin.ModelAdmin):
    list_display = ('id', 'price', 'total_bytes', 'total_token', 'number_of_languages', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('price', 'total_bytes', 'total_token', 'number_of_languages')
    ordering = ('-created_at',)