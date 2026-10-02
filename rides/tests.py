from unittest.mock import patch
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from config.asgi import application
from .models import DriverProfile, RideRequest


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
        self.assertEqual(response.data["payment_method"], RideRequest.PaymentMethod.CASH)
        self.assertEqual(response.data["payment_status"], RideRequest.PaymentStatus.DUE)
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


class DriverMatchingApiTests(APITestCase):
    def setUp(self):
        self.rider = User.objects.create_user(username="matching-rider", password="StrongPass123!abc")
        self.driver = User.objects.create_user(username="driver", password="StrongPass123!abc")
        self.profile = DriverProfile.objects.create(
            user=self.driver,
            is_approved=True,
        )
        self.ride_data = {
            "pickup_address": "Central Station",
            "pickup_latitude": "51.507200",
            "pickup_longitude": "-0.127600",
            "destination_address": "City Airport",
            "destination_latitude": "51.470000",
            "destination_longitude": "-0.454300",
        }
        self.client.force_authenticate(user=self.rider)
        response = self.client.post("/api/rides/", self.ride_data, format="json")
        self.ride_id = response.data["id"]

    def go_online(self, user=None, latitude="51.500000", longitude="-0.100000"):
        self.client.force_authenticate(user=user or self.driver)
        return self.client.post(
            "/api/driver/location/",
            {
                "latitude": latitude,
                "longitude": longitude,
                "is_available": True,
            },
            format="json",
        )

    def test_unapproved_user_cannot_use_driver_endpoints(self):
        unapproved = User.objects.create_user(username="pending-driver", password="StrongPass123!abc")
        DriverProfile.objects.create(user=unapproved)
        self.client.force_authenticate(user=unapproved)

        response = self.client.post(
            "/api/driver/location/",
            {"latitude": "51.5", "longitude": "-0.1", "is_available": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_driver_location_rejects_invalid_coordinates(self):
        response = self.go_online(latitude="91")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_available)
        self.assertIsNone(self.profile.latitude)

    def test_nearby_rides_lists_unassigned_rides_by_distance(self):
        self.go_online()
        self.client.force_authenticate(user=self.rider)
        farther_data = {
            **self.ride_data,
            "pickup_address": "Farther station",
            "pickup_latitude": "51.540000",
            "pickup_longitude": "-0.100000",
        }
        self.client.post("/api/rides/", farther_data, format="json")
        self.client.force_authenticate(user=self.driver)

        response = self.client.get("/api/driver/rides/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["id"], self.ride_id)
        self.assertLess(response.data[0]["distance_km"], response.data[1]["distance_km"])

    def test_driver_must_be_online_to_view_nearby_rides(self):
        self.client.force_authenticate(user=self.driver)

        response = self.client.get("/api/driver/rides/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_driver_accepts_nearby_ride_and_becomes_unavailable(self):
        self.go_online()

        response = self.client.post(f"/api/driver/rides/{self.ride_id}/accept/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], RideRequest.Status.ACCEPTED)
        self.assertEqual(response.data["driver_username"], self.driver.username)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_available)
        self.client.force_authenticate(user=self.rider)
        rider_response = self.client.get(f"/api/rides/{self.ride_id}/")
        self.assertEqual(rider_response.data["driver_username"], self.driver.username)

    def test_accepting_ride_schedules_websocket_update(self):
        self.go_online()

        with patch("rides.views.broadcast_ride_update") as broadcast:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(f"/api/driver/rides/{self.ride_id}/accept/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        broadcast.assert_called_once_with(UUID(self.ride_id))

    def test_driver_cannot_accept_ride_outside_matching_radius(self):
        self.go_online(latitude="52.500000", longitude="-0.100000")

        response = self.client.post(f"/api/driver/rides/{self.ride_id}/accept/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNone(RideRequest.objects.get(id=self.ride_id).driver_id)

    def test_only_assigned_driver_can_advance_ride_status(self):
        self.go_online()
        self.client.post(f"/api/driver/rides/{self.ride_id}/accept/")
        other_driver = User.objects.create_user(username="other-driver", password="StrongPass123!abc")
        DriverProfile.objects.create(user=other_driver, is_approved=True)
        self.client.force_authenticate(user=other_driver)

        response = self.client.post(
            f"/api/driver/rides/{self.ride_id}/status/",
            {"status": RideRequest.Status.DRIVER_ARRIVING},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            RideRequest.objects.get(id=self.ride_id).status,
            RideRequest.Status.ACCEPTED,
        )

    def test_driver_must_follow_ride_status_transitions(self):
        self.go_online()
        self.client.post(f"/api/driver/rides/{self.ride_id}/accept/")

        response = self.client.post(
            f"/api/driver/rides/{self.ride_id}/status/",
            {"status": RideRequest.Status.COMPLETED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ride_status_cannot_skip_a_transition(self):
        self.go_online()
        self.client.post(f"/api/driver/rides/{self.ride_id}/accept/")

        response = self.client.post(
            f"/api/driver/rides/{self.ride_id}/status/",
            {"status": RideRequest.Status.ARRIVED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            RideRequest.objects.get(id=self.ride_id).status,
            RideRequest.Status.ACCEPTED,
        )

    def test_driver_can_complete_ride_through_valid_transitions(self):
        self.go_online()
        self.client.post(f"/api/driver/rides/{self.ride_id}/accept/")
        for next_status in (
            RideRequest.Status.DRIVER_ARRIVING,
            RideRequest.Status.ARRIVED,
            RideRequest.Status.IN_PROGRESS,
            RideRequest.Status.COMPLETED,
        ):
            response = self.client.post(
                f"/api/driver/rides/{self.ride_id}/status/",
                {"status": next_status},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["status"], next_status)

    def test_driver_confirms_cash_after_completing_ride(self):
        self.go_online()
        self.client.post(f"/api/driver/rides/{self.ride_id}/accept/")
        for next_status in (
            RideRequest.Status.DRIVER_ARRIVING,
            RideRequest.Status.ARRIVED,
            RideRequest.Status.IN_PROGRESS,
            RideRequest.Status.COMPLETED,
        ):
            self.client.post(
                f"/api/driver/rides/{self.ride_id}/status/",
                {"status": next_status},
                format="json",
            )

        response = self.client.post(
            f"/api/driver/rides/{self.ride_id}/cash-payment/confirm/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["payment_status"], RideRequest.PaymentStatus.PAID)
        self.assertIsNotNone(response.data["cash_paid_at"])

        repeat_response = self.client.post(
            f"/api/driver/rides/{self.ride_id}/cash-payment/confirm/"
        )
        self.assertEqual(repeat_response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(user=self.rider)
        rider_response = self.client.get(f"/api/rides/{self.ride_id}/")
        self.assertEqual(rider_response.data["payment_status"], RideRequest.PaymentStatus.PAID)

    def test_cash_cannot_be_confirmed_before_ride_completion(self):
        self.go_online()
        self.client.post(f"/api/driver/rides/{self.ride_id}/accept/")

        response = self.client.post(
            f"/api/driver/rides/{self.ride_id}/cash-payment/confirm/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            RideRequest.objects.get(id=self.ride_id).payment_status,
            RideRequest.PaymentStatus.DUE,
        )

    def test_rider_cannot_confirm_cash_payment(self):
        self.client.force_authenticate(user=self.rider)

        response = self.client.post(
            f"/api/driver/rides/{self.ride_id}/cash-payment/confirm/"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RideUpdatesWebsocketTests(TestCase):
    def setUp(self):
        self.rider = User.objects.create_user(username="ws-rider", password="StrongPass123!abc")
        self.other_user = User.objects.create_user(
            username="ws-other",
            password="StrongPass123!abc",
        )
        self.ride = RideRequest.objects.create(
            rider=self.rider,
            pickup_address="Central Station",
            pickup_latitude="51.507200",
            pickup_longitude="-0.127600",
            destination_address="City Airport",
            destination_latitude="51.470000",
            destination_longitude="-0.454300",
        )
        self.rider_token = Token.objects.create(user=self.rider)
        self.other_token = Token.objects.create(user=self.other_user)

    def test_rider_receives_initial_ride_snapshot(self):
        async def run():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/rides/{self.ride.id}/",
            )
            connected, _ = await communicator.connect()
            await communicator.send_json_to({"token": self.rider_token.key})
            message = await communicator.receive_json_from()
            await communicator.disconnect()
            return connected, message

        connected, message = async_to_sync(run)()

        self.assertTrue(connected)
        self.assertEqual(message["type"], "ride.update")
        self.assertEqual(message["ride"]["id"], str(self.ride.id))
        self.assertEqual(message["ride"]["status"], RideRequest.Status.REQUESTED)

    def test_other_user_is_denied_ride_updates(self):
        async def run():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/rides/{self.ride.id}/",
            )
            connected, _ = await communicator.connect()
            await communicator.send_json_to({"token": self.other_token.key})
            message = await communicator.receive_json_from()
            closed = await communicator.receive_output(timeout=1)
            return connected, message, closed

        connected, message, closed = async_to_sync(run)()

        self.assertTrue(connected)
        self.assertEqual(message["type"], "error")
        self.assertEqual(closed["code"], 4403)

    def test_subscriber_receives_live_ride_update(self):
        async def run():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/rides/{self.ride.id}/",
            )
            connected, _ = await communicator.connect()
            await communicator.send_json_to({"token": self.rider_token.key})
            await communicator.receive_json_from()
            await get_channel_layer().group_send(
                f"ride_{self.ride.id}",
                {
                    "type": "ride.update",
                    "ride": {"id": str(self.ride.id), "status": RideRequest.Status.ACCEPTED},
                },
            )
            message = await communicator.receive_json_from()
            await communicator.disconnect()
            return connected, message

        connected, message = async_to_sync(run)()

        self.assertTrue(connected)
        self.assertEqual(message["type"], "ride.update")
        self.assertEqual(message["ride"]["status"], RideRequest.Status.ACCEPTED)
