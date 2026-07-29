"""JWT validation — the same HS256 token core-api issues.

We don't have a user table here, so the "current user" is simply the numeric
``sub`` claim of a valid token.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from lattice_notifications.config import get_settings

settings = get_settings()

# Points at core-api's login endpoint so Swagger's Authorize button works, but
# the token is validated locally with the shared secret.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="http://localhost:8000/auth/login")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise credentials_error
