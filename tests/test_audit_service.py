from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import database.db as db_module
import services.artikli as artikli_service
import services.audit as audit_service
import services.pazar as pazar_service
import services.rezervacije as rezervacije_service
import services.smjena as smjena_service
import services.uredjaji as uredjaji_service
import services.users as users_service
from models.session_state import SessionState
from services.permissions import ROLA_MANAGER, ROLA_RADNIK


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "audit.sqlite3"))
    db_module.inicijalizuj_bazu()
    conn = db_module.get_db()
    admin = users_service.kreiraj_prvog_admina(
        "admin", "Administrator", "sigurna"
    )
    yield conn, admin
    db_module.zatvori_bazu()


def _akcije(conn):
    return [
        red[0]
        for red in conn.execute("SELECT akcija FROM logovi ORDER BY id").fetchall()
    ]


def test_login_i_user_management_upisuju_strukturirani_audit(db):
    conn, admin = db
    assert users_service.prijavi_korisnika("admin", "sigurna") == admin
    user_id = users_service.kreiraj_korisnika(
        admin, "mira", "Mira", "lozinka", ROLA_RADNIK
    )
    users_service.promijeni_rolu(admin, user_id, ROLA_MANAGER)
    users_service.postavi_aktivnost(admin, user_id, False)
    users_service.postavi_aktivnost(admin, user_id, True)
    users_service.promijeni_lozinku_korisnika(
        admin, user_id, "nova-lozinka"
    )

    akcije = _akcije(conn)
    for akcija in (
        "LOGIN_SUCCESS", "USER_CREATED", "USER_ROLE_CHANGED",
        "USER_DEACTIVATED", "USER_ACTIVATED", "USER_PASSWORD_CHANGED",
    ):
        assert akcija in akcije
    red = conn.execute(
        """SELECT user_id, username, radnik, entitet, entitet_id, detalj
           FROM logovi WHERE akcija = 'USER_PASSWORD_CHANGED'"""
    ).fetchone()
    assert (red["user_id"], red["username"], red["radnik"]) == (
        admin.id, admin.username, admin.ime
    )
    assert (red["entitet"], red["entitet_id"]) == (
        "korisnik", str(user_id)
    )
    assert "nova-lozinka" not in red["detalj"]


def test_smjena_start_naplata_transfer_i_zatvaranje_imaju_audit(db):
    conn, admin = db
    smjena_id = smjena_service.otvori_smjenu(admin)
    sesija = SessionState(
        vreme_starta=datetime.now() - timedelta(minutes=30),
        tip="neograniceno",
    )
    pazar_service.start_sesija("PC1", sesija, smjena_id, actor=admin)
    pazar_service.prebaci_sesiju_na_uredjaj(
        smjena_id, "PC1", "PC2", actor=admin
    )
    pazar_service.naplati_uredjaj(
        "PC2", sesija, [], 2.0, smjena_id, actor=admin
    )
    smjena_service.zatvori_smjenu(
        smjena_id, {}, [], actor=admin
    )

    akcije = _akcije(conn)
    for akcija in (
        "SHIFT_OPENED", "SESSION_STARTED", "SESSION_TRANSFERRED",
        "SESSION_CHARGED", "SHIFT_CLOSED",
    ):
        assert akcija in akcije


def test_preuzimanje_smjene_mijenja_user_id_i_upisuje_audit(db):
    conn, admin = db
    smjena_id = smjena_service.otvori_smjenu(admin)
    users_service.kreiraj_korisnika(
        admin, "manager", "Manager", "lozinka", ROLA_MANAGER
    )
    manager = users_service.prijavi_korisnika("manager", "lozinka")

    smjena_service.preuzmi_smjenu(smjena_id, manager)

    red = conn.execute(
        "SELECT user_id, radnik FROM smjene WHERE id = ?", (smjena_id,)
    ).fetchone()
    assert (red["user_id"], red["radnik"]) == (manager.id, manager.ime)
    audit = conn.execute(
        """SELECT user_id, entitet_id FROM logovi
           WHERE akcija = 'SHIFT_TAKEN_OVER'"""
    ).fetchone()
    assert (audit["user_id"], audit["entitet_id"]) == (
        manager.id, str(smjena_id)
    )


def test_rezervacija_upisuje_novi_identitet_u_audit(db):
    conn, admin = db
    uredjaji_service.dodaj_uredjaj(
        "PC1", 2.0, "PC", "Classic", actor=admin
    )
    uredjaj_id = conn.execute(
        "SELECT id FROM uredjaji WHERE ime = ?", ("PC1",)
    ).fetchone()[0]
    pocetak = datetime.now() + timedelta(days=1)
    rezervacija_id = rezervacije_service.kreiraj_rezervaciju(
        uredjaj_id, "Gost", pocetak, pocetak + timedelta(hours=1), admin
    )
    red = conn.execute(
        """SELECT user_id, username, entitet, entitet_id, uredjaj
           FROM logovi WHERE akcija = 'RESERVATION_CREATED'"""
    ).fetchone()
    assert dict(red) == {
        "user_id": admin.id,
        "username": admin.username,
        "entitet": "rezervacija",
        "entitet_id": str(rezervacija_id),
        "uredjaj": "PC1",
    }


