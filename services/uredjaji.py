from datetime import datetime
from typing import Optional
from database.db import get_db
from services.audit import dohvati_audit, upisi_audit_u_transakciji
from services.permissions import DEVICE_MANAGE, zahtijevaj_dozvolu
from services.rezervacije import STATUS_REZERVISANO, STATUS_STIGAO


def ucitaj_uredjaje() -> list:
    conn = get_db()
    return conn.execute(
        "SELECT id, ime, cena, tip, grupa FROM uredjaji ORDER BY grupa, ime"
    ).fetchall()


def dodaj_uredjaj(
    ime: str, cena: float, tip: str, grupa: str = "Classic", *, actor
) -> None:
    actor = zahtijevaj_dozvolu(actor, DEVICE_MANAGE)
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO uredjaji (ime, cena, tip, grupa) VALUES (?, ?, ?, ?)",
            (ime, cena, tip, grupa)
        )
        upisi_audit_u_transakciji(
            conn, actor, "DEVICE_CREATED", "uredjaj",
            entitet_id=cursor.lastrowid, uredjaj=ime,
            detalj=f"Tip {tip}, grupa {grupa}, cijena {cena:.2f} KM/h."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def brisi_uredjaj(uid: int, *, actor) -> None:
    actor = zahtijevaj_dozvolu(actor, DEVICE_MANAGE)
    conn = get_db()
    uredjaj = conn.execute(
        "SELECT ime FROM uredjaji WHERE id = ?", (uid,)
    ).fetchone()
    if uredjaj is None:
        raise ValueError("Uređaj ne postoji.")
    rezervacije = conn.execute(
        "SELECT COUNT(*) FROM rezervacije WHERE uredjaj_id = ?", (uid,)
    ).fetchone()[0]
    if rezervacije:
        aktivne = conn.execute(
            """SELECT COUNT(*) FROM rezervacije
               WHERE uredjaj_id = ? AND status IN (?, ?) AND kraj > ?""",
            (uid, STATUS_REZERVISANO, STATUS_STIGAO, datetime.now().isoformat()),
        ).fetchone()[0]
        if aktivne:
            raise ValueError(
                "Uređaj ima buduću ili aktivnu rezervaciju i ne može biti obrisan."
            )
        raise ValueError("Uređaj ima historiju rezervacija i ne može biti obrisan.")
    try:
        conn.execute("DELETE FROM uredjaji WHERE id = ?", (uid,))
        upisi_audit_u_transakciji(
            conn, actor, "DEVICE_DELETED", "uredjaj", entitet_id=uid,
            uredjaj=uredjaj["ime"], detalj="Uređaj obrisan."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def postavi_cijenu_grupe(grupa: str, cena: float, *, actor) -> int:
    actor = zahtijevaj_dozvolu(actor, DEVICE_MANAGE)
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE uredjaji SET cena = ? WHERE grupa = ?", (cena, grupa)
        )
        upisi_audit_u_transakciji(
            conn, actor, "DEVICE_GROUP_PRICE_CHANGED", "uredjaj_grupa",
            entitet_id=grupa,
            detalj=f"Cijena grupe {grupa}: {cena:.2f} KM/h; uređaja: {cursor.rowcount}."
        )
        conn.commit()
        return cursor.rowcount
    except Exception:
        conn.rollback()
        raise


def seed_uredjaje_ako_prazno(podrazumijevani: list, *, actor) -> None:
    actor = zahtijevaj_dozvolu(actor, DEVICE_MANAGE)
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM uredjaji").fetchone()[0] != 0:
        return
    try:
        for ime, cena, tip, grupa in podrazumijevani:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO uredjaji (ime, cena, tip, grupa)
                   VALUES (?, ?, ?, ?)""",
                (ime, cena, tip, grupa),
            )
            if cursor.rowcount:
                upisi_audit_u_transakciji(
                    conn, actor, "DEVICE_CREATED", "uredjaj",
                    entitet_id=cursor.lastrowid, uredjaj=ime,
                    detalj=(
                        f"Početno kreiranje; tip {tip}, grupa {grupa}, "
                        f"cijena {cena:.2f} KM/h."
                    ),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def dohvati_aktivne_sesije(smjena_id: int) -> list:
    conn = get_db()
    return conn.execute(
        """SELECT uredjaj, vreme_starta, tip, limit_sekundi FROM sesije_log
           WHERE smjena_id = ? AND vreme_kraja IS NULL""",
        (smjena_id,)
    ).fetchall()


def ucitaj_logove(actor, filter_datum: Optional[str] = None) -> list:
    rezultat = dohvati_audit(
        actor,
        datum_od=filter_datum,
        datum_do=filter_datum,
        limit=200,
    )
    return rezultat["stavke"]
