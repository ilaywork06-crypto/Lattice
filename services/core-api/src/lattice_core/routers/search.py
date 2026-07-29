"""Smart global search across the whole system (requirement §7).

One endpoint answers the app-wide search box. It looks through the meaningful
text on items (name, serial, version, project, industry, team, description,
DM"C), plus locations and — for managers only — users, then ranks results so the
most relevant (exact, then prefix, then substring) float to the top.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from lattice_core.database import get_db
from lattice_core.deps import require_viewer
from lattice_core.models import Item, Location, User, UserRole
from lattice_core.schemas import SearchHit, SearchResults

router = APIRouter(prefix="/search", tags=["search"])

_ITEM_LIMIT = 20
_LOC_LIMIT = 8
_USER_LIMIT = 8


def _like(term: str) -> str:
    """Build a LIKE pattern that treats the user's text as literal.

    `%` and `_` are LIKE wildcards, so an unescaped search for "%" matched every
    row in the system and "a_b" quietly matched "axb". Escaping them (backslash
    first, so it isn't doubled) makes the box search for what was typed.
    """
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _score(q: str, *fields: str | None) -> int:
    """Higher is better: exact > prefix > word-boundary > substring."""
    best = 0
    for raw in fields:
        if not raw:
            continue
        f = raw.lower()
        if f == q:
            best = max(best, 100)
        elif f.startswith(q):
            best = max(best, 80)
        elif f" {q}" in f" {f}":
            best = max(best, 65)
        elif q in f:
            best = max(best, 45)
    return best


@router.get("", response_model=SearchResults)
def search(
    q: str = Query(min_length=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_viewer),
):
    term = q.strip()
    ql = term.lower()
    like = _like(term)

    # ── items ──
    item_rows = (
        db.query(Item)
        .options(joinedload(Item.location))
        .filter(Item.is_template.is_(False))
        .filter(
            or_(
                Item.name.ilike(like, escape="\\"),
                Item.serial.ilike(like, escape="\\"),
                Item.version.ilike(like, escape="\\"),
                Item.project.ilike(like, escape="\\"),
                Item.industry.ilike(like, escape="\\"),
                Item.team.ilike(like, escape="\\"),
                Item.description.ilike(like, escape="\\"),
                Item.dmz.ilike(like, escape="\\"),
            )
        )
        .limit(200)
        .all()
    )
    scored_items = sorted(
        item_rows,
        key=lambda i: (
            -_score(
                ql, i.name, i.serial, i.version, i.project, i.industry, i.team,
                i.description, i.dmz,
            ),
            i.name.lower(),
        ),
    )[:_ITEM_LIMIT]
    items = [
        SearchHit(
            kind="item",
            id=i.id,
            title=i.name,
            subtitle=" · ".join(
                p for p in (
                    i.serial,
                    i.version and f"v{i.version}",
                    i.project,
                    i.location.name if i.location else None,
                ) if p
            ) or None,
            badge=i.type.value,
            state=i.state,
            link=f"/items/{i.id}",
        )
        for i in scored_items
    ]

    # ── locations ──
    loc_rows = (
        db.query(Location)
        .filter(
            or_(
                Location.name.ilike(like, escape="\\"),
                Location.building.ilike(like, escape="\\"),
                Location.room.ilike(like, escape="\\"),
            )
        )
        .limit(80)
        .all()
    )
    scored_locs = sorted(
        loc_rows,
        key=lambda loc: (-_score(ql, loc.name, loc.building, loc.room), loc.name.lower()),
    )[:_LOC_LIMIT]
    locations = [
        SearchHit(
            kind="location",
            id=loc.id,
            title=loc.name,
            subtitle=" · ".join(p for p in (loc.building, loc.room) if p) or None,
            badge="location",
            link="/locations",
        )
        for loc in scored_locs
    ]

    # ── users (managers only — mirrors the users endpoint guard) ──
    users: list[SearchHit] = []
    if user.role == UserRole.manager:
        user_rows = (
            db.query(User)
            .filter(
                or_(
                    User.full_name.ilike(like, escape="\\"),
                    User.email.ilike(like, escape="\\"),
                )
            )
            .limit(80)
            .all()
        )
        scored_users = sorted(
            user_rows,
            key=lambda u: (-_score(ql, u.full_name, u.email), u.full_name.lower()),
        )[:_USER_LIMIT]
        users = [
            SearchHit(
                kind="user",
                id=u.id,
                title=u.full_name,
                subtitle=u.email,
                badge=u.role.value,
                link="/users",
            )
            for u in scored_users
        ]

    return SearchResults(
        query=term,
        total=len(items) + len(locations) + len(users),
        items=items,
        locations=locations,
        users=users,
    )
