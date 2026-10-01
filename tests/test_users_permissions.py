import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import database.db as db_module
import database.models as db_models
import services.uredjaji as uredjaji_service
import services.users as users
from services import auth
from services.artikli import dodaj_artikal
from services.rezervacije import kreiraj_rezervaciju
from services.smjena import otvori_smjenu
from services.permissions import (
    ARTICLE_MANAGE,
    AUDIT_VIEW,
    DEVICE_MANAGE,
    REPORT_VIEW,
    RESERVATION_MANAGE,
    ROLE_PERMISSIONS,
    ROLA_ADMIN,
    ROLA_MANAGER,
    ROLA_RADNIK,
    USER_MANAGE,
    ima_dozvolu,
)
from services.uredjaji import dodaj_uredjaj, seed_uredjaje_ako_prazno


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "users.sqlite3"))
    db_module.inicijalizuj_bazu()
    yield db_module.get_db()
    db_module.zatvori_bazu()


def _admin():
    return users.kreiraj_prvog_admina("admin", "Administrator", "sigurna")


def test_first_run_kreira_prvog_admina_bez_default_lozinke(db):
    assert users.stanje_prvog_pokretanja() == "novi_admin"
    actor = _admin()
    red = db.execute("SELECT * FROM korisnici WHERE id = ?", (actor.id,)).fetchone()
    assert red["rola"] == ROLA_ADMIN
    assert red["aktivan"] == 1
    assert red["password_hash"] != "sigurna"
    assert users.stanje_prvog_pokretanja() == "login"


def test_validan_login_vraca_stabilni_identitet_i_upisuje_audit(db):
    admin = _admin()
    prijavljen = users.prijavi_korisnika("ADMIN", "sigurna")
    assert prijavljen == admin
    red = db.execute(
        "SELECT user_id, username, akcija FROM logovi WHERE akcija = ?",
        ("LOGIN_SUCCESS",),
    ).fetchone()
    assert (red["user_id"], red["username"]) == (admin.id, "admin")


def test_pogresna_lozinka_i_nepostojeci_username_daju_isti_neuspjeh(db):
    _admin()
    assert users.prijavi_korisnika("admin", "pogresna") is None
    assert users.prijavi_korisnika("ne-postoji", "pogresna") is None
    assert db.execute(
        "SELECT COUNT(*) FROM logovi WHERE akcija = ?", ("LOGIN_SUCCESS",)
    ).fetchone()[0] == 0


def test_deaktiviran_korisnik_se_ne_moze_prijaviti(db):
    admin = _admin()
    uid = users.kreiraj_korisnika(admin, "radnik", "Radnik", "lozinka", ROLA_RADNIK)
    users.postavi_aktivnost(admin, uid, False)
    assert users.prijavi_korisnika("radnik", "lozinka") is None


def test_deaktivacija_odmah_ponistava_stari_prijavljeni_identitet(db):
    admin = _admin()
    uid = users.kreiraj_korisnika(
        admin, "radnik", "Radnik", "lozinka", ROLA_RADNIK
    )
    radnik = users.prijavi_korisnika("radnik", "lozinka")
    users.postavi_aktivnost(admin, uid, False)
    with pytest.raises(PermissionError, match="nije aktivan"):
        otvori_smjenu(radnik)


def test_promjena_role_odmah_ponistava_staru_admin_dozvolu(db):
    admin = _admin()
    drugi_id = users.kreiraj_korisnika(
        admin, "drugi-admin", "Drugi Admin", "lozinka", ROLA_ADMIN
    )
    stari_identitet = users.prijavi_korisnika("drugi-admin", "lozinka")
    users.promijeni_rolu(admin, drugi_id, ROLA_MANAGER)
    with pytest.raises(PermissionError):
        dodaj_uredjaj("PC-STARI-ACTOR", 2.0, "PC", actor=stari_identitet)


def test_username_je_jedinstven_bez_obzira_na_velicinu_slova(db):
    admin = _admin()
    users.kreiraj_korisnika(admin, "radnik", "Prvi", "lozinka", ROLA_RADNIK)
    with pytest.raises(sqlite3.IntegrityError):
        users.kreiraj_korisnika(admin, "RADNIK", "Drugi", "lozinka", ROLA_RADNIK)


def test_password_hash_je_pbkdf2_zapis(db):
    admin = _admin()
    zapis = db.execute(
        "SELECT password_hash FROM korisnici WHERE id = ?", (admin.id,)
    ).fetchone()[0]
    assert zapis.startswith("v1$pbkdf2_sha256$600000$")
    assert auth.provjeri_password_hash("sigurna", zapis) == (True, False)


