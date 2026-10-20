"""In-memory per-IP limits for expensive and authentication routes.

``get_remote_address`` reads ``request.client.host``. ProxyHeadersMiddleware
and Uvicorn ``--proxy-headers`` set that host from ``X-Forwarded-For`` when
the connection comes from a trusted proxy. This module does not read the
header itself, and ``rate_limit.conf`` stays empty so ``.env`` is not loaded.
"""

from pathlib import Path

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    headers_enabled=False,
    config_filename=str(Path(__file__).with_name("rate_limit.conf")),
)
