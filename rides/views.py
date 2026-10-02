import math

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DriverProfile, RideRequest
from .realtime import broadcast_ride_update
from .serializers import (
    DriverLocationSerializer,
    RideRequestSerializer,
    RideStatusSerializer,
    RiderRegistrationSerializer,
)


User = get_user_model()
MATCH_RADIUS_KM = 10
EARTH_RADIUS_KM = 6371


class IsApprovedDriver(BasePermission):
    def has_permission(self, request, view):
        try:
            return request.user.driver_profile.is_approved
        except DriverProfile.DoesNotExist:
            return False


def distance_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    lat_delta = lat2 - lat1
    lon_delta = lon2 - lon1
    haversine = (
        math.sin(lat_delta / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(lon_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1, haversine)))


class RiderRegistrationView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RiderRegistrationSerializer
    permission_classes = (AllowAny,)


class RiderLoginView(ObtainAuthToken):
    permission_classes = (AllowAny,)


class RiderLogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=204)


class RideRequestCreateView(generics.CreateAPIView):
    queryset = RideRequest.objects.all()
    serializer_class = RideRequestSerializer

    def get_queryset(self):
        return self.queryset.filter(rider=self.request.user)

    def perform_create(self, serializer):
        ride = serializer.save(rider=self.request.user)
        transaction.on_commit(lambda: broadcast_ride_update(ride.id))


class RideRequestDetailView(generics.RetrieveAPIView):
    queryset = RideRequest.objects.select_related("driver")
    serializer_class = RideRequestSerializer
    lookup_field = "id"

    def get_queryset(self):
        return self.queryset.filter(rider=self.request.user)


class DriverLocationView(APIView):
    permission_classes = (IsAuthenticated, IsApprovedDriver)

    def post(self, request):
        serializer = DriverLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = request.user.driver_profile
        if serializer.validated_data["is_available"] and RideRequest.objects.filter(
            driver=request.user,
            status__in=(
                RideRequest.Status.ACCEPTED,
                RideRequest.Status.DRIVER_ARRIVING,
                RideRequest.Status.ARRIVED,
                RideRequest.Status.IN_PROGRESS,
            ),
        ).exists():
            raise ValidationError({"is_available": "Complete your active ride before going online."})
        profile.latitude = serializer.validated_data["latitude"]
        profile.longitude = serializer.validated_data["longitude"]
        profile.is_available = serializer.validated_data["is_available"]
        profile.save(update_fields=("latitude", "longitude", "is_available", "updated_at"))
        return Response(
            {
                "latitude": profile.latitude,
                "longitude": profile.longitude,
                "is_available": profile.is_available,
            }
        )


class NearbyRideListView(APIView):
    permission_classes = (IsAuthenticated, IsApprovedDriver)

    def get(self, request):
        profile = request.user.driver_profile
        if not profile.is_available or profile.latitude is None or profile.longitude is None:
            raise ValidationError(
                {"detail": "Go online and share your location to see nearby rides."}
            )

        latitude = float(profile.latitude)
        longitude = float(profile.longitude)
        latitude_delta = MATCH_RADIUS_KM / 111
        longitude_delta = min(
            180,
            MATCH_RADIUS_KM / (111 * max(abs(math.cos(math.radians(latitude))), 0.01)),
        )
        rides = RideRequest.objects.select_related("driver").filter(
            driver__isnull=True,
            status__in=(RideRequest.Status.REQUESTED, RideRequest.Status.MATCHING),
            pickup_latitude__gte=max(-90, latitude - latitude_delta),
            pickup_latitude__lte=min(90, latitude + latitude_delta),
        )
        if longitude_delta < 180:
            west = longitude - longitude_delta
            east = longitude + longitude_delta
            if west < -180:
                rides = rides.filter(
                    Q(pickup_longitude__gte=west + 360) | Q(pickup_longitude__lte=east)
                )
            elif east > 180:
                rides = rides.filter(
                    Q(pickup_longitude__gte=west) | Q(pickup_longitude__lte=east - 360)
                )
            else:
                rides = rides.filter(
                    pickup_longitude__gte=west,
                    pickup_longitude__lte=east,
                )

        nearby = []
        for ride in rides:
            distance = distance_km(
                latitude,
                longitude,
                float(ride.pickup_latitude),
                float(ride.pickup_longitude),
            )
            if distance <= MATCH_RADIUS_KM:
                item = RideRequestSerializer(ride).data
                item["distance_km"] = round(distance, 2)
                nearby.append(item)
        nearby.sort(key=lambda ride: ride["distance_km"])
        return Response(nearby)