def test_admin_kreira_korisnika_i_mijenja_ime(db):
    admin = _admin()
    uid = users.kreiraj_korisnika(admin, "mira", "Mira", "lozinka", ROLA_MANAGER)
    users.promijeni_ime(admin, uid, "Mira M.")
    red = db.execute("SELECT ime, rola FROM korisnici WHERE id = ?", (uid,)).fetchone()
    assert (red["ime"], red["rola"]) == ("Mira M.", ROLA_MANAGER)


def test_promjena_role(db):
    admin = _admin()
    uid = users.kreiraj_korisnika(admin, "radnik", "Radnik", "lozinka", ROLA_RADNIK)
    users.promijeni_rolu(admin, uid, ROLA_MANAGER)
    assert db.execute("SELECT rola FROM korisnici WHERE id = ?", (uid,)).fetchone()[0] == ROLA_MANAGER


def test_deaktivacija_i_ponovna_aktivacija(db):
    admin = _admin()
    uid = users.kreiraj_korisnika(admin, "radnik", "Radnik", "lozinka", ROLA_RADNIK)
    users.postavi_aktivnost(admin, uid, False)
    users.postavi_aktivnost(admin, uid, True)
    assert db.execute("SELECT aktivan FROM korisnici WHERE id = ?", (uid,)).fetchone()[0] == 1


def test_promjena_lozinke(db):
    admin = _admin()
    uid = users.kreiraj_korisnika(admin, "radnik", "Radnik", "stara", ROLA_RADNIK)
    users.promijeni_lozinku_korisnika(admin, uid, "nova-lozinka")
    assert users.prijavi_korisnika("radnik", "stara") is None
    assert users.prijavi_korisnika("radnik", "nova-lozinka") is not None


def test_posljednji_admin_se_ne_moze_deaktivirati(db):
    admin = _admin()
    with pytest.raises(ValueError, match="Posljednji"):
        users.postavi_aktivnost(admin, admin.id, False)


def test_posljednji_admin_ne_moze_izgubiti_admin_rolu(db):
    admin = _admin()
    with pytest.raises(ValueError, match="Posljednji"):
        users.promijeni_rolu(admin, admin.id, ROLA_MANAGER)


def test_radnik_ne_moze_pozvati_admin_write_servis(db):
    admin = _admin()
    users.kreiraj_korisnika(admin, "radnik", "Radnik", "lozinka", ROLA_RADNIK)
    radnik = users.prijavi_korisnika("radnik", "lozinka")
    with pytest.raises(PermissionError):
        dodaj_uredjaj("PC-X", 2.0, "PC", actor=radnik)


def test_seed_uredjaja_je_admin_write_i_auditiran_je(db):
    admin = _admin()
    users.kreiraj_korisnika(
        admin, "radnik", "Radnik", "lozinka", ROLA_RADNIK
    )
    radnik = users.prijavi_korisnika("radnik", "lozinka")
    uredjaji = [("PC-SEED", 2.0, "PC", "Classic")]
    with pytest.raises(PermissionError):
        seed_uredjaje_ako_prazno(uredjaji, actor=radnik)
    assert db.execute("SELECT COUNT(*) FROM uredjaji").fetchone()[0] == 0

    seed_uredjaje_ako_prazno(uredjaji, actor=admin)

    assert db.execute("SELECT COUNT(*) FROM uredjaji").fetchone()[0] == 1
    assert db.execute(
        """SELECT COUNT(*) FROM logovi
           WHERE akcija = 'DEVICE_CREATED' AND uredjaj = 'PC-SEED'"""
    ).fetchone()[0] == 1


def test_seed_uredjaja_i_audit_su_atomski(db, monkeypatch):
    admin = _admin()

    def greska(*_args, **_kwargs):
        raise RuntimeError("audit greška")

    monkeypatch.setattr(
        uredjaji_service, "upisi_audit_u_transakciji", greska
    )
    with pytest.raises(RuntimeError, match="audit"):
        seed_uredjaje_ako_prazno(
            [("PC-SEED", 2.0, "PC", "Classic")], actor=admin
        )

    assert db.execute("SELECT COUNT(*) FROM uredjaji").fetchone()[0] == 0


