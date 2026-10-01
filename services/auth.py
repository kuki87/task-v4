import hashlib
import hmac
import secrets

from database.db import get_db
from services.logger import log


PBKDF2_ITERACIJE = 600_000
PBKDF2_SALT_BAJTOVA = 16
PBKDF2_VERZIJA = "v1"
PBKDF2_OZNAKA = "pbkdf2_sha256"
MIN_DUZINA_LOZINKE = 4

AUTH_NEDOSTAJE = "nedostaje"
AUTH_SPREMAN = "spreman"
AUTH_OSTECEN = "ostecen"

_ADMIN_ZAPIS = "admin_password"
_LEGACY_HASH = "admin_hash"
_LEGACY_SALT = "admin_salt"


def _pbkdf2_hash(lozinka: str, salt: bytes, iteracije: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", lozinka.encode("utf-8"), salt, iteracije
    )


def _napravi_pbkdf2_zapis(lozinka: str) -> str:
    salt = secrets.token_bytes(PBKDF2_SALT_BAJTOVA)
    hash_bajtovi = _pbkdf2_hash(lozinka, salt, PBKDF2_ITERACIJE)
    return (
        f"{PBKDF2_VERZIJA}${PBKDF2_OZNAKA}${PBKDF2_ITERACIJE}"
        f"${salt.hex()}${hash_bajtovi.hex()}"
    )


def napravi_password_hash(lozinka: str) -> str:
    if not isinstance(lozinka, str) or len(lozinka) < MIN_DUZINA_LOZINKE:
        raise ValueError(
            f"Lozinka mora imati najmanje {MIN_DUZINA_LOZINKE} znaka."
        )
    return _napravi_pbkdf2_zapis(lozinka)


def provjeri_password_hash(lozinka: str, zapis: str) -> tuple[bool, bool]:
    podaci = _procitaj_pbkdf2_zapis(zapis)
    if podaci is None or not isinstance(lozinka, str):
        return False, False
    iteracije, salt, hash_pohranjen = podaci
    hash_unesen = _pbkdf2_hash(lozinka, salt, iteracije)
    ispravno = hmac.compare_digest(hash_unesen, hash_pohranjen)
    return ispravno, ispravno and iteracije < PBKDF2_ITERACIJE


def _procitaj_pbkdf2_zapis(zapis: str):
    try:
        verzija, algoritam, iteracije_txt, salt_hex, hash_hex = zapis.split("$")
        iteracije = int(iteracije_txt)
        salt = bytes.fromhex(salt_hex)
        hash_bajtovi = bytes.fromhex(hash_hex)
    except (AttributeError, TypeError, ValueError):
        return None

    if verzija != PBKDF2_VERZIJA or algoritam != PBKDF2_OZNAKA:
        return None
    if not 100_000 <= iteracije <= 10_000_000:
        return None
    if len(salt) < PBKDF2_SALT_BAJTOVA:
        return None
    if len(hash_bajtovi) != hashlib.sha256().digest_size:
        return None
    return iteracije, salt, hash_bajtovi


def _legacy_zapis_ispravan(hash_pohranjen: str, salt: str) -> bool:
    try:
        hash_bajtovi = bytes.fromhex(hash_pohranjen)
        salt_bajtovi = bytes.fromhex(salt)
    except (AttributeError, TypeError, ValueError):
        return False
    return (
        len(hash_bajtovi) == hashlib.sha256().digest_size
        and len(salt_bajtovi) >= PBKDF2_SALT_BAJTOVA
    )


def _legacy_hash_lozinke(lozinka: str, salt: str) -> str:
    kombinovano = (lozinka + salt).encode("utf-8")
    return hashlib.sha256(kombinovano).hexdigest()


def _ucitaj_auth_zapise() -> dict:
    conn = get_db()
    rows = conn.execute(
        "SELECT kljuc, vrijednost FROM config WHERE kljuc IN (?, ?, ?)",
        (_ADMIN_ZAPIS, _LEGACY_HASH, _LEGACY_SALT),
    ).fetchall()
    return {row["kljuc"]: row["vrijednost"] for row in rows}


