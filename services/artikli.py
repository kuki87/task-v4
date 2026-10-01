from database.db import get_db
from services.audit import upisi_audit_u_transakciji
from services.permissions import ARTICLE_MANAGE, zahtijevaj_dozvolu


def ucitaj_artikle() -> list:
    conn = get_db()
    return conn.execute("SELECT id, naziv, cijena FROM artikli ORDER BY naziv").fetchall()


def dodaj_artikal(naziv: str, cijena: float, *, actor) -> None:
    actor = zahtijevaj_dozvolu(actor, ARTICLE_MANAGE)
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO artikli (naziv, cijena) VALUES (?, ?)", (naziv, cijena)
        )
        upisi_audit_u_transakciji(
            conn, actor, "ARTICLE_CREATED", "artikal",
            entitet_id=cursor.lastrowid,
            detalj=f"{naziv}, cijena {cijena:.2f} KM."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def uredi_artikal(aid: int, naziv: str, cijena: float, *, actor) -> None:
    actor = zahtijevaj_dozvolu(actor, ARTICLE_MANAGE)
    conn = get_db()
    try:
        conn.execute(
            "UPDATE artikli SET naziv = ?, cijena = ? WHERE id = ?",
            (naziv, cijena, aid)
        )
        upisi_audit_u_transakciji(
            conn, actor, "ARTICLE_UPDATED", "artikal", entitet_id=aid,
            detalj=f"{naziv}, cijena {cijena:.2f} KM."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def brisi_artikal(aid: int, *, actor) -> None:
    actor = zahtijevaj_dozvolu(actor, ARTICLE_MANAGE)
    conn = get_db()
    red = conn.execute("SELECT naziv FROM artikli WHERE id = ?", (aid,)).fetchone()
    if red is None:
        raise ValueError("Artikal ne postoji.")
    try:
        conn.execute("DELETE FROM artikli WHERE id = ?", (aid,))
        upisi_audit_u_transakciji(
            conn, actor, "ARTICLE_DELETED", "artikal", entitet_id=aid,
            detalj=f"Obrisan artikal {red['naziv']}."
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
