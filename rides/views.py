from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RideRequest
from .serializers import RideRequestSerializer, RiderRegistrationSerializer


User = get_user_model()


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
        serializer.save(rider=self.request.user)


class RideRequestDetailView(generics.RetrieveAPIView):
    queryset = RideRequest.objects.all()
    serializer_class = RideRequestSerializer
    lookup_field = "id"

    def get_queryset(self):
        return self.queryset.filter(rider=self.request.user)
