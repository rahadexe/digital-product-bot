"""Confirming USDT deposits against the shop's own Binance account.

The customer sends USDT (TRC20 or BEP20) to the shop's Binance deposit address and submits the transaction
ID, exactly as before. This service looks that transaction up in Binance's deposit history with a read-only
API key: when Binance reports it as credited, for the right coin, network and at least the expected amount,
the deposit is approved automatically. Anything that does not match is left for the admin to review, so a
wrong or unknown transaction never credits a wallet.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import asyncpg
import httpx

if TYPE_CHECKING:
    from app.services.binance_credentials import BinanceCredentialsService

from app.core.config import Settings
from app.core.money import money
from app.db import Database
from app.services.audit import record
from app.services.deposits import DepositService
from app.services.errors import InvalidInputError
from app.services.http import gateway_http
from app.services.notifications import Notifier
from app.services.settings import SettingsService

logger = logging.getLogger("app.services.binance")

BINANCE_API = "https://api.binance.com"
# On-chain deposits into the shop's Binance account, and transfers sent inside Binance with Binance Pay.
PROVIDER = "binance"
PAY_PROVIDER = "binance_pay"
PROVIDERS = (PROVIDER, PAY_PROVIDER)
# Binance Pay order types that mean money arrived from a person.
PAY_INCOMING = ("C2C", "PAY", "REMITTANCE")
# Binance's own deposit states; 1 means the coin is in the account and spendable.
STATUS_SUCCESS = 1
# How far back a submitted transaction may be found (Binance keeps 90 days; a shop deposit is far newer).
LOOKBACK_DAYS = 7
# A payment is credited only when it arrived shortly before the customer claimed it. Someone copying an old
# transaction from a block explorer (or the shop's own transfers into Binance) is sent to the admin instead.
# Three days rather than one: a customer who pays at night and comes back after the weekend is making an
# honest claim, and one day turned that into a manual ticket. What stops a payment being claimed twice is
# _already_credited, not this window; this only keeps genuinely old history out of an automatic credit.
PAID_BEFORE_CLAIM_HOURS = 72
MAX_CHECKS_PER_RUN = 20
# Binance Pay transfers show in the history within seconds. A reference still missing after
# these waits was mistyped, not delayed; it is refused rather than filed, because a filed
# request holds the customer's one pending deposit until an admin rejects it.
PAY_LOOKUP_RETRY_DELAYS = (3.0, 4.0)
# Order ids are 18 digits and transaction ids longer. Anything shorter is a Binance UID, which
# names a sender, not a payment: those are still filed for an admin to match by hand.
MIN_PAYMENT_REFERENCE = 15
# Networks Binance names for the chains customers use for USDT.
NETWORKS = {"TRX": "TRC20", "BSC": "BEP20", "ETH": "ERC20"}


class BinanceError(Exception):
    """Binance refused the request or could not be reached. Nothing is approved."""


class BinanceClient:
    """The read-only call this integration needs with automatic server time synchronization."""

    _time_offset: int = 0
    _last_time_sync: float = 0.0

    def __init__(self, api_key: str, api_secret: str, http: httpx.AsyncClient, timeout: float = 20.0):
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self.http = http
        self._pay_cache: tuple[float, list[dict[str, Any]]] | None = None

    @classmethod
    async def sync_server_time(cls, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - cls._last_time_sync < 300):
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{BINANCE_API}/api/v3/time")
                if res.status_code == 200:
                    server_time = res.json().get("serverTime")
                    if server_time:
                        cls._time_offset = int(server_time) - int(time.time() * 1000)
                        cls._last_time_sync = now
        except Exception:
            pass

    def _sign(self, params: dict[str, Any]) -> str:
        adjusted_ts = int(time.time() * 1000) + BinanceClient._time_offset - 300
        query = urlencode({**params, "timestamp": adjusted_ts, "recvWindow": 60_000})
        signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return f"{query}&signature={signature}"

    async def _signed_get(self, path: str, params: dict[str, Any]) -> Any:
        await self.sync_server_time()
        try:
            response = await self.http.get(
                f"{BINANCE_API}{path}?{self._sign(params)}",
                headers={"X-MBX-APIKEY": self.api_key, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise BinanceError(f"Binance could not be reached ({type(exc).__name__}).") from None
        try:
            body = response.json()
        except ValueError:
            body = None

        if response.status_code == 400 and isinstance(body, dict) and body.get("code") == -1021:
            # Timestamp drift: force resync and retry once
            await self.sync_server_time(force=True)
            try:
                response = await self.http.get(
                    f"{BINANCE_API}{path}?{self._sign(params)}",
                    headers={"X-MBX-APIKEY": self.api_key, "Accept": "application/json"},
                )
                try:
                    body = response.json()
                except ValueError:
                    body = None
            except Exception:
                pass

        if response.status_code != 200:
            message = ""
            if isinstance(body, dict):
                # -2015 is the usual answer when the key, its permission or the server IP is wrong.
                message = f" {body.get('code', '')} {str(body.get('msg') or '')[:120]}".rstrip()
            raise BinanceError(f"Binance HTTP {response.status_code}{message}")
        return body

    async def deposit_history(
        self, *, coin: str = "USDT", tx_id: str | None = None, start_time: int | None = None
    ) -> list[dict[str, Any]]:
        """Coin that arrived on a blockchain, as Binance credited it."""
        params: dict[str, Any] = {"coin": coin, "limit": 100}
        if tx_id:
            params["txId"] = tx_id
        if start_time:
            params["startTime"] = start_time
        body = await self._signed_get("/sapi/v1/capital/deposit/hisrec", params)
        if not isinstance(body, list):
            raise BinanceError("Binance answered the deposit history with something unexpected.")
        return body

    async def pay_transactions(self, *, start_time: int | None = None) -> list[dict[str, Any]]:
        """Binance Pay movements; money received from a person is positive and carries who sent it."""
        if self._pay_cache and time.monotonic() - self._pay_cache[0] < 15:
            return self._pay_cache[1]
        params: dict[str, Any] = {"limit": 100}
        if start_time:
            params["startTime"] = start_time
        body = await self._signed_get("/sapi/v1/pay/transactions", params)
        data = body.get("data") if isinstance(body, dict) else body
        rows = [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
        self._pay_cache = (time.monotonic(), rows)
        return rows


def _payer_id(row: dict[str, Any]) -> str:
    payer = row.get("payerInfo")
    return str((payer or {}).get("binanceId") or "").strip() if isinstance(payer, dict) else ""


def _same_transaction(left: str, right: str) -> bool:
    """Transaction hashes are compared without case or an 0x prefix, which wallets show differently."""
    normalise = lambda value: str(value or "").strip().lower().removeprefix("0x")  # noqa: E731
    return bool(normalise(left)) and normalise(left) == normalise(right)


class BinanceDepositService:
    def __init__(
        self,
        db: Database,
        settings: SettingsService,
        deposits: DepositService,
        notifier: Notifier,
        config: Settings,
        binance_credentials: BinanceCredentialsService | None = None,
    ):
        self.db = db
        self.settings = settings
        self.deposits = deposits
        self.notifier = notifier
        self.config = config
        self.binance_credentials = binance_credentials
        self.http = gateway_http()

    # --- configuration ---
    def client(self, api_key: str, api_secret: str) -> BinanceClient:
        return BinanceClient(api_key, api_secret, self.http)

    async def get_credentials_for_method(self, method_id: int | None) -> tuple[str, str]:
        if method_id is not None and self.binance_credentials:
            creds = await self.binance_credentials.get(method_id)
            if creds and creds.get("api_key") and creds.get("api_secret"):
                return creds["api_key"].strip(), creds["api_secret"].strip()
        # Fallback to legacy global settings if configured
        key = (await self.settings.get("binance_api_key")).strip() or self.config.binance_api_key.strip()
        secret = (await self.settings.get("binance_api_secret")).strip() or self.config.binance_api_secret.strip()
        if key and secret:
            return key, secret
        return "", ""

    async def _credentials(self, method_id: int | None = None) -> tuple[str, str]:
        return await self.get_credentials_for_method(method_id)

    async def enabled(self, method_id: int | None = None) -> bool:
        key, secret = await self.get_credentials_for_method(method_id)
        return bool(key and secret)

    async def status(self) -> dict[str, Any]:
        values = await self.settings.values()
        methods = await self.deposits.methods(active_only=False)
        binance_methods = [
            m for m in methods
            if m.get("auto_verify") in PROVIDERS or m.get("account_type") == "crypto" or "binance" in m.get("name", "").lower()
        ]
        has_any_keys = any(bool(m.get("has_api_credentials")) for m in binance_methods)
        if not has_any_keys:
            legacy_key, legacy_secret = await self.get_credentials_for_method(None)
            has_any_keys = bool(legacy_key and legacy_secret)
        return {
            "enabled": any(m.get("is_active") == 1 for m in binance_methods),
            "has_credentials": has_any_keys,
            "coin": values.get("binance_coin", "USDT"),
            "ready": bool(has_any_keys and binance_methods),
            "methods": [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "kind": "Binance" if m.get("auto_verify") == PAY_PROVIDER else "On-chain",
                    "network": m.get("auto_verify_network") or ("Binance ID" if m.get("auto_verify") == PAY_PROVIDER else "any"),
                    "is_active": m["is_active"],
                    "has_api_credentials": bool(m.get("has_api_credentials")),
                }
                for m in binance_methods
            ],
        }

    async def test_connection(self, method_id: int | None = None) -> dict[str, Any]:
        key, secret = await self.get_credentials_for_method(method_id)
        if not key or not secret:
            if method_id is None and self.binance_credentials:
                methods = await self.deposits.methods(active_only=False)
                for m in methods:
                    if m.get("has_api_credentials"):
                        key, secret = await self.get_credentials_for_method(m["id"])
                        if key and secret:
                            break
        if not key or not secret:
            return {"ok": False, "message": "Add the Binance API key and secret first."}
        values = await self.settings.values()
        coin = values.get("binance_coin", "USDT")
        try:
            history = await self.client(key, secret).deposit_history(coin=coin, start_time=self._since())
        except BinanceError as exc:
            return {"ok": False, "message": f"{exc} Use a key with 'Enable Reading' and whitelist this server's IP."}
        return {
            "ok": True,
            "message": f"Binance accepted the key. {len(history)} {coin} deposit(s) in the last {LOOKBACK_DAYS} days.",
        }

    @staticmethod
    def _arrived_in_time(deposit: dict[str, Any], arrived_ms: Any) -> bool:
        """True when Binance reports no time, or the payment reached Binance no earlier than a day before the claim."""
        try:
            arrived = int(arrived_ms or 0) / 1000
        except (TypeError, ValueError):
            return False
        if not arrived:
            return True
        claimed = deposit["created_at"].timestamp()
        return arrived >= claimed - PAID_BEFORE_CLAIM_HOURS * 3600

    def _since(self) -> int:
        return int((time.time() - LOOKBACK_DAYS * 86_400) * 1000)

    # --- checking deposits ---
    async def _pending(self, deposit_id: int | None = None) -> list[dict[str, Any]]:
        if deposit_id is not None:
            query = (
                "SELECT d.*, m.auto_verify, m.auto_verify_network, m.min_deposit, m.account_info AS method_account "
                "FROM deposits d "
                "LEFT JOIN deposit_methods m ON m.id = d.method_id "
                "WHERE d.status = 'pending' AND d.id = $1"
            )
            async with self.db.connect() as conn:
                return [dict(row) for row in await conn.fetch(query, deposit_id)]

        query = (
            "SELECT d.*, m.auto_verify, m.auto_verify_network, m.min_deposit, m.account_info AS method_account FROM deposits d "
            "JOIN deposit_methods m ON m.id = d.method_id "
            "WHERE d.status = 'pending' AND m.auto_verify = ANY($1) AND d.created_at > now() - $2 * interval '1 day' "
            "ORDER BY d.next_check_at, d.id LIMIT 50"
        )
        async with self.db.connect() as conn:
            return [dict(row) for row in await conn.fetch(query, list(PROVIDERS), LOOKBACK_DAYS)]

    async def check(self, deposit_id: int, notify_customer: bool = True) -> dict[str, Any]:
        """Check one pending deposit against Binance. Returns what happened, without raising."""
        pending = await self._pending(deposit_id)
        if not pending:
            return {"checked": False, "credited": False, "detail": "This deposit is not waiting for a Binance check."}
        deposit = pending[0]
        key, secret = await self.get_credentials_for_method(deposit.get("method_id"))
        if not key or not secret:
            return {"checked": False, "credited": False, "detail": "Binance credentials are not configured for this method."}
        coin = (await self.settings.values())["binance_coin"]
        try:
            return await self._match(deposit, self.client(key, secret), coin, notify_customer=notify_customer)
        except BinanceError as exc:
            logger.warning("Binance check for deposit #%s failed: %s", deposit_id, exc)
            return {"checked": False, "credited": False, "detail": str(exc)}

    async def recheck_pending(self) -> int:
        """Background pass over deposits still waiting, for payments that confirm after the customer left."""
        async with self.db.transaction() as conn:
            claimed = await conn.fetch(
                "UPDATE deposits SET next_check_at=now()+interval '2 minutes' WHERE id IN ("
                "SELECT d.id FROM deposits d JOIN deposit_methods m ON m.id=d.method_id "
                "WHERE d.status='pending' AND m.auto_verify=ANY($1) AND d.next_check_at<=now() "
                "AND d.created_at>now()-interval '7 days' ORDER BY d.next_check_at,d.id "
                "LIMIT $2 FOR UPDATE OF d SKIP LOCKED) RETURNING id", list(PROVIDERS), MAX_CHECKS_PER_RUN
            )
        pending = []
        for row in claimed:
            pending.extend(await self._pending(row['id']))
        coin = (await self.settings.values())["binance_coin"]
        checked = 0
        for deposit in pending[:MAX_CHECKS_PER_RUN]:
            key, secret = await self.get_credentials_for_method(deposit.get("method_id"))
            if not key or not secret:
                continue
            client = self.client(key, secret)
            try:
                await self._match(deposit, client, coin, notify_customer=True)
            except BinanceError as exc:
                logger.warning("Binance check for deposit #%s failed: %s", deposit["id"], exc)
                continue
            checked += 1
        return checked

    async def claim(self, tg_user_id: int, method_id: int, reference: str, expected_usdt: float | None = None) -> dict[str, Any]:
        """A customer says they have paid. What they sent decides the amount, so none is asked for."""
        async with self.db.connect() as conn:
            method = await conn.fetchrow(
                "SELECT * FROM deposit_methods WHERE id = $1 AND is_active = 1",
                method_id,
            )
        if not method:
            raise InvalidInputError("Payment method is no longer available.")
        min_dep = float(method["min_deposit"])
        if expected_usdt is not None:
            paid = money(expected_usdt, positive=True)
            base_amount = paid  # USDT credits USD wallet 1:1.
        else:
            base_amount = money(min_dep, positive=True)

        key, secret = await self.get_credentials_for_method(method_id)
        has_keys = bool(key and secret)

        if has_keys and method.get("auto_verify") == PAY_PROVIDER and len(reference.strip()) >= MIN_PAYMENT_REFERENCE:
            refused = await self._refuse_unusable_pay_reference(reference, key=key, secret=secret)
            if refused:
                return {"deposit_id": None, "checked": True, "credited": False, **refused}

        deposit_id = await self.deposits.create_request(tg_user_id, method_id, base_amount, reference,
                                                        quoted_rate=1.0, notify_admin=False)
        if has_keys:
            async with self.db.transaction() as conn:
                await conn.execute(
                    "UPDATE deposits SET admin_note = $1 WHERE id = $2 AND status = 'pending'",
                    f"Waiting for Binance auto-verification (expected {expected_usdt:g} USDT)..." if expected_usdt else "Waiting for Binance auto-verification...",
                    deposit_id,
                )
            result = await self.check(deposit_id, notify_customer=False)
            if not result.get("credited"):
                await self.deposits.alert_admin_needs_review(deposit_id, str(result.get("detail") or ""))
            return {"deposit_id": deposit_id, **result}
        else:
            async with self.db.transaction() as conn:
                await conn.execute(
                    "UPDATE deposits SET admin_note = $1 WHERE id = $2 AND status = 'pending'",
                    f"Manual Binance review required (expected {expected_usdt:g} USDT)" if expected_usdt else "Manual Binance review required",
                    deposit_id,
                )
            await self.deposits.alert_admin_needs_review(deposit_id, "Manual verification required.")
            return {"deposit_id": deposit_id, "checked": False, "credited": False, "detail": "Manual review required"}

    async def _refuse_unusable_pay_reference(self, reference: str, key: str = "", secret: str = "") -> dict[str, Any] | None:
        """Why this Binance Pay reference can never be credited, or None if it might be."""
        if not key or not secret:
            key, secret = await self._credentials()
        if not key or not secret:
            return None
        coin = (await self.settings.values())["binance_coin"]
        wanted = reference.strip().lower()
        for attempt in range(len(PAY_LOOKUP_RETRY_DELAYS) + 1):
            if attempt:
                await asyncio.sleep(PAY_LOOKUP_RETRY_DELAYS[attempt - 1])
            try:
                # A fresh client each time: the client caches the history for 15 seconds.
                history = await self.client(key, secret).pay_transactions(start_time=self._since())
            except BinanceError:
                return None
            matches = [
                row for row in history
                if wanted in {str(row.get("orderId") or "").strip().lower(),
                              str(row.get("transactionId") or "").strip().lower()}
                and str(row.get("orderType") or "").upper() in PAY_INCOMING
                and money(row.get("amount") or 0) > 0
                and str(row.get("currency") or "").upper() == coin.upper()
            ]
            if matches:
                break
        else:
            return {"error": "not_found", "detail": "Binance has no incoming transfer with this reference."}
        for row in matches:
            ids = [str(row.get(k) or "").strip() for k in ("transactionId", "orderId")]
            if not any([await self._already_credited(i) for i in ids if i]):
                return None
        return {"error": "already_used", "detail": "This transfer has already been credited."}

    async def _already_credited(self, transaction_id: str, exclude_deposit_id: int | None = None) -> bool:
        norm_tx = str(transaction_id or "").strip().lower().removeprefix("0x")
        query = (
            "SELECT 1 FROM deposits WHERE (lower(btrim(transaction_id)) = lower(btrim($1)) "
            "OR lower(btrim(transaction_id)) = lower(btrim('0x' || $1)) "
            "OR admin_note ILIKE $2) AND status = 'approved'"
        )
        params: list[Any] = [norm_tx, f"%{norm_tx}%"]
        if exclude_deposit_id is not None:
            query += " AND id <> $3"
            params.append(exclude_deposit_id)
        async with self.db.connect() as conn:
            return bool(await conn.fetchval(query, *params))

    async def _match(
        self, deposit: dict[str, Any], client: BinanceClient, coin: str, notify_customer: bool = True
    ) -> dict[str, Any]:
        if deposit.get("auto_verify") == PAY_PROVIDER:
            return await self._match_pay(deposit, client, coin, notify_customer=notify_customer)
        transaction_id = str(deposit["transaction_id"]).strip()
        records = await client.deposit_history(coin=coin, tx_id=transaction_id)
        if not records:
            # Binance's filter is exact; wallets show hashes with different case or an 0x prefix.
            records = [
                row
                for row in await client.deposit_history(coin=coin, start_time=self._since())
                if _same_transaction(row.get("txId", ""), transaction_id)
            ]
        record_row = next((row for row in records if _same_transaction(row.get("txId", ""), transaction_id)), None)
        if not record_row:
            return {"checked": True, "credited": False, "detail": "Binance has not received this transaction yet."}

        # Everything Binance reports must agree with what this shop asked the customer to do.
        sent_to = str(record_row.get("address") or "").strip()
        shown = str(deposit.get("method_account") or "").strip()
        if sent_to and shown and sent_to.lower() != shown.lower():
            return await self._flag(deposit, f"it was sent to {sent_to}, not to the address this method shows")
        if not self._arrived_in_time(deposit, record_row.get("insertTime")):
            return await self._flag(deposit, f"the payment arrived more than {PAID_BEFORE_CLAIM_HOURS} hours before it was claimed")
        network = str(record_row.get("network") or "")
        wanted = str(deposit.get("auto_verify_network") or "")
        if wanted and network.upper() != wanted.upper():
            return await self._flag(deposit, f"paid on {network or 'an unknown network'}, but this method accepts {wanted} only")
        if str(record_row.get("coin") or "").upper() != coin.upper():
            return await self._flag(deposit, f"the transaction is {record_row.get('coin')}, not {coin}")
        if int(record_row.get("status", -1)) != STATUS_SUCCESS:
            return {
                "checked": True,
                "credited": False,
                "detail": f"Binance is still confirming it ({record_row.get('confirmTimes') or 'pending'}).",
            }

        received = money(record_row.get("amount") or 0)
        # Filed under Binance's own spelling of the hash, so "0xABC" and "abc" cannot be credited twice.
        canonical = str(record_row.get("txId") or transaction_id).strip()
        if canonical.lower() != transaction_id.lower() and await self._already_credited(canonical, exclude_deposit_id=deposit["id"]):
            return await self._flag(deposit, f"payment {canonical} has already been credited")
        return await self._credit(
            deposit,
            received=received,
            coin=coin,
            transaction_id=canonical,
            note=f"Confirmed on Binance: {received:g} {coin} ({NETWORKS.get(network.upper(), network)}), TrxID {transaction_id}",
            notify_customer=notify_customer,
        )

    async def _match_pay(
        self, deposit: dict[str, Any], client: BinanceClient, coin: str, notify_customer: bool = True
    ) -> dict[str, Any]:
        """Binance Pay: matching by Binance UID, Counterparty ID, Order ID, or Transaction ID."""
        reference = str(deposit["transaction_id"]).strip().lower()
        history = await client.pay_transactions(start_time=self._since())
        arrivals = [
            row
            for row in history
            if str(row.get("orderType") or "").upper() in PAY_INCOMING
            and money(row.get("amount") or 0) > 0
            and str(row.get("currency") or "").upper() == coin.upper()
            and self._arrived_in_time(deposit, row.get("transactionTime"))
        ]

        # Kept apart from the list above: a reference that is real but older than the
        # window is a different problem from one Binance has never seen, and telling a
        # customer to wait a minute for a payment they made last week helps nobody.
        stale = [
            row
            for row in history
            if reference in {str(row.get("orderId") or "").strip().lower(),
                             str(row.get("transactionId") or "").strip().lower()}
            and not self._arrived_in_time(deposit, row.get("transactionTime"))
        ]

        matched_rows = []
        for row in arrivals:
            order_id = str(row.get("orderId") or "").strip().lower()
            tx_id = str(row.get("transactionId") or "").strip().lower()
            # Stable sender IDs (payerInfo.binanceId, counterpartyId) are not payment-specific proof
            # and are deliberately not matched on. Require the unique receipt reference; ambiguous
            # UID-only claims remain pending for review.
            candidates = {c for c in (order_id, tx_id) if c}
            if reference in candidates:
                matched_rows.append(row)

        matched_rows.sort(key=lambda row: int(row.get("transactionTime") or 0), reverse=True)
        for row in matched_rows:
            transaction_id = str(row.get("transactionId") or "").strip()
            order_id = str(row.get("orderId") or "").strip()
            if not transaction_id:
                continue
            if await self._already_credited(transaction_id, exclude_deposit_id=deposit["id"]):
                continue
            if order_id and await self._already_credited(order_id, exclude_deposit_id=deposit["id"]):
                continue
            received = money(row.get("amount") or 0)
            payer_num = _payer_id(row).strip()
            return await self._credit(
                deposit,
                received=received,
                coin=coin,
                transaction_id=transaction_id,
                order_id=order_id,
                note=f"Confirmed on Binance: {received:g} {coin} (Order: {order_id}, Transaction: {transaction_id}, Payer: {payer_num})",
                notify_customer=notify_customer,
            )
        return {
            "checked": True,
            "credited": False,
            "needs_person": bool(stale),
            "detail": (
                f"Transfer '{reference}' was found on Binance, but it was paid more than "
                f"{PAID_BEFORE_CLAIM_HOURS} hours before this request. Please send a new payment "
                f"and use that receipt, or contact support."
                if stale else
                f"No matching {coin} transfer found for '{reference}'. "
                f"If you just paid, please wait a minute."
            ),
        }

    async def _credit(
        self,
        deposit: dict[str, Any],
        *,
        received: float,
        coin: str,
        transaction_id: str,
        note: str,
        order_id: str = "",
        notify_customer: bool = True,
    ) -> dict[str, Any]:
        """The payment decides the amount, and its own id is what the deposit is filed under."""
        credit = money(received)  # Binance USDT and wallet USD are 1:1.
        limit = await self.settings.number("max_deposit_limit")
        if credit > limit:
            return await self._flag(deposit, f"{received:g} {coin} is above the single deposit limit")
        minimum = money(deposit.get("min_deposit") or 0)
        if credit < minimum:
            return await self._flag(deposit, f"{received:g} {coin} is below this method's smallest top-up")

        # Amount check: if deposit had a claimed amount (e.g. expected amount), ensure tolerance matches!
        if deposit.get("admin_note") and "expected" in str(deposit.get("admin_note")).lower():
            match_exp = re.search(r"expected\s+([0-9.]+)\s+usdt", str(deposit.get("admin_note")), re.IGNORECASE)
            if match_exp:
                exp_val = float(match_exp.group(1))
                if abs(credit - exp_val) > 0.05:
                    return await self._flag(deposit, f"received {received:g} {coin} does not match claimed {exp_val:g} {coin}")
        if abs(credit - money(deposit["amount"])) > 0.01 or transaction_id.lower() != str(deposit["transaction_id"]).lower():
            try:
                async with self.db.transaction() as conn:
                    updated = await conn.fetchval(
                        "UPDATE deposits SET amount = $1, transaction_id = $2, pay_amount=$4, paid_currency=$5 WHERE id = $3 AND status = 'pending' RETURNING amount",
                        credit,
                        transaction_id,
                        deposit["id"],
                        received,
                        coin,
                    )
                    if updated is None:
                        return {"checked": True, "credited": False, "detail": "The deposit is no longer pending."}
                    await record(
                        conn,
                        "deposit_amount_adjusted",
                        f"Deposit #{deposit['id']}: {received:g} {coin} received, credit set to {credit:.2f}",
                    )
            except asyncpg.UniqueViolationError:
                return await self._flag(deposit, f"payment {transaction_id} has already been credited")

        success, message, _ = await self.deposits.approve(deposit["id"], note, notify_customer=notify_customer)
        if not success:
            return {"checked": True, "credited": False, "detail": message}
        logger.info("Deposit #%s credited automatically from Binance (%s %s)", deposit["id"], received, coin)
        return {
            "checked": True,
            "credited": True,
            "amount": credit,
            "received_coin": received,
            "coin": coin,
            "transaction_id": transaction_id,
            "detail": f"Credited {credit:.2f} from {received:g} {coin}.",
        }

    async def _flag(self, deposit: dict[str, Any], reason: str) -> dict[str, Any]:
        """Something about the payment is off: leave it for the admin and say why."""
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE deposits SET admin_note = $1 WHERE id = $2 AND status = 'pending'",
                f"Needs a look: {reason}."[:500],
                deposit["id"],
            )
            await record(conn, "deposit_check_flagged", f"Deposit #{deposit['id']}: {reason}")
        # needs_person separates "we are still looking" from "looking will not help":
        # the caller told the customer to wait a minute for both, and one of them was
        # never going to arrive.
        return {"checked": True, "credited": False, "needs_person": True,
                "detail": f"Needs review: {reason}."}
