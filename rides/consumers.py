import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework.authtoken.models import Token
from rest_framework.renderers import JSONRenderer

from .models import RideRequest
from .realtime import ride_group_name
from .serializers import RideRequestSerializer


class RideUpdatesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.ride_id = self.scope["url_route"]["kwargs"]["ride_id"]
        self.group_name = ride_group_name(self.ride_id)
        self.user_id = None
        await self.accept()

    async def receive_json(self, content, **kwargs):
        if self.user_id is not None:
            await self.close(code=4400)
            return

        token = content.get("token") if isinstance(content, dict) else None
        ride = await self.get_authorized_ride(token)
        if ride is None:
            await self.send_json(
                {"type": "error", "detail": "Invalid token or ride access denied."}
            )
            await self.close(code=4403)
            return

        self.user_id = ride["user_id"]
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.send_json({"type": "ride.update", "ride": ride["data"]})

    async def disconnect(self, close_code):
        if self.user_id is not None:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def ride_update(self, event):
        await self.send_json({"type": "ride.update", "ride": event["ride"]})

    @database_sync_to_async
    def get_authorized_ride(self, token_key):
        if not isinstance(token_key, str) or not token_key:
            return None
        try:
            token = Token.objects.select_related("user").get(key=token_key, user__is_active=True)
            ride = RideRequest.objects.select_related("driver").get(id=self.ride_id)
        except (Token.DoesNotExist, RideRequest.DoesNotExist, ValueError):
            return None

        if ride.rider_id != token.user_id and ride.driver_id != token.user_id:
            return None

        ride_data = json.loads(JSONRenderer().render(RideRequestSerializer(ride).data))
        return {"user_id": token.user_id, "data": ride_data}
