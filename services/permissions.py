from collections.abc import Mapping

from database.db import get_db
from models.user import UserIdentity


ROLA_ADMIN = "admin"
ROLA_MANAGER = "manager"
ROLA_RADNIK = "radnik"
ROLE = (ROLA_ADMIN, ROLA_MANAGER, ROLA_RADNIK)

POS_USE = "pos.use"
SHIFT_OPEN = "shift.open"
SHIFT_CLOSE = "shift.close"
RESERVATION_MANAGE = "reservation.manage"
DASHBOARD_VIEW = "dashboard.view"
REPORT_VIEW = "report.view"
SESSION_HISTORY_VIEW = "session_history.view"
AUDIT_VIEW = "audit.view"
DEVICE_MANAGE = "device.manage"
ARTICLE_MANAGE = "article.manage"
USER_MANAGE = "user.manage"

SVE_DOZVOLE = frozenset({
    POS_USE,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    RESERVATION_MANAGE,
    DASHBOARD_VIEW,
    REPORT_VIEW,
    SESSION_HISTORY_VIEW,
    AUDIT_VIEW,
    DEVICE_MANAGE,
    ARTICLE_MANAGE,
    USER_MANAGE,
})

ROLE_PERMISSIONS = {
    ROLA_ADMIN: SVE_DOZVOLE,
    ROLA_MANAGER: frozenset({
        POS_USE,
        SHIFT_OPEN,
        SHIFT_CLOSE,
        RESERVATION_MANAGE,
        DASHBOARD_VIEW,
        REPORT_VIEW,
        SESSION_HISTORY_VIEW,
        AUDIT_VIEW,
    }),
    ROLA_RADNIK: frozenset({
        POS_USE,
        SHIFT_OPEN,
        SHIFT_CLOSE,
        RESERVATION_MANAGE,
        DASHBOARD_VIEW,
    }),
}


def normalizuj_identitet(actor) -> UserIdentity:
    if isinstance(actor, UserIdentity):
        return actor
    if isinstance(actor, Mapping):
        try:
            return UserIdentity(
                id=int(actor["id"]),
                username=str(actor.get("username", actor.get("korisnicko_ime"))),
                ime=str(actor["ime"]),
                rola=str(actor["rola"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PermissionError("Neispravan identitet korisnika.") from exc
    raise PermissionError("Korisnik nije prijavljen.")


def ima_dozvolu(rola_ili_actor, dozvola: str) -> bool:
    if isinstance(rola_ili_actor, str):
        rola = rola_ili_actor
    else:
        try:
            rola = normalizuj_identitet(rola_ili_actor).rola
        except PermissionError:
            return False
    return dozvola in ROLE_PERMISSIONS.get(rola, frozenset())


def zahtijevaj_dozvolu(actor, dozvola: str) -> UserIdentity:
    identitet = normalizuj_identitet(actor)
    red = get_db().execute(
        """SELECT id, korisnicko_ime, ime, rola, aktivan
           FROM korisnici WHERE id = ?""",
        (identitet.id,),
    ).fetchone()
    if red is None or not red["aktivan"]:
        raise PermissionError("Korisnik nije aktivan ili više ne postoji.")
    aktuelni = UserIdentity.iz_reda(red)
    if not ima_dozvolu(aktuelni.rola, dozvola):
        raise PermissionError("Nemate dozvolu za ovu akciju.")
    return aktuelni
