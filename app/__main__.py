"""Run SubsMarket: ``python -m app [all|web|worker|migrate]``.

``all`` (the default) runs the web API (with Telegram webhook) and delivery worker in one
process. Scaled deployments may run several ``web`` replicas only with REDIS_URL set
(FSM state must be shared); otherwise run one. ``migrate`` applies database migrations and exits.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.runtime import ROLES, run


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app", description="Run SubsMarket services.")
    parser.add_argument("role", nargs="?", default="all", choices=ROLES)
    args = parser.parse_args()
    configure_logging()
    try:
        asyncio.run(run(args.role, get_settings()))
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.getLogger("app").critical("SubsMarket stopped after a fatal error.", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
