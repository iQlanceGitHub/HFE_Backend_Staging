from typing import Callable, Iterable, Optional

from fastapi import HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.authentication import JWTtoken


class AuthMiddleware(BaseHTTPMiddleware):
    """Simple JWT auth middleware.

    - Skips authentication for configured exempt paths and for docs by default
    - Validates `Authorization: Bearer <token>` header
    - On success, attaches token data to `request.state.user`
    """

    def __init__(
        self,
        app,
        exempt_paths: Optional[Iterable[str]] = None,
        allow_docs: bool = True,
    ) -> None:
        super().__init__(app)
        self.exempt_paths = list(exempt_paths or [])
        if allow_docs:
            self.exempt_paths.extend([
                "/docs",
                "/openapi.json",
                "/redoc",
            ])

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        path: str = request.url.path

        # Allow any path that starts with an exempt prefix
        for prefix in self.exempt_paths:
            if path.startswith(prefix):
                return await call_next(request)

        # Expect Authorization: Bearer <token>
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header.split(" ", 1)[1].strip()

        try:
            credentials_exception = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
            token_data = JWTtoken.verify_token(token, credentials_exception)
            # Attach to request.state for downstream use if needed
            request.state.user = token_data
        except HTTPException as exc:  # Includes expired or invalid token cases
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or {"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)


