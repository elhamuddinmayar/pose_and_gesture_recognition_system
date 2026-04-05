from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json


class PoseConsumer(AsyncWebsocketConsumer):
    """
    Handles the main surveillance WebSocket (/ws/pose/).
    Every connected dashboard tab joins 'surveillance_group' and receives
    live detection broadcasts from the engine.
    Additionally, each authenticated user joins their own personal channel
    group so that assignment notifications can be pushed directly to them.
    """

    async def connect(self):
        # 1. Join the global surveillance broadcast group
        await self.channel_layer.group_add("surveillance_group", self.channel_name)

        # 2. Join the user's personal notification group (if authenticated)
        self.user = self.scope.get("user")
        if self.user and self.user.is_authenticated:
            self.personal_group = f"user_{self.user.id}"
            await self.channel_layer.group_add(self.personal_group, self.channel_name)
        else:
            self.personal_group = None

        await self.accept()

        # 3. On connect, push any unread notifications so the user sees them
        #    immediately without waiting for the next event.
        if self.user and self.user.is_authenticated:
            unread = await self._get_unread_notifications()
            for notif in unread:
                await self.send(text_data=json.dumps({
                    "type": "NOTIFICATION",
                    "notification_id": notif["id"],
                    "notification_type": notif["notification_type"],
                    "title": notif["title"],
                    "message": notif["message"],
                    "created_at": notif["created_at"],
                }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("surveillance_group", self.channel_name)
        if self.personal_group:
            await self.channel_layer.group_discard(self.personal_group, self.channel_name)

    # ------------------------------------------------------------------ #
    # Receive messages from the browser (e.g. "mark notification as read")
    # ------------------------------------------------------------------ #
    async def receive(self, text_data):
        data = json.loads(text_data)

        if data.get("type") == "MARK_READ":
            notif_id = data.get("notification_id")
            if notif_id:
                await self._mark_notification_read(notif_id)

    # ------------------------------------------------------------------ #
    # Handlers called by channel_layer.group_send()
    # ------------------------------------------------------------------ #
    async def forward_to_websocket(self, event):
        """Called by the engine's broadcast() for STAT_UPDATE / TARGET_MATCH."""
        await self.send(text_data=json.dumps(event["payload"]))

    async def send_notification(self, event):
        """
        Called when an admin/supervisor pushes a notification to a user's
        personal group via: channel_layer.group_send(f"user_{uid}", {...})
        """
        await self.send(text_data=json.dumps({
            "type": "NOTIFICATION",
            "notification_id": event["notification_id"],
            "notification_type": event["notification_type"],
            "title": event["title"],
            "message": event["message"],
            "created_at": event["created_at"],
        }))

    # ------------------------------------------------------------------ #
    # DB helpers (sync wrapped for async context)
    # ------------------------------------------------------------------ #
    @database_sync_to_async
    def _get_unread_notifications(self):
        from surveillance.models import Notification
        qs = Notification.objects.filter(
            recipient=self.user, is_read=False
        ).order_by('-created_at')[:10]
        return list(qs.values('id', 'notification_type', 'title', 'message', 'created_at'))

    @database_sync_to_async
    def _mark_notification_read(self, notif_id):
        from surveillance.models import Notification
        Notification.objects.filter(pk=notif_id, recipient=self.user).update(is_read=True)