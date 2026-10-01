from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

import database.db as db_module
import services.pazar as pazar_service
import services.smjena as smjena_service
import services.users as users_service
import ui.audit as audit_ui
import ui.korisnici as korisnici_ui
import ui.login as login_ui
from models.app_state import AppState
from models.session_state import SessionState
from models.user import UserIdentity
from services.permissions import ROLA_ADMIN, ROLA_MANAGER, ROLA_RADNIK
from tests.helpers import napravi_test_korisnika
from ui.glavni_prozor import GlavniProzor, _MainWindow
from ui.login import FirstRunDijalog, LoginDijalog


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    AppState().odjavi_korisnika()
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "auth-ui.sqlite3"))
    db_module.inicijalizuj_bazu()
    yield db_module.get_db()
    AppState().odjavi_korisnika()
    db_module.zatvori_bazu()


def _presretni_warning(monkeypatch):
    warning = Mock(return_value=QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    return warning


def test_first_run_dijalog_kreira_admina(qtbot, monkeypatch):
    admin = UserIdentity(1, "admin", "Administrator", ROLA_ADMIN)
    kreiraj = Mock(return_value=admin)
    monkeypatch.setattr(login_ui, "kreiraj_prvog_admina", kreiraj)
    dijalog = FirstRunDijalog("novi_admin")
    qtbot.addWidget(dijalog)
    dijalog.inp_username.setText("admin")
    dijalog.inp_ime.setText("Administrator")
    dijalog.inp_lozinka.setText("sigurna")
    dijalog.inp_potvrda.setText("sigurna")

    dijalog._kreiraj()

    assert dijalog.result() == QDialog.DialogCode.Accepted
    assert dijalog.korisnik == admin
    kreiraj.assert_called_once_with("admin", "Administrator", "sigurna")


def test_login_dijalog_prihvata_validan_login(qtbot, monkeypatch):
    admin = UserIdentity(1, "admin", "Administrator", ROLA_ADMIN)
    prijava = Mock(return_value=admin)
    monkeypatch.setattr(login_ui, "prijavi_korisnika", prijava)
    dijalog = LoginDijalog()
    qtbot.addWidget(dijalog)
    dijalog.inp_username.setText("admin")
    dijalog.inp_lozinka.setText("sigurna")

    dijalog._prijavi()

    assert dijalog.result() == QDialog.DialogCode.Accepted
    assert dijalog.korisnik == admin


def test_login_dijalog_daje_genericku_poruku_za_neispravne_podatke(
    qtbot, monkeypatch
):
    monkeypatch.setattr(login_ui, "prijavi_korisnika", lambda *_: None)
    warning = _presretni_warning(monkeypatch)
    dijalog = LoginDijalog()
    qtbot.addWidget(dijalog)
    dijalog.inp_username.setText("ne-postoji")
    dijalog.inp_lozinka.setText("pogresna")

    dijalog._prijavi()

    assert dijalog.result() == QDialog.DialogCode.Rejected
    assert warning.call_args.args[2] == (
        "Neispravno korisničko ime ili lozinka."
    )


def test_deaktiviran_korisnik_se_ne_moze_prijaviti_kroz_ui(
    qtbot, db, monkeypatch
):
    admin = users_service.kreiraj_prvog_admina(
        "admin", "Administrator", "sigurna"
    )
    user_id = users_service.kreiraj_korisnika(
        admin, "radnik", "Radnik", "lozinka", ROLA_RADNIK
    )
    users_service.postavi_aktivnost(admin, user_id, False)
    warning = _presretni_warning(monkeypatch)
    dijalog = LoginDijalog()
    qtbot.addWidget(dijalog)
    dijalog.inp_username.setText("radnik")
    dijalog.inp_lozinka.setText("lozinka")

    dijalog._prijavi()

    assert dijalog.korisnik is None
    assert "Neispravno korisničko ime" in warning.call_args.args[2]


@pytest.mark.parametrize(
    ("rola", "vidljivo"),
    [
        (
            ROLA_RADNIK,
            {"Gaming", "Smjena", "Dashboard", "Rezervacije", "Odjava"},
        ),
        (
            ROLA_MANAGER,
            {
                "Gaming", "Smjena", "Dashboard", "Historija", "Rezervacije",
                "Izvještaji", "Audit", "Odjava",
            },
        ),
        (
            ROLA_ADMIN,
            {
                "Gaming", "Smjena", "Dashboard", "Historija", "Rezervacije",
                "Izvještaji", "Audit", "Admin", "Korisnici", "Odjava",
            },
        ),
    ],
)
def test_navigacija_prati_centralne_dozvole(qtbot, db, rola, vidljivo):
    actor = napravi_test_korisnika(db, username=rola, ime=rola, rola=rola)
    AppState().prijavi_korisnika(actor)
    prozor = _MainWindow()
    qtbot.addWidget(prozor)
    prozor._timer.stop()
    prozor._rezervacije_timer.stop()
    assert set(prozor._nav_buttons) == vidljivo


class _PrihvacenNoviKorisnik:
    rezultat = {
        "korisnicko_ime": "mira",
        "ime": "Mira",
        "lozinka": "lozinka",
        "rola": ROLA_RADNIK,
    }

    def __init__(self, *_args, **_kwargs):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted


def test_korisnici_ui_kreira_mijenja_rolu_i_deaktivira(qtbot, db, monkeypatch):
    admin = napravi_test_korisnika(db)
    dijalog = korisnici_ui.KorisniciDijalog(admin)
    qtbot.addWidget(dijalog)
    monkeypatch.setattr(
        korisnici_ui, "NoviKorisnikDijalog", _PrihvacenNoviKorisnik
    )
    dijalog._novi()
    assert dijalog.tabela.rowCount() == 2

    red_mire = next(
        i for i in range(dijalog.tabela.rowCount())
        if dijalog.tabela.item(i, 0).text() == "mira"
    )
    dijalog.tabela.selectRow(red_mire)
    monkeypatch.setattr(
        korisnici_ui.QInputDialog,
        "getItem",
        lambda *_args, **_kwargs: (ROLA_MANAGER, True),
    )
    dijalog._rola()
    assert db.execute(
        "SELECT rola FROM korisnici WHERE korisnicko_ime = ?", ("mira",)
    ).fetchone()[0] == ROLA_MANAGER

    red_mire = next(
        i for i in range(dijalog.tabela.rowCount())
        if dijalog.tabela.item(i, 0).text() == "mira"
    )
    dijalog.tabela.selectRow(red_mire)
    dijalog._aktivnost()
    assert db.execute(
        "SELECT aktivan FROM korisnici WHERE korisnicko_ime = ?", ("mira",)
    ).fetchone()[0] == 0


def test_korisnici_ui_prikazuje_zastitu_posljednjeg_admina(
    qtbot, db, monkeypatch
):
    admin = napravi_test_korisnika(db)
    warning = _presretni_warning(monkeypatch)
    dijalog = korisnici_ui.KorisniciDijalog(admin)
    qtbot.addWidget(dijalog)
    dijalog.tabela.selectRow(0)
    dijalog._aktivnost()
    warning.assert_called_once()
    assert db.execute(
        "SELECT aktivan FROM korisnici WHERE id = ?", (admin.id,)
    ).fetchone()[0] == 1


def _audit_red(broj):
    return {
        "id": broj,
        "vreme": "2026-10-01T10:00:00",
        "smjena_id": 1,
        "user_id": 1,
        "username": "admin",
        "radnik": "Administrator",
        "uredjaj": "PC1",
        "akcija": "TEST",
        "entitet": "test",
        "entitet_id": str(broj),
        "detalj": f"Detalj {broj}",
    }


@pytest.fixture
def audit_servisi(monkeypatch):
    redovi = [_audit_red(3), _audit_red(2), _audit_red(1)]
    opcije = {
        "korisnici": [{"user_id": 1, "naziv": "admin"}],
        "akcije": ["TEST"],
        "entiteti": ["test"],
        "uredjaji": ["PC1"],
    }
    dohvati = Mock(
        side_effect=lambda _actor, limit, offset, **_filteri: {
            "stavke": redovi[offset:offset + limit],
            "ukupno": len(redovi),
            "limit": limit,
            "offset": offset,
        }
    )
    monkeypatch.setattr(audit_ui, "dohvati_audit_opcije", lambda _actor: opcije)
    monkeypatch.setattr(audit_ui, "dohvati_audit", dohvati)
    return redovi, dohvati


def test_audit_ui_tabela_refresh_filteri_i_paginacija(qtbot, audit_servisi):
    _redovi, dohvati = audit_servisi
    actor = UserIdentity(1, "admin", "Administrator", ROLA_ADMIN)
    dijalog = audit_ui.AuditDijalog(actor, limit=2)
    qtbot.addWidget(dijalog)
    assert dijalog.tabela.rowCount() == 2
    dijalog.osvjezi()
    assert dijalog.tabela.rowCount() == 2
    dijalog.cmb_akcija.setCurrentIndex(1)
    dijalog._reset_i_osvjezi()
    assert dohvati.call_args.kwargs["akcija"] == "TEST"
    dijalog._sljedeca()
    assert dijalog.tabela.rowCount() == 1
    assert dijalog.offset == 2


def test_audit_ui_prazno_stanje_ne_pada(qtbot, monkeypatch):
    monkeypatch.setattr(
        audit_ui,
        "dohvati_audit_opcije",
        lambda _actor: {
            "korisnici": [], "akcije": [], "entiteti": [], "uredjaji": []
        },
    )
    monkeypatch.setattr(
        audit_ui,
        "dohvati_audit",
        lambda *_args, **_kwargs: {
            "stavke": [], "ukupno": 0, "limit": 20, "offset": 0
        },
    )
    dijalog = audit_ui.AuditDijalog(
        UserIdentity(1, "admin", "Administrator", ROLA_ADMIN), limit=20
    )
    qtbot.addWidget(dijalog)
    assert dijalog.tabela.rowCount() == 0
    assert dijalog.lbl_stranica.text() == "0–0 / 0"


def test_logout_otvara_login_tok_i_ne_mijenja_aktivnu_sesiju(db):
    actor = napravi_test_korisnika(db)
    AppState().prijavi_korisnika(actor)
    smjena_id = smjena_service.otvori_smjenu(actor)
    AppState().postavi_smjenu(smjena_id, actor.ime)
    sesija = SessionState(vreme_starta=datetime.now(), tip="neograniceno")
    pazar_service.start_sesija("PC1", sesija, smjena_id, actor=actor)
    prije = [
        dict(red) for red in db.execute(
            "SELECT * FROM sesije_log ORDER BY id"
        ).fetchall()
    ]

    wrapper = GlavniProzor.__new__(GlavniProzor)
    wrapper.state = AppState()
    wrapper._window = Mock()
    wrapper._qapp = Mock()
    wrapper._prijavi_korisnika = Mock(return_value=False)
    wrapper._otvori_glavni_prozor = Mock()
    wrapper._odjava()

    wrapper._prijavi_korisnika.assert_called_once_with()
    wrapper._qapp.quit.assert_called_once_with()
    assert AppState().trenutni_korisnik() is None
    assert db.execute(
        "SELECT COUNT(*) FROM logovi WHERE akcija = 'LOGOUT' AND user_id = ?",
        (actor.id,),
    ).fetchone()[0] == 1
    assert smjena_service.dohvati_aktivnu_smjenu()["id"] == smjena_id
    poslije = [
        dict(red) for red in db.execute(
            "SELECT * FROM sesije_log ORDER BY id"
        ).fetchall()
    ]
    assert poslije == prije


def test_logout_odmah_zatvara_dijaloge_sa_starim_actorom(qtbot, db):
    actor = napravi_test_korisnika(db)
    AppState().prijavi_korisnika(actor)
    prozor = _MainWindow()
    qtbot.addWidget(prozor)
    prozor._timer.stop()
    prozor._rezervacije_timer.stop()
    prozor._otvori_korisnike()
    prozor._otvori_audit()
    korisnici = prozor._korisnici_dlg
    audit = prozor._audit_dlg
    assert korisnici.actor == actor
    assert audit.actor == actor

    wrapper = GlavniProzor.__new__(GlavniProzor)
    wrapper.state = AppState()
    wrapper._window = prozor
    wrapper._qapp = Mock()
    wrapper._prijavi_korisnika = Mock(return_value=False)
    wrapper._otvori_glavni_prozor = Mock()

    wrapper._odjava()

    assert korisnici.actor is None
    assert audit.actor is None
    assert korisnici.isHidden()
    assert audit.isHidden()
    assert prozor._bocni.actor_getter() is None
