"""FastAPI dependencies: current-user resolution and role guards."""

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.models import User, UserRole
from lattice_core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_ROLE_RANK = {UserRole.viewer: 0, UserRole.editor: 1, UserRole.manager: 2}


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError):
        raise credentials_error
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_min_role(minimum: UserRole) -> Callable[[User], User]:
    def guard(user: User = Depends(get_current_user)) -> User:
        if _ROLE_RANK[user.role] < _ROLE_RANK[minimum]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires at least '{minimum.value}' role",
            )
        return user

    return guard


require_viewer = require_min_role(UserRole.viewer)
require_editor = require_min_role(UserRole.editor)
require_manager = require_min_role(UserRole.manager)
