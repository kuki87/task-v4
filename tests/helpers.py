from datetime import datetime

from models.user import UserIdentity
from services.auth import napravi_password_hash


def napravi_test_korisnika(
    conn,
    *,
    username: str = "tester",
    ime: str = "Tester",
    rola: str = "admin",
) -> UserIdentity:
    """Kreira stabilnog DB korisnika za service/UI regression testove."""
    sada = datetime.now().replace(microsecond=0).isoformat()
    conn.execute(
        """INSERT OR IGNORE INTO korisnici
           (korisnicko_ime, ime, password_hash, rola, aktivan, kreiran, azuriran)
           VALUES (?, ?, ?, ?, 1, ?, ?)""",
        (username, ime, napravi_password_hash("test-lozinka"), rola, sada, sada),
    )
    conn.commit()
    red = conn.execute(
        """SELECT id, korisnicko_ime, ime, rola
           FROM korisnici WHERE korisnicko_ime = ?""",
        (username,),
    ).fetchone()
    return UserIdentity.iz_reda(red)
