from django.contrib import admin

from .models import RideRequest


@admin.register(RideRequest)
class RideRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "rider", "pickup_address", "destination_address", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "rider__username", "pickup_address", "destination_address")
    readonly_fields = ("id", "created_at", "updated_at")
