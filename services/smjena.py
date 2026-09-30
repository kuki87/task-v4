from datetime import datetime
from typing import Dict, List, Optional, Tuple
from database.db import get_db
from models.session_state import SessionState
from models.artikal import Artikal
from services.pazar import naplati_uredjaj


AktivnaSesija = Tuple[SessionState, List[Artikal], float]


def otvori_smjenu(ime_radnika: str) -> int:
    aktivna = dohvati_aktivnu_smjenu()
    if aktivna:
        raise ValueError(
            f"Smjena radnika '{aktivna['radnik']}' je već otvorena!"
        )
    conn = get_db()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        "INSERT INTO smjene (pocetak, radnik, pazar) VALUES (?, ?, 0.0)",
        (now, ime_radnika)
    )
    conn.commit()
    return cursor.lastrowid


def zatvori_smjenu(
    smjena_id: int,
    aktivne_sesije: Dict[str, AktivnaSesija],
    sank_kosarica: List[Artikal]
) -> dict:
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
        "SELECT id, pocetak, radnik FROM smjene WHERE kraj IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        return dict(row)
    return None


def dohvati_smjenu_po_id(smjena_id: int) -> Optional[dict]:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM smjene WHERE id = ?", (smjena_id,)
    ).fetchone()
    if row:
        return dict(row)
    return None
