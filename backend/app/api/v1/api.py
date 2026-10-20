"""Version 1 API router mounted at ``/api/v1``.

Analytics routes are included here through :mod:`app.api.v1.router` and are
served at ``/api/v1/analytics``.
"""

from .router import api_router

__all__ = ["api_router"]
