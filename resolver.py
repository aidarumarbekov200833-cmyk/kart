from telethon import TelegramClient
from telethon.errors import (FloodWaitError, UsernameInvalidError,
                             UsernameNotOccupiedError, RPCError)
from config import settings
from db import update_lead_status
import asyncio

# Safety cap so a single FloodWait can't hang the worker forever.
MAX_FLOOD_WAIT = 300


async def verify_leads_async(leads, session_file):
    client = TelegramClient(session_file, settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            return {"error": "Session not authorized", "verified": 0, "failed": 0}
        res = {"verified": 0, "failed": 0, "channels": 0, "invalid": 0}
        for lead in leads:
            try:
                e = await client.get_entity(lead['handle'])
                if getattr(e, 'broadcast', False) or getattr(e, 'megagroup', False):
                    update_lead_status(lead['id'], 'channel'); res['channels'] += 1
                else:
                    update_lead_status(lead['id'], 'verified'); res['verified'] += 1
            except (UsernameInvalidError, UsernameNotOccupiedError):
                update_lead_status(lead['id'], 'invalid'); res['invalid'] += 1
            except FloodWaitError as w:
                # Respect Telegram's cooldown but cap it; skip lead if too long.
                if w.seconds > MAX_FLOOD_WAIT:
                    break
                await asyncio.sleep(w.seconds + 1)
                continue
            except RPCError:
                update_lead_status(lead['id'], 'error'); res['failed'] += 1
            except Exception:
                update_lead_status(lead['id'], 'error'); res['failed'] += 1
            # Light, human-like pacing between lookups.
            await asyncio.sleep(1.5)
        return res
    finally:
        await client.disconnect()


def verify_leads(leads, session_file):
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(verify_leads_async(leads, session_file))
    finally:
        loop.close()
