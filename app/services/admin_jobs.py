"""Administrative alerts queued in the same transaction as the event."""
import json
from contextvars import ContextVar

require_admin_delivery = ContextVar('require_admin_delivery', default=False)

async def enqueue(conn, kind, event_id, payload):
    await conn.execute(
        "INSERT INTO admin_notification_jobs(event_key,kind,payload) VALUES($1,$2,$3::jsonb) ON CONFLICT(event_key) DO NOTHING",
        f"{kind}:{event_id}", kind, json.dumps(payload, default=str),
    )
