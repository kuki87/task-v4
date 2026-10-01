from datetime import datetime
from typing import Dict, List, Optional, Tuple
from database.db import get_db
from models.session_state import SessionState
from models.artikal import Artikal
from services.pazar import naplati_uredjaj
from services.audit import upisi_audit_u_transakciji
from services.permissions import SHIFT_CLOSE, SHIFT_OPEN, zahtijevaj_dozvolu


AktivnaSesija = Tuple[SessionState, List[Artikal], float]


def otvori_smjenu(actor) -> int:
    actor = zahtijevaj_dozvolu(actor, SHIFT_OPEN)
    aktivna = dohvati_aktivnu_smjenu()
    if aktivna:
        raise ValueError(
        f"Smjena radnika '{aktivna['radnik']}' je već otvorena!"
        )
    conn = get_db()
    now = datetime.now().isoformat()
    try:
        cursor = conn.execute(
            """INSERT INTO smjene (pocetak, radnik, pazar, user_id)
               VALUES (?, ?, 0.0, ?)""",
            (now, actor.ime, actor.id)
        )
        smjena_id = int(cursor.lastrowid)
        upisi_audit_u_transakciji(
            conn, actor, "SHIFT_OPENED", "smjena", entitet_id=smjena_id,
            smjena_id=smjena_id, detalj="Smjena otvorena."
        )
        conn.commit()
        return smjena_id
    except Exception:
        conn.rollback()
        raise


def zatvori_smjenu(
    smjena_id: int,
    aktivne_sesije: Dict[str, AktivnaSesija],
    sank_kosarica: List[Artikal],
    *,
    actor,
) -> dict:
    actor = zahtijevaj_dozvolu(actor, SHIFT_CLOSE)
    conn = get_db()
    now = datetime.now().isoformat()

    naplacene_sesije = {}
    try:
        for ime_uredjaja, (session, kosarica, cena_po_satu) in aktivne_sesije.items():
            naplacene_sesije[ime_uredjaja] = naplati_uredjaj(
                ime_uredjaja,
                session,
                kosarica,
                cena_po_satu,
                smjena_id,
                actor=actor,
                commit=False,
            )

        row = conn.execute(
            "SELECT COALESCE(SUM(iznos), 0) AS ukupno FROM pazar_arhiva WHERE smjena_id = ?",
            (smjena_id,)
        ).fetchone()
        iznos_pazara = round(float(row["ukupno"]), 2)

        conn.execute(
            "UPDATE smjene SET kraj = ?, pazar = ? WHERE id = ?",
            (now, iznos_pazara, smjena_id)
        )
        upisi_audit_u_transakciji(
            conn, actor, "SHIFT_CLOSED", "smjena", entitet_id=smjena_id,
            smjena_id=smjena_id, detalj=f"Pazar {iznos_pazara:.2f} KM."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "smjena_id": smjena_id,
        "kraj": now,
        "pazar": iznos_pazara,
        "naplacene_sesije": naplacene_sesije,
        "sank_kosarica": sank_kosarica,
    }


def dohvati_aktivnu_smjenu() -> Optional[dict]:
    conn = get_db()
    row = conn.execute(
        """SELECT id, pocetak, radnik, user_id
           FROM smjene WHERE kraj IS NULL ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    if row:
        return dict(row)
    return None


def preuzmi_smjenu(smjena_id: int, actor) -> None:
    actor = zahtijevaj_dozvolu(actor, SHIFT_OPEN)
    conn = get_db()
    try:
        red = conn.execute(
            "SELECT id, radnik, user_id FROM smjene WHERE id = ? AND kraj IS NULL",
            (smjena_id,),
        ).fetchone()
        if red is None:
            raise ValueError("Aktivna smjena ne postoji.")
        prethodni = red["radnik"] or "—"
        conn.execute(
            "UPDATE smjene SET user_id = ?, radnik = ? WHERE id = ?",
            (actor.id, actor.ime, smjena_id),
        )
        upisi_audit_u_transakciji(
            conn, actor, "SHIFT_TAKEN_OVER", "smjena", entitet_id=smjena_id,
            smjena_id=smjena_id,
            detalj=f"Preuzeta smjena prethodnog radnika: {prethodni}."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def dohvati_smjenu_po_id(smjena_id: int) -> Optional[dict]:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM smjene WHERE id = ?", (smjena_id,)
    ).fetchone()
    if row:
        return dict(row)
    return None