class AcceptRideView(APIView):
    permission_classes = (IsAuthenticated, IsApprovedDriver)

    @transaction.atomic
    def post(self, request, id):
        try:
            ride = RideRequest.objects.select_for_update().get(id=id)
        except RideRequest.DoesNotExist:
            return Response({"detail": "Ride not found."}, status=404)

        profile = DriverProfile.objects.select_for_update().get(user=request.user)
        if not profile.is_available or profile.latitude is None or profile.longitude is None:
            raise ValidationError(
                {"detail": "Go online and share your location before accepting a ride."}
            )
        if ride.status not in (RideRequest.Status.REQUESTED, RideRequest.Status.MATCHING):
            raise ValidationError({"detail": "This ride is no longer available."})
        if ride.driver_id is not None:
            raise ValidationError({"detail": "This ride has already been accepted."})
        if distance_km(
            float(profile.latitude),
            float(profile.longitude),
            float(ride.pickup_latitude),
            float(ride.pickup_longitude),
        ) > MATCH_RADIUS_KM:
            raise ValidationError({"detail": "This ride is outside your matching radius."})
        if RideRequest.objects.filter(
            driver=request.user,
            status__in=(
                RideRequest.Status.ACCEPTED,
                RideRequest.Status.DRIVER_ARRIVING,
                RideRequest.Status.ARRIVED,
                RideRequest.Status.IN_PROGRESS,
            ),
        ).exists():
            raise ValidationError(
                {"detail": "Complete your active ride before accepting another."}
            )

        ride.driver = request.user
        ride.status = RideRequest.Status.ACCEPTED
        ride.save(update_fields=("driver", "status", "updated_at"))
        profile.is_available = False
        profile.save(update_fields=("is_available", "updated_at"))
        transaction.on_commit(lambda: broadcast_ride_update(ride.id))
        return Response(RideRequestSerializer(ride).data)


class DriverRideStatusView(APIView):
    permission_classes = (IsAuthenticated, IsApprovedDriver)
    transitions = {
        RideRequest.Status.ACCEPTED: RideRequest.Status.DRIVER_ARRIVING,
        RideRequest.Status.DRIVER_ARRIVING: RideRequest.Status.ARRIVED,
        RideRequest.Status.ARRIVED: RideRequest.Status.IN_PROGRESS,
        RideRequest.Status.IN_PROGRESS: RideRequest.Status.COMPLETED,
    }

    @transaction.atomic
    def post(self, request, id):
        serializer = RideStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ride = RideRequest.objects.select_for_update().get(id=id, driver=request.user)
        except RideRequest.DoesNotExist:
            return Response({"detail": "Ride not found."}, status=404)

        next_status = serializer.validated_data["status"]
        if self.transitions.get(ride.status) != next_status:
            raise ValidationError(
                {"status": f"Cannot change ride status from {ride.status} to {next_status}."}
            )
        ride.status = next_status
        ride.save(update_fields=("status", "updated_at"))
        if next_status == RideRequest.Status.COMPLETED:
            profile = request.user.driver_profile
            profile.is_available = False
            profile.save(update_fields=("is_available", "updated_at"))
        transaction.on_commit(lambda: broadcast_ride_update(ride.id))
        return Response(RideRequestSerializer(ride).data)


class ConfirmCashPaymentView(APIView):
    permission_classes = (IsAuthenticated, IsApprovedDriver)

    @transaction.atomic
    def post(self, request, id):
        try:
            ride = RideRequest.objects.select_for_update().get(id=id, driver=request.user)
        except RideRequest.DoesNotExist:
            return Response({"detail": "Ride not found."}, status=404)

        if ride.payment_method != RideRequest.PaymentMethod.CASH:
            raise ValidationError({"detail": "This ride does not use cash payment."})
        if ride.status != RideRequest.Status.COMPLETED:
            raise ValidationError({"detail": "Cash can only be confirmed after the ride is completed."})
        if ride.payment_status == RideRequest.PaymentStatus.PAID:
            raise ValidationError({"detail": "Cash payment has already been confirmed."})

        ride.payment_status = RideRequest.PaymentStatus.PAID
        ride.cash_paid_at = timezone.now()
        ride.save(update_fields=("payment_status", "cash_paid_at", "updated_at"))
        transaction.on_commit(lambda: broadcast_ride_update(ride.id))
        return Response(RideRequestSerializer(ride).data)
