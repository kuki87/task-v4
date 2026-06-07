import hashlib
import secrets
from database.db import get_db
from constants import ADMIN_DEFAULT_LOZINKA


def hash_lozinke(lozinka: str, salt: str) -> str:
    kombinovano = (lozinka + salt).encode("utf-8")
    return hashlib.sha256(kombinovano).hexdigest()


def provjeri_lozinku(unesena: str, hash_pohranjen: str, salt: str) -> bool:
    return hash_lozinke(unesena, salt) == hash_pohranjen


def promijeni_lozinku(nova: str):
    salt = secrets.token_hex(16)
    h = hash_lozinke(nova, salt)
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO config (kljuc, vrijednost) VALUES (?, ?)",
        ("admin_hash", h)
    )
    conn.execute(
        "INSERT OR REPLACE INTO config (kljuc, vrijednost) VALUES (?, ?)",
        ("admin_salt", salt)
    )
    conn.commit()


def provjeri_admin_lozinku(unesena: str) -> bool:
    conn = get_db()
    row_hash = conn.execute(
        "SELECT vrijednost FROM config WHERE kljuc = 'admin_hash'"
    ).fetchone()
    row_salt = conn.execute(
        "SELECT vrijednost FROM config WHERE kljuc = 'admin_salt'"
    ).fetchone()

    if row_hash is None or row_salt is None:
        # Nema lozinke u bazi, inicijalizuj default
        promijeni_lozinku(ADMIN_DEFAULT_LOZINKA)
        return unesena == ADMIN_DEFAULT_LOZINKA

    return provjeri_lozinku(unesena, row_hash["vrijednost"], row_salt["vrijednost"])
