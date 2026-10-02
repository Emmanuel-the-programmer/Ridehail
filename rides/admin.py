from django.contrib import admin

from .models import DriverProfile, RideRequest


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_approved", "is_available", "vehicle_description", "updated_at")
    list_filter = ("is_approved", "is_available")
    search_fields = ("user__username", "vehicle_description")
    readonly_fields = ("updated_at",)


@admin.register(RideRequest)
class RideRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "rider",
        "driver",
        "pickup_address",
        "destination_address",
        "status",
        "payment_method",
        "payment_status",
        "created_at",
    )
    list_filter = ("status", "payment_method", "payment_status", "created_at")
    search_fields = (
        "id",
        "rider__username",
        "driver__username",
        "pickup_address",
        "destination_address",
    )
    readonly_fields = ("id", "created_at", "updated_at")
