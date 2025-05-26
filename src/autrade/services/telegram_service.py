from typing import Optional
import aiohttp
from ..config.settings import TelegramConfig

class TelegramService:
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{config.token}"

    async def send_message(
        self,
        session: aiohttp.ClientSession,
        message: str,
        parse_mode: str = 'HTML'
    ) -> None:
        try:
            await session.post(
                f"{self.base_url}/sendMessage",
                data={
                    'chat_id': self.config.chat_id,
                    'text': message,
                    'parse_mode': parse_mode
                }
            )
        except Exception as e:
            print(f"Telegram error: {e}")

    async def edit_message(
        self,
        session: aiohttp.ClientSession,
        message_id: int,
        message: str,
        parse_mode: str = 'HTML'
    ) -> None:
        try:
            await session.post(
                f"{self.base_url}/editMessageText",
                data={
                    'chat_id': self.config.chat_id,
                    'message_id': message_id,
                    'text': message,
                    'parse_mode': parse_mode
                }
            )
        except Exception as e:
            print(f"Telegram edit error: {e}")

    async def send_photo(
        self,
        session: aiohttp.ClientSession,
        photo_path: str,
        caption: str = ""
    ) -> None:
        try:
            with open(photo_path, "rb") as photo:
                data = aiohttp.FormData()
                data.add_field("chat_id", self.config.chat_id)
                data.add_field("photo", photo, filename="report.png", content_type="image/png")
                data.add_field("caption", caption)
                await session.post(f"{self.base_url}/sendPhoto", data=data)
        except Exception as e:
            print(f"Telegram photo error: {e}") 