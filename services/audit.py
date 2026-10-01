from datetime import date, datetime, time, timedelta
from typing import Optional

from database.db import get_db
from services.permissions import AUDIT_VIEW, normalizuj_identitet, zahtijevaj_dozvolu


def upisi_audit_u_transakciji(
    conn,
    actor,
    akcija: str,
    entitet: str,
    *,
    entitet_id=None,
    detalj: Optional[str] = None,
    smjena_id: Optional[int] = None,
    uredjaj: Optional[str] = None,
) -> None:
    identitet = normalizuj_identitet(actor)
    conn.execute(
        """INSERT INTO logovi
           (vreme, smjena_id, radnik, uredjaj, akcija, user_id, username,
            entitet, entitet_id, detalj)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().replace(microsecond=0).isoformat(),
            smjena_id,
            identitet.ime,
            uredjaj,
            akcija,
            identitet.id,
            identitet.username,
            entitet,
            str(entitet_id) if entitet_id is not None else None,
            detalj,
        ),
    )


def upisi_audit(actor, akcija: str, entitet: str, **kwargs) -> None:
    conn = get_db()
    try:
        upisi_audit_u_transakciji(conn, actor, akcija, entitet, **kwargs)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _datum_granice(vrijednost, kraj_dana=False):
    if isinstance(vrijednost, str):
        vrijednost = date.fromisoformat(vrijednost)
    if isinstance(vrijednost, datetime):
        return vrijednost
    if not isinstance(vrijednost, date):
        raise ValueError("Datum nije ispravan.")
    osnovno = datetime.combine(vrijednost, time.min)
    return osnovno + timedelta(days=1) if kraj_dana else osnovno


def dohvati_audit(
    actor,
    *,
    datum_od=None,
    datum_do=None,
    user_id: Optional[int] = None,
    akcija: Optional[str] = None,
    entitet: Optional[str] = None,
    uredjaj: Optional[str] = None,
    pretraga: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    zahtijevaj_dozvolu(actor, AUDIT_VIEW)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    uslovi = []
    parametri = []
    if datum_od is not None:
        uslovi.append("vreme >= ?")
        parametri.append(_datum_granice(datum_od).isoformat())
    if datum_do is not None:
        uslovi.append("vreme < ?")
        parametri.append(_datum_granice(datum_do, True).isoformat())
    if user_id is not None:
        uslovi.append("user_id = ?")
        parametri.append(user_id)
    if akcija:
        uslovi.append("akcija = ?")
        parametri.append(akcija)
    if entitet:
        uslovi.append("entitet = ?")
        parametri.append(entitet)
    if uredjaj:
        uslovi.append("uredjaj = ?")
        parametri.append(uredjaj)
    if pretraga and pretraga.strip():
        obrazac = f"%{pretraga.strip()}%"
        uslovi.append(
            "(COALESCE(username, '') LIKE ? OR COALESCE(radnik, '') LIKE ? "
            "OR COALESCE(detalj, '') LIKE ? OR COALESCE(akcija, '') LIKE ?)"
        )
        parametri.extend((obrazac, obrazac, obrazac, obrazac))
    gdje = " WHERE " + " AND ".join(uslovi) if uslovi else ""
    conn = get_db()
    ukupno = conn.execute(
        "SELECT COUNT(*) FROM logovi" + gdje, tuple(parametri)
    ).fetchone()[0]
    redovi = conn.execute(
        """SELECT id, vreme, smjena_id, user_id, username, radnik, uredjaj,
                  akcija, entitet, entitet_id, detalj
           FROM logovi"""
        + gdje
        + " ORDER BY vreme DESC, id DESC LIMIT ? OFFSET ?",
        tuple(parametri) + (limit, offset),
    ).fetchall()
    return {
        "stavke": [dict(red) for red in redovi],
        "ukupno": int(ukupno),
        "limit": limit,
        "offset": offset,
    }


def dohvati_audit_opcije(actor) -> dict:
    zahtijevaj_dozvolu(actor, AUDIT_VIEW)
    conn = get_db()
    korisnici = conn.execute(
        """SELECT DISTINCT user_id, COALESCE(username, radnik) AS naziv
           FROM logovi
           WHERE user_id IS NOT NULL
             AND COALESCE(username, radnik) IS NOT NULL
           ORDER BY naziv"""
    ).fetchall()
    akcije = conn.execute(
        "SELECT DISTINCT akcija FROM logovi WHERE akcija IS NOT NULL ORDER BY akcija"
    ).fetchall()
    entiteti = conn.execute(
        "SELECT DISTINCT entitet FROM logovi WHERE entitet IS NOT NULL ORDER BY entitet"
    ).fetchall()
    uredjaji = conn.execute(
        "SELECT DISTINCT uredjaj FROM logovi WHERE uredjaj IS NOT NULL ORDER BY uredjaj"
    ).fetchall()
    return {
        "korisnici": [dict(red) for red in korisnici],
        "akcije": [red[0] for red in akcije],
        "entiteti": [red[0] for red in entiteti],
        "uredjaji": [red[0] for red in uredjaji],
    }
