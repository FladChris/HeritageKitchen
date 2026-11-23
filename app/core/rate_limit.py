import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.config import settings

_attempts_by_ip: dict[str, list[float]] = defaultdict(list)
_attempts_lock = Lock()


def enforce_login_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()

    with _attempts_lock:
        attempts = _attempts_by_ip[client_ip]
        attempts[:] = [
            attempt
            for attempt in attempts
            if now - attempt < settings.login_rate_limit_window_seconds
        ]

        if len(attempts) >= settings.login_rate_limit_max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again later.",
            )

        attempts.append(now)
