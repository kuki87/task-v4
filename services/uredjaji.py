from datetime import datetime
from typing import Optional
from database.db import get_db
from services.rezervacije import STATUS_REZERVISANO, STATUS_STIGAO


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
        """SELECT uredjaj, vreme_starta, tip, limit_sekundi FROM sesije_log
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
