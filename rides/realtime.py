import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework.renderers import JSONRenderer

from .models import RideRequest
from .serializers import RideRequestSerializer


def ride_group_name(ride_id):
    return f"ride_{ride_id}"


def broadcast_ride_update(ride_id):
    channel_layer = get_channel_layer()
    ride = RideRequest.objects.select_related("driver").get(id=ride_id)
    ride_data = json.loads(JSONRenderer().render(RideRequestSerializer(ride).data))
    async_to_sync(channel_layer.group_send)(
        ride_group_name(ride_id),
        {"type": "ride.update", "ride": ride_data},
    )
