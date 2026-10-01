from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import RideRequest


User = get_user_model()


class RideRequestApiTests(APITestCase):
    def setUp(self):
        self.rider = User.objects.create_user(username="rider", password="StrongPass123!abc")
        self.client.force_authenticate(user=self.rider)
        self.ride_data = {
            "pickup_address": "Central Station",
            "pickup_latitude": "51.507200",
            "pickup_longitude": "-0.127600",
            "destination_address": "City Airport",
            "destination_latitude": "51.470000",
            "destination_longitude": "-0.454300",
        }

    def test_create_ride_starts_in_requested_status(self):
        response = self.client.post("/api/rides/", self.ride_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], RideRequest.Status.REQUESTED)
        self.assertEqual(RideRequest.objects.count(), 1)

    def test_create_ride_rejects_out_of_range_coordinates(self):
        invalid_data = {**self.ride_data, "pickup_latitude": "91"}

        response = self.client.post("/api/rides/", invalid_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(RideRequest.objects.exists())

    def test_rider_can_retrieve_ride_status(self):
        create_response = self.client.post("/api/rides/", self.ride_data, format="json")

        response = self.client.get(f"/api/rides/{create_response.data['id']}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], create_response.data["id"])
        self.assertEqual(response.data["status"], RideRequest.Status.REQUESTED)

    def test_ride_creation_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.post("/api/rides/", self.ride_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(RideRequest.objects.exists())

    def test_rider_cannot_retrieve_another_riders_ride(self):
        create_response = self.client.post("/api/rides/", self.ride_data, format="json")
        other_rider = User.objects.create_user(
            username="other-rider",
            password="StrongPass123!abc",
        )
        self.client.force_authenticate(user=other_rider)

        response = self.client.get(f"/api/rides/{create_response.data['id']}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_registration_creates_user_and_returns_token(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "new-rider",
                "email": "rider@example.com",
                "password": "StrongPass123!abc",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data)
        self.assertTrue(response.data["token"])
        self.assertTrue(User.objects.filter(username="new-rider").exists())

    def test_registration_rejects_weak_password(self):
        response = self.client.post(
            "/api/auth/register/",
            {"username": "new-rider", "password": "password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="new-rider").exists())

    def test_login_and_logout_manage_token(self):
        self.client.force_authenticate(user=None)
        login_response = self.client.post(
            "/api/auth/login/",
            {"username": self.rider.username, "password": "StrongPass123!abc"},
            format="json",
        )
        token = login_response.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

        logout_response = self.client.post("/api/auth/logout/")
        protected_response = self.client.post("/api/rides/", self.ride_data, format="json")

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertEqual(logout_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(protected_response.status_code, status.HTTP_401_UNAUTHORIZED)
