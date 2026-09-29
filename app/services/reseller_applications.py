"""Service for handling Reseller applications."""

from __future__ import annotations

import logging
from typing import Any

from app.db.database import Database, affected

logger = logging.getLogger("app.services.reseller_applications")


class ResellerApplicationsService:
    def __init__(self, db: Database):
        self.db = db

    async def create_application(
        self,
        user_id: int,
        tg_user_id: int,
        full_name: str,
        telegram_handle: str,
        phone_number: str,
        channel_link: str,
    ) -> int:
        """Create a new reseller application."""
        async with self.db.transaction() as conn:
            # Cancel any existing pending applications for this user
            await conn.execute(
                "UPDATE reseller_applications SET status = 'cancelled', updated_at = now() WHERE tg_user_id = $1 AND status = 'pending'",
                tg_user_id,
            )
            app_id = await conn.fetchval(
                """
                INSERT INTO reseller_applications (
                    user_id, tg_user_id, full_name, telegram_handle, phone_number, channel_link, status
                ) VALUES ($1, $2, $3, $4, $5, $6, 'pending')
                RETURNING id
                """,
                user_id,
                tg_user_id,
                full_name.strip(),
                telegram_handle.strip(),
                phone_number.strip(),
                channel_link.strip(),
            )
            return int(app_id)

    async def get_application(self, app_id: int) -> dict[str, Any] | None:
        """Retrieve single application by ID with user info."""
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                """
                SELECT ra.*, u.username, u.first_name, u.last_name, u.rank, u.balance
                FROM reseller_applications ra
                LEFT JOIN users u ON u.id = ra.user_id
                WHERE ra.id = $1
                """,
                app_id,
            )
            return dict(row) if row else None

    async def get_pending_by_user(self, tg_user_id: int) -> dict[str, Any] | None:
        """Retrieve active pending application for user if one exists."""
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM reseller_applications
                WHERE tg_user_id = $1 AND status = 'pending'
                ORDER BY id DESC LIMIT 1
                """,
                tg_user_id,
            )
            return dict(row) if row else None

    async def cancel_application(self, app_id: int, tg_user_id: int) -> bool:
        """Cancel a pending application on behalf of the user."""
        async with self.db.transaction() as conn:
            status = await conn.execute(
                "UPDATE reseller_applications SET status = 'cancelled', updated_at = now() WHERE id = $1 AND tg_user_id = $2 AND status = 'pending'",
                app_id,
                tg_user_id,
            )
            return bool(affected(status))

    async def list_applications(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List applications with optional status filter."""
        where = "WHERE 1=1"
        params: list[Any] = []
        if status and status.lower() != "all":
            params.append(status.lower().strip())
            where += f" AND ra.status = ${len(params)}"

        params.append(limit)
        limit_idx = len(params)
        params.append(offset)
        offset_idx = len(params)

        query = f"""
            SELECT ra.*, u.username, u.first_name, u.last_name, u.rank, u.balance
            FROM reseller_applications ra
            LEFT JOIN users u ON u.id = ra.user_id
            {where}
            ORDER BY
                CASE WHEN ra.status = 'pending' THEN 0 ELSE 1 END,
                ra.created_at DESC
            LIMIT ${limit_idx} OFFSET ${offset_idx}
        """
        async with self.db.connect() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

    async def count_applications(self, status: str | None = None) -> int:
        """Count total applications."""
        where = "WHERE 1=1"
        params: list[Any] = []
        if status and status.lower() != "all":
            params.append(status.lower().strip())
            where += f" AND status = ${len(params)}"

        async with self.db.connect() as conn:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM reseller_applications {where}", *params)
            return int(count or 0)

    async def get_summary(self) -> dict[str, int]:
        """Get application counts for badges/dashboard."""
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) AS pending,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) AS approved,
                    COUNT(CASE WHEN status = 'rejected' THEN 1 END) AS rejected
                FROM reseller_applications
                """
            )
            if not row:
                return {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
            return {
                "total": int(row["total"] or 0),
                "pending": int(row["pending"] or 0),
                "approved": int(row["approved"] or 0),
                "rejected": int(row["rejected"] or 0),
            }

    async def approve_application(self, app_id: int, reviewed_by: int | None = None, notes: str = "") -> dict[str, Any] | None:
        """Approve application, promote user rank to 'reseller'."""
        async with self.db.transaction() as conn:
            app = await conn.fetchrow("SELECT * FROM reseller_applications WHERE id = $1 FOR UPDATE", app_id)
            if not app:
                return None

            status = await conn.execute(
                """
                UPDATE reseller_applications
                SET status = 'approved',
                    reviewed_by = $1,
                    reviewed_at = now(),
                    admin_notes = COALESCE(NULLIF($2, ''), admin_notes),
                    updated_at = now()
                WHERE id = $3
                """,
                reviewed_by,
                notes.strip(),
                app_id,
            )
            if not affected(status):
                return None

            # Promote user rank to reseller
            await conn.execute(
                "UPDATE users SET rank = 'reseller', updated_at = now() WHERE id = $1",
                app["user_id"],
            )
            return dict(app)

    async def reject_application(self, app_id: int, reviewed_by: int | None = None, reason: str = "") -> dict[str, Any] | None:
        """Reject application with reason."""
        async with self.db.transaction() as conn:
            app = await conn.fetchrow("SELECT * FROM reseller_applications WHERE id = $1 FOR UPDATE", app_id)
            if not app:
                return None

            status = await conn.execute(
                """
                UPDATE reseller_applications
                SET status = 'rejected',
                    reviewed_by = $1,
                    reviewed_at = now(),
                    admin_notes = $2,
                    updated_at = now()
                WHERE id = $3
                """,
                reviewed_by,
                reason.strip(),
                app_id,
            )
            if not affected(status):
                return None
            return dict(app)
