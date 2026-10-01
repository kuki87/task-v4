from datetime import datetime
from threading import RLock

from database.db import get_db
from models.user import UserIdentity
from services.audit import upisi_audit_u_transakciji
from services.auth import (
    AUTH_NEDOSTAJE,
    AUTH_OSTECEN,
    AUTH_SPREMAN,
    napravi_password_hash,
    obrisi_legacy_auth_u_transakciji,
    provjeri_legacy_admin_lozinku,
    provjeri_password_hash,
    stanje_admin_lozinke,
)
from services.permissions import (
    ROLE,
    ROLA_ADMIN,
    USER_MANAGE,
    zahtijevaj_dozvolu,
)


_users_lock = RLock()


def broj_korisnika() -> int:
    return int(get_db().execute("SELECT COUNT(*) FROM korisnici").fetchone()[0])


def stanje_prvog_pokretanja() -> str:
    if broj_korisnika() > 0:
        return "login"
    legacy = stanje_admin_lozinke()
    if legacy == AUTH_NEDOSTAJE:
        return "novi_admin"
    if legacy == AUTH_SPREMAN:
        return "migracija_legacy"
    if legacy == AUTH_OSTECEN:
        return "legacy_ostecen"
    return "legacy_ostecen"


def _validiraj_podatke(korisnicko_ime, ime, rola, lozinka):
    username = str(korisnicko_ime or "").strip()
    prikazno_ime = str(ime or "").strip()
    if not username:
        raise ValueError("Korisničko ime je obavezno.")
    if not prikazno_ime:
        raise ValueError("Ime je obavezno.")
    if rola not in ROLE:
        raise ValueError("Nepoznata rola korisnika.")
    return username, prikazno_ime, napravi_password_hash(lozinka)


def _insert_korisnik(conn, username, ime, password_hash, rola):
    sada = datetime.now().replace(microsecond=0).isoformat()
    cursor = conn.execute(
        """INSERT INTO korisnici
           (korisnicko_ime, ime, password_hash, rola, aktivan, kreiran, azuriran)
           VALUES (?, ?, ?, ?, 1, ?, ?)""",
        (username, ime, password_hash, rola, sada, sada),
    )
    return int(cursor.lastrowid)


def kreiraj_prvog_admina(korisnicko_ime: str, ime: str, lozinka: str) -> UserIdentity:
    username, ime, password_hash = _validiraj_podatke(
        korisnicko_ime, ime, ROLA_ADMIN, lozinka
    )
    with _users_lock:
        conn = get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT COUNT(*) FROM korisnici").fetchone()[0]:
                raise ValueError("Prvi korisnik je već kreiran.")
            if stanje_admin_lozinke() != AUTH_NEDOSTAJE:
                raise ValueError("Postoji legacy admin pristup koji prvo treba migrirati.")
            user_id = _insert_korisnik(conn, username, ime, password_hash, ROLA_ADMIN)
            actor = UserIdentity(user_id, username, ime, ROLA_ADMIN)
            upisi_audit_u_transakciji(
                conn, actor, "USER_CREATED", "korisnik",
                entitet_id=user_id, detalj="Kreiran prvi admin korisnik."
            )
            conn.commit()
            return actor
        except Exception:
            conn.rollback()
            raise


def migriraj_legacy_admin(
    legacy_lozinka: str,
    korisnicko_ime: str,
    ime: str,
    nova_lozinka: str,
) -> UserIdentity:
    username, ime, password_hash = _validiraj_podatke(
        korisnicko_ime, ime, ROLA_ADMIN, nova_lozinka
    )
    with _users_lock:
        conn = get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT COUNT(*) FROM korisnici").fetchone()[0]:
                raise ValueError("Korisnici već postoje.")
            if stanje_admin_lozinke() != AUTH_SPREMAN:
                raise ValueError("Legacy admin zapis nije spreman za migraciju.")
            if not provjeri_legacy_admin_lozinku(legacy_lozinka):
                raise ValueError("Postojeća admin lozinka nije ispravna.")
            user_id = _insert_korisnik(conn, username, ime, password_hash, ROLA_ADMIN)
            actor = UserIdentity(user_id, username, ime, ROLA_ADMIN)
            obrisi_legacy_auth_u_transakciji(conn)
            upisi_audit_u_transakciji(
                conn, actor, "LEGACY_AUTH_MIGRATED", "korisnik",
                entitet_id=user_id, detalj="Legacy admin pristup migriran."
            )
            conn.commit()
            return actor
        except Exception:
            conn.rollback()
            raise


