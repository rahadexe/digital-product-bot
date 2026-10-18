"""Backward-compatible Digital Mart entry point using the shared supplier client."""

from __future__ import annotations

from typing import Any

from app.services.suppliers import DigitalMartClient, SupplierError


class UpstreamResellerService(DigitalMartClient):
    async def get_account(self) -> dict[str, Any] | None:
        try:
            data = await self._get_json("me")
            if not isinstance(data, dict) or not isinstance(data.get("user"), dict):
                return None
            return data
        except SupplierError:
            return None
