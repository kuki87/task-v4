import hashlib
import sqlite3
from pathlib import Path

import pytest

import database.db as db_module
import services.auth as auth_service


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    db_path = tmp_path / "auth-test.sqlite3"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    monkeypatch.setattr(auth_service.log, "error", lambda *args, **kwargs: None)

    db_module.inicijalizuj_bazu()
    conn = db_module.get_db()
    stvarna_putanja = Path(
        conn.execute("PRAGMA database_list").fetchone()["file"]
    ).resolve()
    assert stvarna_putanja == db_path.resolve()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    yield conn

    db_module.zatvori_bazu()


def _auth_redovi(db):
    return [
        tuple(red)
        for red in db.execute(
            "SELECT kljuc, vrijednost FROM config ORDER BY kljuc"
        ).fetchall()
    ]


def _upisi_legacy_zapis(db, lozinka: str):
    salt = bytes(range(16)).hex()
    legacy_hash = hashlib.sha256((lozinka + salt).encode("utf-8")).hexdigest()
    db.executemany(
        "INSERT INTO config (kljuc, vrijednost) VALUES (?, ?)",
        (("admin_hash", legacy_hash), ("admin_salt", salt)),
    )
    db.commit()


def test_novi_zapis_koristi_pbkdf2_sha256_i_600000_iteracija(db):
    assert auth_service.promijeni_lozinku("nova-lozinka") is True

    zapis = db.execute(
        "SELECT vrijednost FROM config WHERE kljuc = ?", ("admin_password",)
    ).fetchone()["vrijednost"]
    verzija, algoritam, iteracije, salt_hex, hash_hex = zapis.split("$")

    assert verzija == "v1"
    assert algoritam == "pbkdf2_sha256"
    assert int(iteracije) == 600_000
    assert len(bytes.fromhex(salt_hex)) >= 16
    assert len(bytes.fromhex(hash_hex)) == hashlib.sha256().digest_size
    assert _auth_redovi(db) == [("admin_password", zapis)]


def test_pogresna_pbkdf2_lozinka_ne_mijenja_bazu(db):
    auth_service.promijeni_lozinku("ispravna-lozinka")
    prije = _auth_redovi(db)

    assert auth_service.provjeri_admin_lozinku("pogresna-lozinka") is False

    assert _auth_redovi(db) == prije


def test_uspjesna_legacy_prijava_migrira_zapis_na_pbkdf2(db):
    _upisi_legacy_zapis(db, "stara-lozinka")

    assert auth_service.provjeri_admin_lozinku("stara-lozinka") is True

    redovi = _auth_redovi(db)
    assert [kljuc for kljuc, _ in redovi] == ["admin_password"]
    dijelovi = redovi[0][1].split("$")
    assert dijelovi[:3] == ["v1", "pbkdf2_sha256", "600000"]
    assert auth_service.stanje_admin_lozinke() == auth_service.AUTH_SPREMAN


def test_pogresna_legacy_lozinka_ne_migrira_zapis(db):
    _upisi_legacy_zapis(db, "stara-lozinka")
    prije = _auth_redovi(db)

    assert auth_service.provjeri_admin_lozinku("pogresna-lozinka") is False

    assert _auth_redovi(db) == prije
    assert db.execute(
        "SELECT COUNT(*) FROM config WHERE kljuc = ?", ("admin_password",)
    ).fetchone()[0] == 0


def test_potpuno_odsustvo_auth_zapisa_daje_first_run_stanje(db):
    assert _auth_redovi(db) == []
    assert auth_service.stanje_admin_lozinke() == auth_service.AUTH_NEDOSTAJE
    assert auth_service.provjeri_admin_lozinku("bilo-sta") is False


@pytest.mark.parametrize(
    "zapisi",
    [
        (("admin_hash", "00" * 32),),
        (("admin_salt", "00" * 16),),
        (("admin_password", "neispravan-zapis"),),
        (("admin_hash", "00" * 32), ("admin_salt", "00" * 15)),
        (
            (
                "admin_password",
                f"v1$pbkdf2_sha256$600000${'00' * 16}${'00' * 32}",
            ),
            ("admin_hash", "00" * 32),
        ),
    ],
    ids=[
        "nedostaje-salt",
        "nedostaje-hash",
        "neispravan-pbkdf2",
        "neispravan-legacy",
        "pomijesani-formati",
    ],
)
def test_djelimican_ili_ostecen_auth_zapis_daje_auth_ostecen(db, zapisi):
    db.executemany(
        "INSERT INTO config (kljuc, vrijednost) VALUES (?, ?)", zapisi
    )
    db.commit()

    assert auth_service.stanje_admin_lozinke() == auth_service.AUTH_OSTECEN


def test_promjena_lozinke_rollbackuje_ako_drugi_sql_korak_padne(
    db, monkeypatch: pytest.MonkeyPatch
):
    _upisi_legacy_zapis(db, "stara-lozinka")
    prije = _auth_redovi(db)

    class VezaSaGreskomNaDelete:
        def __init__(self, stvarna_veza):
            self.stvarna_veza = stvarna_veza
            self.rollback_pozivi = 0

        def execute(self, sql, parametri=()):
            if sql.lstrip().upper().startswith("DELETE FROM CONFIG"):
                raise sqlite3.OperationalError("simulirana greška DELETE koraka")
            return self.stvarna_veza.execute(sql, parametri)

        def commit(self):
            return self.stvarna_veza.commit()

        def rollback(self):
            self.rollback_pozivi += 1
            return self.stvarna_veza.rollback()

    veza_sa_greskom = VezaSaGreskomNaDelete(db)
    monkeypatch.setattr(auth_service, "get_db", lambda: veza_sa_greskom)

    with pytest.raises(sqlite3.OperationalError, match="simulirana greška"):
        auth_service.promijeni_lozinku("nova-lozinka")

    assert veza_sa_greskom.rollback_pozivi == 1
    assert _auth_redovi(db) == prije
