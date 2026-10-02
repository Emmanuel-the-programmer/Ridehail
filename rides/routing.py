from django.urls import path

from .consumers import RideUpdatesConsumer


websocket_urlpatterns = [
    path("ws/rides/<uuid:ride_id>/", RideUpdatesConsumer.as_asgi()),
]
