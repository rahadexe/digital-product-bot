"""Confirming USDT deposits against the shop's own Binance account.

The customer sends USDT (TRC20 or BEP20) to the shop's Binance deposit address and submits the transaction
ID, exactly as before. This service looks that transaction up in Binance's deposit history with a read-only
API key: when Binance reports it as credited, for the right coin, network and at least the expected amount,
the deposit is approved automatically. Anything that does not match is left for the admin to review, so a
wrong or unknown transaction never credits a wallet.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any
from urllib.parse import urlencode

import asyncpg
import httpx

from app.core.config import Settings
from app.core.money import money
from app.db import Database
from app.services.audit import record
from app.services.deposits import DepositService
from app.services.errors import InvalidInputError
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
PAID_BEFORE_CLAIM_HOURS = 24
MAX_CHECKS_PER_RUN = 20
# Networks Binance names for the chains customers use for USDT.
NETWORKS = {"TRX": "TRC20", "BSC": "BEP20", "ETH": "ERC20"}


class BinanceError(Exception):
    """Binance refused the request or could not be reached. Nothing is approved."""


class BinanceClient:
    """The one read-only call this integration needs. Keys are never logged."""

    def __init__(self, api_key: str, api_secret: str, timeout: float = 20.0):
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout

    def _sign(self, params: dict[str, Any]) -> str:
        query = urlencode({**params, "timestamp": int(time.time() * 1000), "recvWindow": 10_000})
        signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return f"{query}&signature={signature}"

    async def _signed_get(self, path: str, params: dict[str, Any]) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{BINANCE_API}{path}?{self._sign(params)}",
                    headers={"X-MBX-APIKEY": self.api_key, "Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise BinanceError(f"Binance could not be reached ({type(exc).__name__}).") from None
        try:
            body = response.json()
        except ValueError:
            body = None
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
        params: dict[str, Any] = {"limit": 100}
        if start_time:
            params["startTime"] = start_time
        body = await self._signed_get("/sapi/v1/pay/transactions", params)
        data = body.get("data") if isinstance(body, dict) else body
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _payer_id(row: dict[str, Any]) -> str:
    payer = row.get("payerInfo")
    return str((payer or {}).get("binanceId") or "").strip() if isinstance(payer, dict) else ""


def _same_transaction(left: str, right: str) -> bool:
    """Transaction hashes are compared without case or an 0x prefix, which wallets show differently."""
    normalise = lambda value: str(value or "").strip().lower().removeprefix("0x")  # noqa: E731
    return bool(normalise(left)) and normalise(left) == normalise(right)


class BinanceDepositService:
    def __init__(self, db: Database, settings: SettingsService, deposits: DepositService, notifier: Notifier, config: Settings):
        self.db = db
        self.settings = settings
        self.deposits = deposits
        self.notifier = notifier
        self.config = config

    # --- configuration ---
    def client(self, api_key: str, api_secret: str) -> BinanceClient:
        return BinanceClient(api_key, api_secret)

    async def _credentials(self) -> tuple[str, str]:
        values = await self.settings.values()
        key = (await self.settings.get("binance_api_key")).strip() or self.config.binance_api_key.strip()
        secret = (await self.settings.get("binance_api_secret")).strip() or self.config.binance_api_secret.strip()
        return (key, secret) if values["binance_enabled"] == "1" else ("", "")

    async def enabled(self) -> bool:
        key, secret = await self._credentials()
        return bool(key and secret)

    async def status(self) -> dict[str, Any]:
        values = await self.settings.values()
        key, secret = await self._credentials()
        async with self.db.connect() as conn:
            methods = await conn.fetch(
                "SELECT id, name, auto_verify, auto_verify_network, is_active FROM deposit_methods "
                "WHERE auto_verify = ANY($1) ORDER BY sort_order, id",
                list(PROVIDERS),
            )
        return {
            "enabled": values["binance_enabled"] == "1",
            "has_credentials": bool(key and secret),
            "coin": values["binance_coin"],
            "ready": bool(key and secret and methods),
            "methods": [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "kind": "Binance Pay" if m["auto_verify"] == PAY_PROVIDER else "On-chain",
                    "network": m["auto_verify_network"] or ("Binance ID" if m["auto_verify"] == PAY_PROVIDER else "any"),
                    "is_active": m["is_active"],
                }
                for m in methods
            ],
        }

    async def test_connection(self) -> dict[str, Any]:
        values = await self.settings.values()
        key = (await self.settings.get("binance_api_key")).strip() or self.config.binance_api_key.strip()
        secret = (await self.settings.get("binance_api_secret")).strip() or self.config.binance_api_secret.strip()
        if not key or not secret:
            return {"ok": False, "message": "Add the Binance API key and secret first."}
        try:
            history = await self.client(key, secret).deposit_history(coin=values["binance_coin"], start_time=self._since())
        except BinanceError as exc:
            return {"ok": False, "message": f"{exc} Use a key with 'Enable Reading' and whitelist this server's IP."}
        return {
            "ok": True,
            "message": f"Binance accepted the key. {len(history)} {values['binance_coin']} deposit(s) in the last {LOOKBACK_DAYS} days.",
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
        query = (
            "SELECT d.*, m.auto_verify, m.auto_verify_network, m.min_deposit, m.account_info AS method_account FROM deposits d "
            "JOIN deposit_methods m ON m.id = d.method_id "
            "WHERE d.status = 'pending' AND m.auto_verify = ANY($1) AND d.created_at > now() - $2 * interval '1 day'"
        )
        params: list[Any] = [list(PROVIDERS), LOOKBACK_DAYS]
        if deposit_id is not None:
            query += " AND d.id = $3"
            params.append(deposit_id)
        query += " ORDER BY d.id DESC LIMIT 50"
        async with self.db.connect() as conn:
            return [dict(row) for row in await conn.fetch(query, *params)]

    async def check(self, deposit_id: int) -> dict[str, Any]:
        """Check one pending deposit against Binance. Returns what happened, without raising."""
        pending = await self._pending(deposit_id)
        if not pending:
            return {"checked": False, "credited": False, "detail": "This deposit is not waiting for a Binance check."}
        key, secret = await self._credentials()
        if not key or not secret:
            return {"checked": False, "credited": False, "detail": "Binance checking is switched off."}
        coin = (await self.settings.values())["binance_coin"]
        try:
            return await self._match(pending[0], self.client(key, secret), coin)
        except BinanceError as exc:
            logger.warning("Binance check for deposit #%s failed: %s", deposit_id, exc)
            return {"checked": False, "credited": False, "detail": str(exc)}

    async def recheck_pending(self) -> int:
        """Background pass over deposits still waiting, for payments that confirm after the customer left."""
        pending = await self._pending()
        if not pending:
            return 0
        key, secret = await self._credentials()
        if not key or not secret:
            return 0
        coin = (await self.settings.values())["binance_coin"]
        client = self.client(key, secret)
        checked = 0
        for deposit in pending[:MAX_CHECKS_PER_RUN]:
            try:
                await self._match(deposit, client, coin)
            except BinanceError as exc:
                logger.warning("Binance check for deposit #%s failed: %s", deposit["id"], exc)
                break
            checked += 1
        return checked

    async def claim(self, tg_user_id: int, method_id: int, reference: str) -> dict[str, Any]:
        """A customer says they have paid. What they sent decides the amount, so none is asked for."""
        async with self.db.connect() as conn:
            method = await conn.fetchrow(
                "SELECT * FROM deposit_methods WHERE id = $1 AND is_active = 1 AND auto_verify = ANY($2)",
                method_id,
                list(PROVIDERS),
            )
        if not method:
            raise InvalidInputError("Payment method is no longer available.")
        # The amount stands in until the payment is found; every confirmation sets it from the payment itself.
        deposit_id = await self.deposits.create_request(tg_user_id, method_id, float(method["min_deposit"]), reference)
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE deposits SET admin_note = $1 WHERE id = $2 AND status = 'pending'",
                "Waiting for Binance; the amount is taken from the payment itself.",
                deposit_id,
            )
        result = await self.check(deposit_id)
        return {"deposit_id": deposit_id, **result}

    async def _already_credited(self, transaction_id: str) -> bool:
        async with self.db.connect() as conn:
            return bool(
                await conn.fetchval(
                    "SELECT 1 FROM deposits WHERE lower(btrim(transaction_id)) = lower(btrim($1)) AND status <> 'rejected'",
                    transaction_id,
                )
            )

    async def _match(self, deposit: dict[str, Any], client: BinanceClient, coin: str) -> dict[str, Any]:
        if deposit.get("auto_verify") == PAY_PROVIDER:
            return await self._match_pay(deposit, client, coin)
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
        if canonical.lower() != transaction_id.lower() and await self._already_credited(canonical):
            return await self._flag(deposit, f"payment {canonical} has already been credited")
        return await self._credit(
            deposit,
            received=received,
            coin=coin,
            transaction_id=canonical,
            note=f"Confirmed on Binance: {received:g} {coin} ({NETWORKS.get(network.upper(), network)}), TrxID {transaction_id}",
        )

    async def _match_pay(self, deposit: dict[str, Any], client: BinanceClient, coin: str) -> dict[str, Any]:
        """Binance Pay: the customer names themselves by their Binance ID, and the transfer carries it."""
        payer = str(deposit["transaction_id"]).strip()
        arrivals = [
            row
            for row in await client.pay_transactions(start_time=self._since())
            if str(row.get("orderType") or "").upper() in PAY_INCOMING
            and money(row.get("amount") or 0) > 0
            and str(row.get("currency") or "").upper() == coin.upper()
            and _payer_id(row).strip() == payer
            and self._arrived_in_time(deposit, row.get("transactionTime"))
        ]
        arrivals.sort(key=lambda row: int(row.get("transactionTime") or 0), reverse=True)
        for row in arrivals:
            transaction_id = str(row.get("transactionId") or "").strip()
            if not transaction_id or await self._already_credited(transaction_id):
                continue
            received = money(row.get("amount") or 0)
            return await self._credit(
                deposit,
                received=received,
                coin=coin,
                transaction_id=transaction_id,
                note=f"Confirmed on Binance Pay: {received:g} {coin} from Binance ID {payer}",
            )
        return {
            "checked": True,
            "credited": False,
            "detail": f"No new {coin} transfer from Binance ID {payer} yet.",
        }

    async def _credit(
        self, deposit: dict[str, Any], *, received: float, coin: str, transaction_id: str, note: str
    ) -> dict[str, Any]:
        """The payment decides the amount, and its own id is what the deposit is filed under."""
        rate = float(deposit["rate_to_currency"] or 1) or 1
        # Multiply by exchange rate if rate >= 1 (e.g. 125 BDT per USDT), else divide
        credit = money(received * rate if rate >= 1.0 else received / rate)
        limit = await self.settings.number("max_deposit_limit")
        if credit > limit:
            return await self._flag(deposit, f"{received:g} {coin} is above the single deposit limit")
        if credit < money(deposit.get("min_deposit") or 0):
            return await self._flag(deposit, f"{received:g} {coin} is below this method's smallest top-up")
        if abs(credit - money(deposit["amount"])) > 0.01 or transaction_id.lower() != str(deposit["transaction_id"]).lower():
            try:
                async with self.db.transaction() as conn:
                    updated = await conn.fetchval(
                        "UPDATE deposits SET amount = $1, transaction_id = $2 WHERE id = $3 AND status = 'pending' RETURNING amount",
                        credit,
                        transaction_id,
                        deposit["id"],
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

        success, message, _ = await self.deposits.approve(deposit["id"], note)
        if not success:
            return {"checked": True, "credited": False, "detail": message}
        logger.info("Deposit #%s credited automatically from Binance (%s %s)", deposit["id"], received, coin)
        return {"checked": True, "credited": True, "amount": credit, "detail": f"Credited {credit:.2f} from {received:g} {coin}."}

    async def _flag(self, deposit: dict[str, Any], reason: str) -> dict[str, Any]:
        """Something about the payment is off: leave it for the admin and say why."""
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE deposits SET admin_note = $1 WHERE id = $2 AND status = 'pending'",
                f"Needs a look: {reason}."[:500],
                deposit["id"],
            )
            await record(conn, "deposit_check_flagged", f"Deposit #{deposit['id']}: {reason}")
        return {"checked": True, "credited": False, "detail": f"Needs review: {reason}."}
