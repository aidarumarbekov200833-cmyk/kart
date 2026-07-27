import asyncio
from telethon import TelegramClient
from config import settings

async def main():
    phone = input("Номер телефона (+7999...): ").strip()
    uid = input("ID пользователя в БД (узнай в админке): ").strip()
    sf = f"data/sessions/{uid}_{phone}.session"
    client = TelegramClient(sf, settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
    await client.start(phone=phone)
    me = await client.get_me()
    print(f"OK: {me.first_name} (@{me.username}) -> {sf}")
    await client.disconnect()

asyncio.run(main())
