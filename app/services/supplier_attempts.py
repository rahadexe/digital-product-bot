"""Durable barrier against resending a purchase after a worker or transaction fails."""

from __future__ import annotations

import json
from typing import Any

from app.db import Database


def unknown_outcome() -> dict[str, Any]:
    return {'success': False, 'outcome_unknown': True,
            'detail': 'An earlier supplier attempt may have been accepted. Reconcile before retrying.'}


class SupplierAttempts:
    def __init__(self, db: Database):
        # Independent commits must survive rollback of the caller's wallet transaction.
        # A separate, small pool also avoids starvation when every main-pool connection
        # is held by a purchase. It is opened lazily, only for supplier purchases.
        self.db = Database(db.dsn, schema=db.schema, max_size=2,
                           statement_cache_size=db.statement_cache_size)

    async def close(self) -> None:
        await self.db.close()

    async def purchase(self, supplier: Any, *, supplier_code: str, product_id: int,
                       quantity: int, custom_id: str, tg_user_id: int, local_product_id: int,
                       customer_request_id: str, retry_refused: bool = False) -> dict[str, Any]:
        async with self.db.connect() as conn:
            claimed = await conn.fetchval(
                """INSERT INTO supplier_order_attempts
                   (request_key, supplier_code, product_id, quantity, status,
                    tg_user_id, local_product_id, customer_request_id)
                   VALUES ($1,$2,$3,$4,'sending',$5,$6,$7) ON CONFLICT DO NOTHING RETURNING request_key""",
                custom_id, supplier_code, product_id, quantity, tg_user_id, local_product_id, customer_request_id,
            )
            if not claimed:
                previous = await conn.fetchrow(
                    'SELECT * FROM supplier_order_attempts WHERE request_key=$1', custom_id,
                )
                if (previous['supplier_code'], previous['product_id'], previous['quantity'],
                    previous['tg_user_id'], previous['local_product_id'], previous['customer_request_id']) != (
                    supplier_code, product_id, quantity, tg_user_id, local_product_id, customer_request_id,
                ):
                    return {'success': False, 'request_conflict': True,
                            'detail': 'This purchase request was already used with different order details.'}
                if previous['status'] == 'accepted':
                    return json.loads(previous['response'])
                if previous['status'] == 'refused':
                    if not retry_refused:
                        return json.loads(previous['response'])
                    claimed = await conn.fetchval(
                        """UPDATE supplier_order_attempts SET status='sending', response=NULL,
                           updated_at=now() WHERE request_key=$1 AND status='refused' RETURNING request_key""",
                        custom_id,
                    )
                if not claimed:
                    return unknown_outcome()

        # The committed 'sending' record remains if cancellation/process death occurs
        # during this call. Never auto-expire it: the supplier may already have charged.
        response = await supplier.purchase(product_id=product_id, quantity=quantity, custom_id=custom_id)
        status = ('accepted' if response.get('success') else
                  'unknown' if response.get('outcome_unknown') else 'refused')
        async with self.db.connect() as conn:
            await conn.execute(
                'UPDATE supplier_order_attempts SET status=$2, response=$3::jsonb, updated_at=now() WHERE request_key=$1',
                custom_id, status, json.dumps(response),
            )
        return response
