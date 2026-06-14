from typing import Optional
from database.db import get_db


def ucitaj_uredjaje() -> list:
    conn = get_db()
    return conn.execute(
        "SELECT id, ime, cena, tip, grupa FROM uredjaji ORDER BY grupa, ime"
    ).fetchall()


def dodaj_uredjaj(ime: str, cena: float, tip: str, grupa: str = "Classic") -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO uredjaji (ime, cena, tip, grupa) VALUES (?, ?, ?, ?)",
        (ime, cena, tip, grupa)
    )
    conn.commit()


def brisi_uredjaj(uid: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM uredjaji WHERE id = ?", (uid,))
    conn.commit()


def postavi_cijenu_grupe(grupa: str, cena: float) -> int:
    conn = get_db()
    cursor = conn.execute(
        "UPDATE uredjaji SET cena = ? WHERE grupa = ?", (cena, grupa)
    )
    conn.commit()
    return cursor.rowcount


def seed_uredjaje_ako_prazno(podrazumijevani: list) -> None:
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM uredjaji").fetchone()[0] == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO uredjaji (ime, cena, tip, grupa) VALUES (?, ?, ?, ?)",
            podrazumijevani
        )
        conn.commit()


def dohvati_aktivne_sesije(smjena_id: int) -> list:
    conn = get_db()
    return conn.execute(
        """SELECT uredjaj, vreme_starta, tip FROM sesije_log
           WHERE smjena_id = ? AND vreme_kraja IS NULL""",
        (smjena_id,)
    ).fetchall()


def ucitaj_logove(filter_datum: Optional[str] = None) -> list:
    conn = get_db()
    if filter_datum:
        return conn.execute(
            "SELECT vreme, radnik, uredjaj, akcija FROM logovi"
            " WHERE vreme LIKE ? ORDER BY vreme DESC LIMIT 200",
            (f"{filter_datum}%",)
        ).fetchall()
    return conn.execute(
        "SELECT vreme, radnik, uredjaj, akcija FROM logovi ORDER BY vreme DESC LIMIT 200"
    ).fetchall()
