from telethon import TelegramClient
from telethon.errors import FloodWaitError, PeerFloodError, UserPrivacyRestrictedError
from config import settings
from db import get_user_tg_accounts, get_pending_leads, update_lead_status, log_sent_message
from utils import process_spintax
import asyncio, random

# If an account hits PeerFlood, stop using it for this run to avoid a ban.
MAX_FLOOD_WAIT = 300


async def _get_client(acc, cache):
    """Reuse one connected client per account instead of reconnecting per lead."""
    c = cache.get(acc['id'])
    if c is None:
        c = TelegramClient(acc['session_file'], settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
        await c.connect()
        cache[acc['id']] = c
    return c


async def send_campaign_async(uid, text, use_spintax=False):
    accs = get_user_tg_accounts(uid)
    if not accs:
        return {"error": "No active Telegram accounts", "sent": 0}
    leads = get_pending_leads(uid, 100)
    if not leads:
        return {"error": "No pending leads", "sent": 0}

    stats = {"sent": 0, "failed": 0, "blocked": 0, "skipped": 0}
    clients = {}
    flooded = set()  # account ids that hit PeerFlood this run
    i = 0
    try:
        for lead in leads:
            # Pick next account that is not flooded.
            usable = [a for a in accs if a['id'] not in flooded]
            if not usable:
                break  # all accounts rate-limited; stop safely
            acc = usable[i % len(usable)]; i += 1
            final = process_spintax(text) if use_spintax else text
            try:
                client = await _get_client(acc, clients)
                if not await client.is_user_authorized():
                    stats['skipped'] += 1
                    continue
                await client.send_message(lead['handle'], final)
                update_lead_status(lead['id'], 'sent')
                log_sent_message(uid, acc['id'], lead['handle'], final, 'sent')
                stats['sent'] += 1
            except PeerFloodError:
                update_lead_status(lead['id'], 'blocked')
                log_sent_message(uid, acc['id'], lead['handle'], final, 'peer_flood')
                stats['blocked'] += 1
                flooded.add(acc['id'])  # protect this account from a ban
                continue
            except FloodWaitError as w:
                if w.seconds > MAX_FLOOD_WAIT:
                    flooded.add(acc['id'])
                    continue
                await asyncio.sleep(w.seconds + 1)
                continue
            except UserPrivacyRestrictedError:
                update_lead_status(lead['id'], 'failed')
                log_sent_message(uid, acc['id'], lead['handle'], final, 'privacy_restricted')
                stats['failed'] += 1
            except Exception as e:
                update_lead_status(lead['id'], 'failed')
                log_sent_message(uid, acc['id'], lead['handle'], final, f'error: {e}')
                stats['failed'] += 1
            # Randomized human-like delay between messages.
            await asyncio.sleep(random.uniform(settings.MAILER_DELAY_MIN, settings.MAILER_DELAY_MAX))
        return stats
    finally:
        for c in clients.values():
            try:
                await c.disconnect()
            except Exception:
                pass


def send_campaign(uid, text, use_spintax=False):
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(send_campaign_async(uid, text, use_spintax))
    finally:
        loop.close()
