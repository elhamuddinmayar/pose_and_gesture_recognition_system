from channels.generic.websocket import AsyncWebsocketConsumer
import json

class PoseConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Join the global surveillance group
        await self.channel_layer.group_add("surveillance_group", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Leave the group when tab is closed
        await self.channel_layer.group_discard("surveillance_group", self.channel_name)

    async def forward_to_websocket(self, event):
        """This is called when the Engine sends data to the group."""
        await self.send(text_data=json.dumps(event["payload"]))