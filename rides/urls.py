from django.urls import path

from .views import (
    RiderLoginView,
    RiderLogoutView,
    RiderRegistrationView,
    RideRequestCreateView,
    RideRequestDetailView,
)


urlpatterns = [
    path("auth/register/", RiderRegistrationView.as_view(), name="rider-register"),
    path("auth/login/", RiderLoginView.as_view(), name="rider-login"),
    path("auth/logout/", RiderLogoutView.as_view(), name="rider-logout"),
    path("rides/", RideRequestCreateView.as_view(), name="ride-request-create"),
    path("rides/<uuid:id>/", RideRequestDetailView.as_view(), name="ride-request-detail"),
]
