from datetime import datetime
from typing import List
from database.db import get_db
from models.session_state import SessionState
from models.artikal import Artikal
from constants import CIJENA_MINECRAFT


def izracunaj_iznos_sesije(session: SessionState, cena_po_satu: float) -> float:
    if session.tip == "minecraft":
        elapsed_sati = session.elapsed_sekundi() / 3600
        return round(elapsed_sati * CIJENA_MINECRAFT, 2)
    if session.tip in ("prepaid", "pass1", "pass2"):
        # Iznos je već naplacen pri startu
        return 0.0
    # Neograniceno i sve nepoznate vrijednosti — po satu
    elapsed_sati = session.elapsed_sekundi() / 3600
    return round(elapsed_sati * cena_po_satu, 2)


def naplati_uredjaj(
    uredjaj_ime: str,
    session: SessionState,
    kosarica: List[Artikal],
    cena_po_satu: float,
    smjena_id: int,
    *,
    commit: bool = True
) -> float:
    conn = get_db()
    now = datetime.now().isoformat()

    iznos_sesije = izracunaj_iznos_sesije(session, cena_po_satu)

    # tip_prodaje
    tip_mapa = {
        "neograniceno": "racunar",
        "prepaid": "prepaid",
        "pass1": "pass1",
        "pass2": "pass2",
        "minecraft": "minecraft",
    }
    tip_prodaje = tip_mapa.get(session.tip, "racunar")

    # Zatvori aktivni zapis kreiran pri START-u.
    cursor = conn.execute(
        """UPDATE sesije_log
           SET vreme_kraja = ?, iznos = ?
           WHERE smjena_id = ? AND uredjaj = ? AND vreme_kraja IS NULL""",
        (now, iznos_sesije, smjena_id, uredjaj_ime)
    )
    if cursor.rowcount == 0:
        if commit:
            conn.rollback()
        raise RuntimeError(
            f"Nije pronađena aktivna sesija za uređaj '{uredjaj_ime}' u smjeni {smjena_id}."
        )

    # Upis sesije u pazar_arhiva
    conn.execute(
        """INSERT INTO pazar_arhiva (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (now, uredjaj_ime, iznos_sesije, smjena_id,
         session.vreme_starta.isoformat(), tip_prodaje)
    )

    # Naplata artikala iz košarice
    ukupno_artikli = 0.0
    for artikal in kosarica:
        ukupno_artikli += artikal.ukupno()
        conn.execute(
            """INSERT INTO pazar_arhiva (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (now, uredjaj_ime, artikal.ukupno(), smjena_id,
             session.vreme_starta.isoformat(), "artikal")
        )
        conn.execute(
            """UPDATE prodaja_artikala SET naplaceno = 1
               WHERE uredjaj = ? AND naziv_artikla = ? AND naplaceno = 0 AND smjena_id = ?""",
            (uredjaj_ime, artikal.naziv, smjena_id)
        )

    if commit:
        conn.commit()
    return round(iznos_sesije + ukupno_artikli, 2)


def naplati_sank_kosaricu(stavke: List[Artikal], smjena_id: int) -> float:
    if not stavke:
        return 0.0
    conn = get_db()
    now = datetime.now().isoformat()
    ukupno = 0.0
    for artikal in stavke:
        ukupno += artikal.ukupno()
        conn.execute(
            """INSERT INTO pazar_arhiva (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (now, "Šank", artikal.ukupno(), smjena_id, now, "sank")
        )
    conn.commit()
    return round(ukupno, 2)


def dohvati_pazar_smjene(smjena_id: int) -> dict:
    conn = get_db()
    rows = conn.execute(
        "SELECT uredjaj, iznos, tip_prodaje, vreme FROM pazar_arhiva WHERE smjena_id = ? ORDER BY vreme DESC",
        (smjena_id,)
    ).fetchall()

    ukupno = sum(r["iznos"] for r in rows)
    sank = sum(r["iznos"] for r in rows if r["tip_prodaje"] == "sank")
    artikli = sum(r["iznos"] for r in rows if r["tip_prodaje"] == "artikal")
    racunari = sum(
        r["iznos"] for r in rows if r["tip_prodaje"] not in ("sank", "artikal")
    )

    return {
        "ukupno": round(ukupno, 2),
        "racunari": round(racunari, 2),
        "artikli": round(artikli, 2),
        "sank": round(sank, 2),
        "transakcije": [dict(r) for r in rows],
    }


def dodaj_artikal_na_uredjaj(
    smjena_id: int,
    uredjaj: str,
    naziv: str,
    kolicina: int,
    cijena: float
):
    conn = get_db()
    now = datetime.now().isoformat()
    ukupna = round(cijena * kolicina, 2)
    conn.execute(
        """INSERT INTO prodaja_artikala (vreme, smjena_id, uredjaj, naziv_artikla, kolicina, ukupna_cijena, naplaceno)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (now, smjena_id, uredjaj, naziv, kolicina, ukupna)
    )
    conn.commit()


def prebaci_sesiju_na_uredjaj(
    smjena_id: int,
    radnik: str,
    izvor_uredjaj: str,
    cilj_uredjaj: str
) -> None:
    conn = get_db()
    now = datetime.now().isoformat()
    try:
        cilj_aktivan = conn.execute(
            """SELECT 1 FROM sesije_log
               WHERE uredjaj = ? AND vreme_kraja IS NULL
               LIMIT 1""",
            (cilj_uredjaj,)
        ).fetchone()
        if cilj_aktivan:
            raise ValueError(f"Uređaj '{cilj_uredjaj}' već ima aktivnu sesiju.")

        cursor = conn.execute(
            """UPDATE sesije_log SET uredjaj = ?
               WHERE smjena_id = ? AND uredjaj = ? AND vreme_kraja IS NULL""",
            (cilj_uredjaj, smjena_id, izvor_uredjaj)
        )
        if cursor.rowcount != 1:
            raise RuntimeError(
                f"Aktivna sesija uređaja '{izvor_uredjaj}' nije pronađena ili nije jedinstvena."
            )

        conn.execute(
            """UPDATE prodaja_artikala SET uredjaj = ?
               WHERE smjena_id = ? AND uredjaj = ? AND naplaceno = 0""",
            (cilj_uredjaj, smjena_id, izvor_uredjaj)
        )
        conn.execute(
            """INSERT INTO logovi (vreme, smjena_id, radnik, uredjaj, akcija)
               VALUES (?, ?, ?, ?, ?)""",
            (now, smjena_id, radnik, izvor_uredjaj,
             f"PRIJENOS → {cilj_uredjaj}")
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def start_sesija(
    uredjaj: str,
    session: SessionState,
    smjena_id: int,
    iznos: float = 0.0
) -> None:
    conn = get_db()
    vreme_starta = session.vreme_starta.isoformat()
    try:
        conn.execute(
            """INSERT INTO sesije_log
               (smjena_id, uredjaj, vreme_starta, vreme_kraja, iznos, tip)
               VALUES (?, ?, ?, NULL, NULL, ?)""",
            (smjena_id, uredjaj, vreme_starta, session.tip)
        )

        if session.tip in ("prepaid", "pass1", "pass2") and iznos > 0:
            conn.execute(
                """INSERT INTO pazar_arhiva
                   (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (vreme_starta, uredjaj, iznos, smjena_id,
                 vreme_starta, session.tip)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def dohvati_nenaplacene_artikle(smjena_id: int, uredjaj: str) -> list:
    conn = get_db()
    rows = conn.execute(
        """SELECT naziv_artikla, kolicina, ukupna_cijena
           FROM prodaja_artikala
           WHERE smjena_id = ? AND uredjaj = ? AND naplaceno = 0""",
        (smjena_id, uredjaj)
    ).fetchall()
    return [dict(r) for r in rows]
