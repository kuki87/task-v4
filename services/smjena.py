from datetime import datetime
from copy import deepcopy
from typing import Dict, List, Optional
from database.db import get_db
from models.session_state import SessionState
from models.artikal import Artikal


def otvori_smjenu(ime_radnika: str) -> int:
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
    aktivne_sesije: Dict[str, SessionState],
    sank_kosarica: List[Artikal],
    iznos_pazara: float
) -> dict:
    conn = get_db()
    now = datetime.now().isoformat()

    conn.execute(
        "UPDATE smjene SET kraj = ?, pazar = ? WHERE id = ?",
        (now, iznos_pazara, smjena_id)
    )
    conn.commit()

    return {
        "smjena_id": smjena_id,
        "kraj": now,
        "pazar": iznos_pazara,
        "preneseni_racunari": list(aktivne_sesije.keys()),
        "sank_kosarica": sank_kosarica,
    }


def prenesi_u_novu_smjenu(
    aktivne_sesije: Dict[str, SessionState],
    nenaplaceni_po_uredjaju: Dict[str, List[Artikal]],
    novi_smjena_id: int
) -> Dict[str, SessionState]:
    conn = get_db()
    now = datetime.now().isoformat()

    nove_sesije = {}
    for ime_uredjaja, session in aktivne_sesije.items():
        nova_sesija = deepcopy(session)
        # Kosarica se prenosi
        nova_sesija.kosarica = deepcopy(nenaplaceni_po_uredjaju.get(ime_uredjaja, []))
        nove_sesije[ime_uredjaja] = nova_sesija

        # Upisi prenesene artikle u novu smjenu
        for artikal in nova_sesija.kosarica:
            conn.execute(
                """INSERT INTO prodaja_artikala
                   (vreme, smjena_id, uredjaj, naziv_artikla, kolicina, ukupna_cijena, naplaceno)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (now, novi_smjena_id, ime_uredjaja,
                 artikal.naziv, artikal.kolicina, artikal.ukupno())
            )

    conn.commit()
    return nove_sesije


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
