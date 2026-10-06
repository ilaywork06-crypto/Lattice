"""User & permission management (manager only, requirement §8)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_manager, require_viewer
from lattice_core.models import ChangeRequest, FieldMode, FieldType, TemplateField, User, UserRole
from lattice_core.schemas import UserBrief, UserCreate, UserOut, UserUpdate
from lattice_core.security import hash_password
from lattice_core.services import field_groups as field_groups_svc
from lattice_core.services.audit import record_audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    """Viewer+ by design — see CONTRACT.md §Users. Note this is deliberately
    *wider* than /search, which withholds `users[]` from non-managers."""
    return db.query(User).order_by(User.full_name).all()


@router.get("/managers", response_model=list[UserBrief])
def list_managers(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return db.query(User).filter(User.role == UserRole.manager, User.is_active).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_manager),
):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    record_audit(
        db,
        action="user.create",
        summary=f"Created user {data.email} ({data.role.value})",
        user=current,
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_manager),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.password:
        user.hashed_password = hash_password(data.password)
    if data.login_hint_visible is not None:
        user.login_hint_visible = data.login_hint_visible
    if data.login_hint_password is not None:
        # An empty string is the explicit "stop publishing the password" signal —
        # `None` here only ever means "the caller didn't mention this field".
        user.login_hint_password = data.login_hint_password.strip() or None
    record_audit(
        db,
        action="user.update",
        summary=f"Updated user {user.email}",
        user=current,
        # Publishing an account on the sign-in screen is a security-relevant
        # decision, so it lands in the audit log as its own fact (§10).
        details={
            "login_hint_visible": user.login_hint_visible,
            "login_hint_password_set": user.has_login_hint_password,
        },
    )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_manager),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current.id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")
    # change_requests.proposed_by is a non-nullable FK with no ON DELETE rule —
    # every other user reference nulls out, but a proposal must keep its author
    # for the audit trail (§10). Removing the row would raise an IntegrityError
    # and surface as a 500, so say plainly what to do instead.
    proposals = (
        db.query(func.count(ChangeRequest.id))
        .filter(ChangeRequest.proposed_by == user.id)
        .scalar()
        or 0
    )
    if proposals:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{user.full_name} has {proposals} change request(s) on record and "
                "cannot be deleted without breaking the audit trail. Deactivate the "
                "account instead — it blocks sign-in and keeps the history intact."
            ),
        )
    _forget_in_templates(db, user.id)
    field_groups_svc.forget_reference(
        db, {FieldType.managers, FieldType.responsible}, user.id
    )
    record_audit(
        db, action="user.delete", summary=f"Deleted user {user.email}", user=current
    )
    db.delete(user)
    db.commit()


def _forget_in_templates(db: Session, user_id: int) -> None:
    """Template fields hold user ids in JSON (fixed values, list options); a
    foreign key can't reach into those, so drop the deleted user by hand."""
    for f in db.query(TemplateField).filter(
        TemplateField.field_type.in_([FieldType.managers, FieldType.responsible])
    ):
        options = (f.config or {}).get("options")
        if options and user_id in options:
            f.config = {**f.config, "options": [o for o in options if o != user_id]}
        if f.mode == FieldMode.fixed:
            if f.fixed_value == user_id:
                f.fixed_value = None
            elif isinstance(f.fixed_value, list) and user_id in f.fixed_value:
                f.fixed_value = [v for v in f.fixed_value if v != user_id]