def test_admin_promjene_uredjaja_artikala_i_cijena_imaju_audit(db):
    conn, admin = db
    uredjaji_service.dodaj_uredjaj(
        "PC1", 2.0, "PC", "Classic", actor=admin
    )
    uredjaji_service.postavi_cijenu_grupe("Classic", 2.5, actor=admin)
    artikli_service.dodaj_artikal("Audit artikal", 1.5, actor=admin)
    artikal_id = conn.execute(
        "SELECT id FROM artikli WHERE naziv = ?", ("Audit artikal",)
    ).fetchone()[0]
    artikli_service.uredi_artikal(
        artikal_id, "Velika kafa", 2.0, actor=admin
    )
    artikli_service.brisi_artikal(artikal_id, actor=admin)
    uredjaj_id = conn.execute(
        "SELECT id FROM uredjaji WHERE ime = ?", ("PC1",)
    ).fetchone()[0]
    uredjaji_service.brisi_uredjaj(uredjaj_id, actor=admin)

    akcije = _akcije(conn)
    assert {
        "DEVICE_CREATED", "DEVICE_GROUP_PRICE_CHANGED", "DEVICE_DELETED",
        "ARTICLE_CREATED", "ARTICLE_UPDATED", "ARTICLE_DELETED",
    }.issubset(akcije)


def test_audit_filteri_korisnika_datuma_i_akcije(db):
    _conn, admin = db
    manager_id = users_service.kreiraj_korisnika(
        admin, "manager", "Manager", "lozinka", ROLA_MANAGER
    )
    manager = users_service.prijavi_korisnika("manager", "lozinka")
    audit_service.upisi_audit(
        manager, "TEST_ACTION", "test", entitet_id=77,
        detalj="ciljani zapis"
    )

    rezultat = audit_service.dohvati_audit(
        admin,
        datum_od=date.today(),
        datum_do=date.today(),
        user_id=manager_id,
        akcija="TEST_ACTION",
    )
    assert rezultat["ukupno"] == 1
    assert rezultat["stavke"][0]["detalj"] == "ciljani zapis"
    sutra = date.today() + timedelta(days=1)
    assert audit_service.dohvati_audit(
        admin, datum_od=sutra, datum_do=sutra
    )["ukupno"] == 0


def test_audit_limit_i_paginacija_imaju_stabilan_sort(db):
    _conn, admin = db
    for broj in range(5):
        audit_service.upisi_audit(
            admin, "PAGE_TEST", "test", entitet_id=broj,
            detalj=f"zapis-{broj}"
        )
    prva = audit_service.dohvati_audit(
        admin, akcija="PAGE_TEST", limit=2, offset=0
    )
    druga = audit_service.dohvati_audit(
        admin, akcija="PAGE_TEST", limit=2, offset=2
    )
    assert prva["ukupno"] == 5
    assert [r["detalj"] for r in prva["stavke"]] == ["zapis-4", "zapis-3"]
    assert [r["detalj"] for r in druga["stavke"]] == ["zapis-2", "zapis-1"]


def test_radnik_ne_moze_citati_puni_audit(db):
    _conn, admin = db
    users_service.kreiraj_korisnika(
        admin, "radnik", "Radnik", "lozinka", ROLA_RADNIK
    )
    radnik = users_service.prijavi_korisnika("radnik", "lozinka")
    with pytest.raises(PermissionError):
        audit_service.dohvati_audit(radnik)


def test_pad_audita_rollbackuje_naplatu_sesije(db, monkeypatch):
    conn, admin = db
    smjena_id = smjena_service.otvori_smjenu(admin)
    sesija = SessionState(
        vreme_starta=datetime.now() - timedelta(minutes=30),
        tip="neograniceno",
    )
    pazar_service.start_sesija("PC1", sesija, smjena_id, actor=admin)

    def greska(*_args, **_kwargs):
        raise RuntimeError("audit nije dostupan")

    monkeypatch.setattr(pazar_service, "upisi_audit_u_transakciji", greska)
    with pytest.raises(RuntimeError, match="audit"):
        pazar_service.naplati_uredjaj(
            "PC1", sesija, [], 2.0, smjena_id, actor=admin
        )

    lifecycle = conn.execute(
        """SELECT vreme_kraja, iznos FROM sesije_log
           WHERE smjena_id = ? AND uredjaj = ?""",
        (smjena_id, "PC1"),
    ).fetchone()
    assert lifecycle["vreme_kraja"] is None
    assert lifecycle["iznos"] is None
    assert conn.execute(
        "SELECT COUNT(*) FROM pazar_arhiva WHERE smjena_id = ?",
        (smjena_id,),
    ).fetchone()[0] == 0
    assert conn.in_transaction is False
