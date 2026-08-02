"""Authentication: OAuth2 password flow issuing JWTs."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import get_current_user
from lattice_core.models import User
from lattice_core.schemas import LoginHintOut, Token, UserOut
from lattice_core.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    user = db.query(User).filter(User.email == form.username).first()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")
    token = create_access_token(subject=str(user.id), role=user.role.value)
    return Token(
        access_token=token,
        role=user.role,
        full_name=user.full_name,
        user_id=user.id,
    )


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)) -> User:
    return current


@router.get("/login-hints", response_model=list[LoginHintOut])
def login_hints(db: Session = Depends(get_db)) -> list[LoginHintOut]:
    """Sign-in shortcuts a manager chose to offer (§8).

    Unauthenticated by necessity — it feeds the login page, before anyone has a
    token. That constraint *is* the design: an account appears only once a
    manager marks it visible, and its password is included only where a manager
    explicitly published one. Deactivated accounts drop out on their own, so
    disabling a user also retires its shortcut.
    """
    users = (
        db.query(User)
        .filter(User.login_hint_visible.is_(True), User.is_active.is_(True))
        .order_by(User.full_name)
        .all()
    )
    return [
        LoginHintOut(
            full_name=u.full_name,
            email=u.email,
            role=u.role,
            password=u.login_hint_password,
        )
        for u in users
    ]
