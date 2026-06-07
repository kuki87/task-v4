from database.db import get_db


def ucitaj_artikle() -> list:
    conn = get_db()
    return conn.execute("SELECT id, naziv, cijena FROM artikli ORDER BY naziv").fetchall()


def dodaj_artikal(naziv: str, cijena: float) -> None:
    conn = get_db()
    conn.execute("INSERT INTO artikli (naziv, cijena) VALUES (?, ?)", (naziv, cijena))
    conn.commit()


def uredi_artikal(aid: int, naziv: str, cijena: float) -> None:
    conn = get_db()
    conn.execute("UPDATE artikli SET naziv = ?, cijena = ? WHERE id = ?", (naziv, cijena, aid))
    conn.commit()


def brisi_artikal(aid: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM artikli WHERE id = ?", (aid,))
    conn.commit()
