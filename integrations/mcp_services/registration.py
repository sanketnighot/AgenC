"""Register MCP HTTP services with the local MCP router."""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)


def register_service(service: str, endpoint: str, router_url: str | None = None) -> bool:
    base = (router_url or os.environ.get("MCP_ROUTER_URL", "http://127.0.0.1:9003")).rstrip(
        "/"
    )
    try:
        r = requests.post(f"{base}/register", json={"service": service, "endpoint": endpoint}, timeout=5)
        if r.status_code == 200:
            logger.info("Registered MCP service %s -> %s", service, endpoint)
            return True
        logger.warning("Register %s failed: %s %s", service, r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("Register %s error: %s", service, e)
    return False


def deregister_service(service: str, router_url: str | None = None) -> None:
    base = (router_url or os.environ.get("MCP_ROUTER_URL", "http://127.0.0.1:9003")).rstrip(
        "/"
    )
    try:
        requests.delete(f"{base}/register/{service}", timeout=5)
        logger.info("Deregistered MCP service %s", service)
    except Exception as e:
        logger.warning("Deregister %s: %s", service, e)