def prijavi_korisnika(korisnicko_ime: str, lozinka: str):
    username = str(korisnicko_ime or "").strip()
    conn = get_db()
    red = conn.execute(
        """SELECT id, korisnicko_ime, ime, password_hash, rola, aktivan
           FROM korisnici WHERE korisnicko_ime = ? COLLATE NOCASE""",
        (username,),
    ).fetchone()
    if red is None or not red["aktivan"]:
        return None
    ispravno, treba_rehash = provjeri_password_hash(lozinka, red["password_hash"])
    if not ispravno:
        return None
    actor = UserIdentity.iz_reda(red)
    sada = datetime.now().replace(microsecond=0).isoformat()
    try:
        if treba_rehash:
            conn.execute(
                "UPDATE korisnici SET password_hash = ?, azuriran = ? WHERE id = ?",
                (napravi_password_hash(lozinka), sada, actor.id),
            )
        conn.execute(
            "UPDATE korisnici SET zadnja_prijava = ? WHERE id = ?", (sada, actor.id)
        )
        upisi_audit_u_transakciji(
            conn, actor, "LOGIN_SUCCESS", "auth", entitet_id=actor.id,
            detalj="Uspješna prijava."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return actor


def odjavi_korisnika(actor) -> None:
    from services.audit import upisi_audit

    upisi_audit(actor, "LOGOUT", "auth", entitet_id=actor.id, detalj="Odjava.")


def dohvati_korisnike(actor, *, limit: int = 200, offset: int = 0) -> dict:
    zahtijevaj_dozvolu(actor, USER_MANAGE)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    conn = get_db()
    ukupno = conn.execute("SELECT COUNT(*) FROM korisnici").fetchone()[0]
    redovi = conn.execute(
        """SELECT id, korisnicko_ime, ime, rola, aktivan, kreiran, azuriran,
                  zadnja_prijava
           FROM korisnici ORDER BY korisnicko_ime COLLATE NOCASE, id
           LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
    return {"stavke": [dict(r) for r in redovi], "ukupno": ukupno,
            "limit": limit, "offset": offset}


def kreiraj_korisnika(actor, korisnicko_ime, ime, lozinka, rola) -> int:
    actor = zahtijevaj_dozvolu(actor, USER_MANAGE)
    username, ime, password_hash = _validiraj_podatke(
        korisnicko_ime, ime, rola, lozinka
    )
    conn = get_db()
    try:
        user_id = _insert_korisnik(conn, username, ime, password_hash, rola)
        upisi_audit_u_transakciji(
            conn, actor, "USER_CREATED", "korisnik", entitet_id=user_id,
            detalj=f"Kreiran korisnik {username}, rola {rola}."
        )
        conn.commit()
        return user_id
    except Exception:
        conn.rollback()
        raise


def _dohvati_korisnika(conn, user_id):
    red = conn.execute(
        "SELECT id, korisnicko_ime, ime, rola, aktivan FROM korisnici WHERE id = ?",
        (user_id,),
    ).fetchone()
    if red is None:
        raise ValueError("Korisnik ne postoji.")
    return red


def _provjeri_posljednjeg_admina(conn, red):
    if red["rola"] != ROLA_ADMIN or not red["aktivan"]:
        return
    broj = conn.execute(
        "SELECT COUNT(*) FROM korisnici WHERE rola = ? AND aktivan = 1",
        (ROLA_ADMIN,),
    ).fetchone()[0]
    if broj <= 1:
        raise ValueError("Posljednji aktivni admin mora ostati aktivan admin.")


def promijeni_ime(actor, user_id: int, novo_ime: str) -> None:
    actor = zahtijevaj_dozvolu(actor, USER_MANAGE)
    novo_ime = str(novo_ime or "").strip()
    if not novo_ime:
        raise ValueError("Ime je obavezno.")
    conn = get_db()
    try:
        red = _dohvati_korisnika(conn, user_id)
        conn.execute(
            "UPDATE korisnici SET ime = ?, azuriran = ? WHERE id = ?",
            (novo_ime, datetime.now().isoformat(), user_id),
        )
        upisi_audit_u_transakciji(
            conn, actor, "USER_NAME_CHANGED", "korisnik", entitet_id=user_id,
            detalj=f"Promijenjeno ime korisnika {red['korisnicko_ime']}."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def promijeni_rolu(actor, user_id: int, nova_rola: str) -> None:
    actor = zahtijevaj_dozvolu(actor, USER_MANAGE)
    if nova_rola not in ROLE:
        raise ValueError("Nepoznata rola korisnika.")
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        red = _dohvati_korisnika(conn, user_id)
        if red["rola"] == ROLA_ADMIN and nova_rola != ROLA_ADMIN:
            _provjeri_posljednjeg_admina(conn, red)
        conn.execute(
            "UPDATE korisnici SET rola = ?, azuriran = ? WHERE id = ?",
            (nova_rola, datetime.now().isoformat(), user_id),
        )
        upisi_audit_u_transakciji(
            conn, actor, "USER_ROLE_CHANGED", "korisnik", entitet_id=user_id,
            detalj=f"Rola: {red['rola']} → {nova_rola}."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def postavi_aktivnost(actor, user_id: int, aktivan: bool) -> None:
    actor = zahtijevaj_dozvolu(actor, USER_MANAGE)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        red = _dohvati_korisnika(conn, user_id)
        if red["aktivan"] and not aktivan:
            _provjeri_posljednjeg_admina(conn, red)
        conn.execute(
            "UPDATE korisnici SET aktivan = ?, azuriran = ? WHERE id = ?",
            (int(bool(aktivan)), datetime.now().isoformat(), user_id),
        )
        akcija = "USER_ACTIVATED" if aktivan else "USER_DEACTIVATED"
        upisi_audit_u_transakciji(
            conn, actor, akcija, "korisnik", entitet_id=user_id,
            detalj=f"Korisnik {red['korisnicko_ime']}."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def promijeni_lozinku_korisnika(actor, user_id: int, nova_lozinka: str) -> None:
    actor = zahtijevaj_dozvolu(actor, USER_MANAGE)
    password_hash = napravi_password_hash(nova_lozinka)
    conn = get_db()
    try:
        red = _dohvati_korisnika(conn, user_id)
        conn.execute(
            "UPDATE korisnici SET password_hash = ?, azuriran = ? WHERE id = ?",
            (password_hash, datetime.now().isoformat(), user_id),
        )
        upisi_audit_u_transakciji(
            conn, actor, "USER_PASSWORD_CHANGED", "korisnik",
            entitet_id=user_id,
            detalj=f"Postavljena nova lozinka za {red['korisnicko_ime']}."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
