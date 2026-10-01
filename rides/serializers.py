from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework.authtoken.models import Token
from rest_framework import serializers

from .models import RideRequest


User = get_user_model()


class RiderRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    token = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "token")
        read_only_fields = ("id", "token")
        extra_kwargs = {
            "email": {"required": False, "allow_blank": True},
        }

    def validate_password(self, value):
        validate_password(
            value,
            user=User(
                username=self.initial_data.get("username", ""),
                email=self.initial_data.get("email", ""),
            ),
        )
        return value

    @transaction.atomic
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        Token.objects.create(user=user)
        return user

    def get_token(self, user):
        return user.auth_token.key


class RideRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = RideRequest
        fields = (
            "id",
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "destination_address",
            "destination_latitude",
            "destination_longitude",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "status", "created_at", "updated_at")

    def validate(self, attrs):
        for field in (
            "pickup_latitude",
            "destination_latitude",
        ):
            if not -90 <= attrs[field] <= 90:
                raise serializers.ValidationError({field: "Latitude must be between -90 and 90."})

        for field in (
            "pickup_longitude",
            "destination_longitude",
        ):
            if not -180 <= attrs[field] <= 180:
                raise serializers.ValidationError(
                    {field: "Longitude must be between -180 and 180."}
                )

        return attrs