def stanje_admin_lozinke() -> str:
    zapisi = _ucitaj_auth_zapise()
    ima_hash = _LEGACY_HASH in zapisi
    ima_salt = _LEGACY_SALT in zapisi

    if _ADMIN_ZAPIS in zapisi:
        if ima_hash or ima_salt:
            return AUTH_OSTECEN
        if _procitaj_pbkdf2_zapis(zapisi[_ADMIN_ZAPIS]) is None:
            return AUTH_OSTECEN
        return AUTH_SPREMAN

    if ima_hash and ima_salt:
        if _legacy_zapis_ispravan(zapisi[_LEGACY_HASH], zapisi[_LEGACY_SALT]):
            return AUTH_SPREMAN
        return AUTH_OSTECEN
    if ima_hash or ima_salt:
        return AUTH_OSTECEN
    return AUTH_NEDOSTAJE


def promijeni_lozinku(nova: str) -> bool:
    if not isinstance(nova, str) or len(nova) < MIN_DUZINA_LOZINKE:
        return False

    zapis = _napravi_pbkdf2_zapis(nova)
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO config (kljuc, vrijednost) VALUES (?, ?)",
            (_ADMIN_ZAPIS, zapis),
        )
        conn.execute(
            "DELETE FROM config WHERE kljuc IN (?, ?)",
            (_LEGACY_HASH, _LEGACY_SALT),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return True


def provjeri_admin_lozinku(unesena: str) -> bool:
    zapisi = _ucitaj_auth_zapise()
    ima_hash = _LEGACY_HASH in zapisi
    ima_salt = _LEGACY_SALT in zapisi

    if _ADMIN_ZAPIS in zapisi:
        if ima_hash or ima_salt:
            log.error("Pomiješani PBKDF2 i legacy admin zapisi u config tabeli.")
            return False
        podaci = _procitaj_pbkdf2_zapis(zapisi[_ADMIN_ZAPIS])
        if podaci is None:
            log.error("Oštećen ili nepodržan PBKDF2 admin zapis u config tabeli.")
            return False

        iteracije, salt, hash_pohranjen = podaci
        hash_unesen = _pbkdf2_hash(unesena, salt, iteracije)
        if not hmac.compare_digest(hash_unesen, hash_pohranjen):
            return False

        if iteracije < PBKDF2_ITERACIJE:
            promijeni_lozinku(unesena)
        return True

    if ima_hash and ima_salt:
        hash_pohranjen = zapisi[_LEGACY_HASH]
        salt = zapisi[_LEGACY_SALT]
        if not _legacy_zapis_ispravan(hash_pohranjen, salt):
            log.error("Oštećen legacy admin zapis u config tabeli.")
            return False

        hash_unesen = _legacy_hash_lozinke(unesena, salt)
        if not hmac.compare_digest(hash_unesen, hash_pohranjen):
            return False

        promijeni_lozinku(unesena)
        return True

    if ima_hash or ima_salt:
        log.error("Oštećen legacy admin zapis u config tabeli (fali hash ili salt).")
    return False


def provjeri_legacy_admin_lozinku(unesena: str) -> bool:
    """Provjeri legacy credential bez rehasha ili izmjene config tabele."""
    zapisi = _ucitaj_auth_zapise()
    if _ADMIN_ZAPIS in zapisi:
        if _LEGACY_HASH in zapisi or _LEGACY_SALT in zapisi:
            return False
        return provjeri_password_hash(unesena, zapisi[_ADMIN_ZAPIS])[0]
    if _LEGACY_HASH in zapisi and _LEGACY_SALT in zapisi:
        if not _legacy_zapis_ispravan(
            zapisi[_LEGACY_HASH], zapisi[_LEGACY_SALT]
        ):
            return False
        return hmac.compare_digest(
            _legacy_hash_lozinke(unesena, zapisi[_LEGACY_SALT]),
            zapisi[_LEGACY_HASH],
        )
    return False


def obrisi_legacy_auth_u_transakciji(conn) -> None:
    conn.execute(
        "DELETE FROM config WHERE kljuc IN (?, ?, ?)",
        (_ADMIN_ZAPIS, _LEGACY_HASH, _LEGACY_SALT),
    )
