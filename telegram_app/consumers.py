import json

from channels.generic.websocket import AsyncWebsocketConsumer


class TelegramConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        await self.channel_layer.group_add(
            "telegram_updates",
            self.channel_name,
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            "telegram_updates",
            self.channel_name,
        )

    async def telegram_message(self, event):
        await self.send(
            text_data=json.dumps(event["data"])
        )