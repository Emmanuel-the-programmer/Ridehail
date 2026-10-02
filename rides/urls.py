from django.urls import path

from .views import (
    AcceptRideView,
    ConfirmCashPaymentView,
    DriverLocationView,
    DriverRideStatusView,
    NearbyRideListView,
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
    path("driver/location/", DriverLocationView.as_view(), name="driver-location"),
    path("driver/rides/", NearbyRideListView.as_view(), name="nearby-rides"),
    path("driver/rides/<uuid:id>/accept/", AcceptRideView.as_view(), name="accept-ride"),
    path(
        "driver/rides/<uuid:id>/status/",
        DriverRideStatusView.as_view(),
        name="driver-ride-status",
    ),
    path(
        "driver/rides/<uuid:id>/cash-payment/confirm/",
        ConfirmCashPaymentView.as_view(),
        name="confirm-cash-payment",
    ),
    path("rides/", RideRequestCreateView.as_view(), name="ride-request-create"),
    path("rides/<uuid:id>/", RideRequestDetailView.as_view(), name="ride-request-detail"),
]