def test_manager_dozvole_su_operativne_bez_admin_upravljanja(db):
    assert ima_dozvolu(ROLA_MANAGER, REPORT_VIEW)
    assert ima_dozvolu(ROLA_MANAGER, AUDIT_VIEW)
    assert ima_dozvolu(ROLA_MANAGER, RESERVATION_MANAGE)
    assert not ima_dozvolu(ROLA_MANAGER, USER_MANAGE)
    assert not ima_dozvolu(ROLA_MANAGER, DEVICE_MANAGE)


def test_manager_servisno_moze_rezervaciju_ali_ne_admin_write(db):
    admin = _admin()
    users.kreiraj_korisnika(
        admin, "manager", "Manager", "lozinka", ROLA_MANAGER
    )
    manager = users.prijavi_korisnika("manager", "lozinka")
    uredjaj_id = db.execute(
        """INSERT INTO uredjaji (ime, cena, tip, grupa)
           VALUES (?, ?, ?, ?)""",
        ("PC1", 2.0, "PC", "Classic"),
    ).lastrowid
    db.commit()
    pocetak = datetime.now() + timedelta(days=1)
    rezervacija_id = kreiraj_rezervaciju(
        uredjaj_id, "Gost", pocetak, pocetak + timedelta(hours=1), manager
    )
    assert rezervacija_id
    with pytest.raises(PermissionError):
        users.kreiraj_korisnika(
            manager, "drugi", "Drugi", "lozinka", ROLA_RADNIK
        )
    with pytest.raises(PermissionError):
        dodaj_artikal("Manager artikal", 1.0, actor=manager)


def test_admin_ima_sve_definisane_dozvole(db):
    assert ROLE_PERMISSIONS[ROLA_ADMIN]
    assert all(ima_dozvolu(ROLA_ADMIN, p) for p in ROLE_PERMISSIONS[ROLA_ADMIN])
    assert ima_dozvolu(ROLA_ADMIN, ARTICLE_MANAGE)


def test_legacy_admin_migracija_uklanja_config_tek_nakon_usera(db):
    auth.promijeni_lozinku("stara-admin")
    assert users.stanje_prvog_pokretanja() == "migracija_legacy"
    admin = users.migriraj_legacy_admin(
        "stara-admin", "novi-admin", "Novi Admin", "nova-admin"
    )
    assert admin.rola == ROLA_ADMIN
    assert users.prijavi_korisnika("novi-admin", "nova-admin") == admin
    assert db.execute(
        "SELECT COUNT(*) FROM config WHERE kljuc LIKE 'admin_%'"
    ).fetchone()[0] == 0


def test_ostecen_legacy_auth_blokira_first_run(db):
    db.execute(
        "INSERT INTO config (kljuc, vrijednost) VALUES (?, ?)",
        ("admin_password", "osteceno"),
    )
    db.commit()
    assert users.stanje_prvog_pokretanja() == "legacy_ostecen"
    with pytest.raises(ValueError, match="legacy"):
        users.kreiraj_prvog_admina("admin", "Admin", "lozinka")


def test_legacy_migracija_rollback_cuva_credential(db, monkeypatch):
    auth.promijeni_lozinku("stara-admin")
    prije = db.execute("SELECT kljuc, vrijednost FROM config").fetchall()

    def greska(*_args, **_kwargs):
        raise RuntimeError("audit greška")

    monkeypatch.setattr(users, "upisi_audit_u_transakciji", greska)
    with pytest.raises(RuntimeError, match="audit"):
        users.migriraj_legacy_admin(
            "stara-admin", "admin", "Admin", "nova-admin"
        )
    poslije = db.execute("SELECT kljuc, vrijednost FROM config").fetchall()
    assert [tuple(r) for r in poslije] == [tuple(r) for r in prije]
    assert users.broj_korisnika() == 0


def test_auth_migracija_je_idempotentna_i_ne_povezuje_starog_radnika(db):
    admin = _admin()
    smjena_id = db.execute(
        """INSERT INTO smjene (pocetak, kraj, radnik, pazar, user_id)
           VALUES (?, NULL, ?, 0, NULL)""",
        ("2026-01-01T08:00:00", "Historijski radnik"),
    ).lastrowid
    db.commit()

    db_models.pokreni_migracije(db)
    db_models.pokreni_migracije(db)

    assert users.broj_korisnika() == 1
    assert db.execute(
        "SELECT user_id FROM smjene WHERE id = ?", (smjena_id,)
    ).fetchone()[0] is None
    assert users.prijavi_korisnika("admin", "sigurna") == admin
