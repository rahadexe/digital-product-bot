"""Run SubsMarket: ``python -m app [all|web|worker|migrate]``.

``all`` (the default) runs the web API (with Telegram webhook) and delivery worker in one
process. Webhook replicas share the durable PostgreSQL inbox and conversation state
(or Redis when configured). Run only one Telegram poller. ``migrate`` applies database migrations and exits.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import os
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.runtime import ROLES, run


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app", description="Run SubsMarket services.")
    parser.add_argument("role", nargs="?", default="all", choices=ROLES)
    parser.add_argument("--reload", action="store_true", help="Automatically reload on code changes.")
    parser.add_argument("--no-reload", action="store_true", help="Run directly without auto-reload.")
    args = parser.parse_args()

    # Auto-reload is enabled by default in development (unless --no-reload or running migrations)
    cfg = get_settings()
    is_dev = getattr(cfg, "app_env", "development") != "production"
    is_migrate = args.role == "migrate"
    should_reload = not is_migrate and not args.no_reload and (args.reload or is_dev or os.environ.get("APP_RELOAD", "").lower() in ("1", "true", "yes"))
    if should_reload:
        try:
            from watchfiles import run_process
            from app.runtime import run_worker_entrypoint
            app_dir = Path(__file__).resolve().parent
            configure_logging()
            logger = logging.getLogger("app.watcher")
            logger.info("Auto-reload ACTIVE. Watching '%s' for changes...", app_dir)
            run_process(str(app_dir), target=run_worker_entrypoint, args=(args.role,))
            return
        except ImportError:
            logging.getLogger("app").warning("watchfiles not installed; running without auto-reload.")

    from app.runtime import run_worker_entrypoint
    run_worker_entrypoint(args.role)


if __name__ == "__main__":
    main()
