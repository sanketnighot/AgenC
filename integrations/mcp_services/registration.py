"""Register MCP HTTP services with the local MCP router."""

from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

# Router may still be binding right after `systemctl restart mcp-router`; sidecars need retries.
_REGISTER_ATTEMPTS = int(os.environ.get("MCP_REGISTER_ATTEMPTS", "40"))
_REGISTER_DELAY_SEC = float(os.environ.get("MCP_REGISTER_DELAY_SEC", "0.25"))


def register_service(service: str, endpoint: str, router_url: str | None = None) -> bool:
    base = (router_url or os.environ.get("MCP_ROUTER_URL", "http://127.0.0.1:9003")).rstrip(
        "/"
    )
    url = f"{base}/register"
    payload = {"service": service, "endpoint": endpoint}

    for attempt in range(1, _REGISTER_ATTEMPTS + 1):
        try:
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                logger.info("Registered MCP service %s -> %s", service, endpoint)
                return True
            transient = r.status_code >= 500 or r.status_code == 429
            if transient and attempt < _REGISTER_ATTEMPTS:
                logger.warning(
                    "Register %s HTTP %s (attempt %s/%s), retrying...",
                    service,
                    r.status_code,
                    attempt,
                    _REGISTER_ATTEMPTS,
                )
                time.sleep(_REGISTER_DELAY_SEC)
                continue
            logger.warning("Register %s failed: %s %s", service, r.status_code, r.text[:200])
            return False
        except (requests.RequestException, OSError) as e:
            if attempt < _REGISTER_ATTEMPTS:
                logger.warning(
                    "Register %s error %s (attempt %s/%s): %s",
                    service,
                    type(e).__name__,
                    attempt,
                    _REGISTER_ATTEMPTS,
                    e,
                )
                time.sleep(_REGISTER_DELAY_SEC)
                continue
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
