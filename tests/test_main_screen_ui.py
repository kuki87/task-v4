from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QLabel

import database.db as db_module
import services.rezervacije as rezervacije_service
import ui.glavni_prozor as glavni_ui
from models.app_state import AppState
from models.artikal import Artikal
from models.session_state import SessionState
from services.permissions import ROLA_ADMIN, ROLA_MANAGER, ROLA_RADNIK
from tests.helpers import napravi_test_korisnika
from ui.glavni_prozor import GlavniProzor, _MainWindow
from ui.kartica_uredjaja import UredjajKartica


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    AppState().odjavi_korisnika()
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "main-screen.sqlite3"))
    db_module.inicijalizuj_bazu()
    yield db_module.get_db()
    AppState().odjavi_korisnika()
    db_module.zatvori_bazu()


def _dodaj_uredjaje(db, broj=1):
    for indeks in range(1, broj + 1):
        db.execute(
            """INSERT INTO uredjaji (ime, cena, tip, grupa)
               VALUES (?, ?, ?, ?)""",
            (f"PC{indeks}", 2.5, "PC", "Classic"),
        )
    db.commit()


def _prozor(qtbot, db, *, rola=ROLA_RADNIK, uredjaji=1):
    _dodaj_uredjaje(db, uredjaji)
    actor = napravi_test_korisnika(
        db, username=f"ui-{rola}", ime=rola.title(), rola=rola
    )
    AppState().prijavi_korisnika(actor)
    prozor = _MainWindow()
    qtbot.addWidget(prozor)
    prozor._timer.stop()
    prozor._rezervacije_timer.stop()
    return prozor, actor


@pytest.mark.parametrize(
    ("rola", "ocekivano", "zabranjeno"),
    [
        (
            ROLA_RADNIK,
            {"Gaming", "Smjena", "Rezervacije", "Dashboard", "Odjava"},
            {"Historija", "Izvještaji", "Audit", "Admin", "Korisnici"},
        ),
        (
            ROLA_MANAGER,
            {
                "Gaming", "Smjena", "Rezervacije", "Dashboard",
                "Historija", "Izvještaji", "Audit", "Odjava",
            },
            {"Admin", "Korisnici"},
        ),
        (
            ROLA_ADMIN,
            {
                "Gaming", "Smjena", "Rezervacije", "Dashboard",
                "Historija", "Izvještaji", "Audit", "Admin",
                "Korisnici", "Odjava",
            },
            set(),
        ),
    ],
)
def test_glavni_ekran_se_kreira_i_prati_permissions(
    qtbot, db, rola, ocekivano, zabranjeno
):
    prozor, _actor = _prozor(qtbot, db, rola=rola, uredjaji=0)

    assert set(prozor._nav_buttons) == ocekivano
    assert zabranjeno.isdisjoint(prozor._nav_buttons)
    assert prozor.centralWidget() is not None


def test_navigacija_je_grupisana_u_bocni_sidebar(qtbot, db):
    prozor, _actor = _prozor(qtbot, db, rola=ROLA_ADMIN, uredjaji=0)
    sidebar = prozor.findChild(type(prozor._alert_bar), "navigationSidebar")

    assert sidebar is not None
    assert prozor._nav_buttons["Gaming"].parent() is sidebar
    assert prozor._nav_buttons["Historija"].parent() is sidebar
    assert prozor._nav_buttons["Admin"].parent() is sidebar
    assert prozor._nav_buttons["Odjava"].parent().objectName() == "topbar"


def _kartica(qtbot):
    kartica = UredjajKartica(
        "PC1", "PC", 2.5, AppState(), lambda: [], uredjaj_id=1,
        grupa="Classic",
    )
    qtbot.addWidget(kartica)
    return kartica


def test_slobodna_kartica_prikazuje_samo_start_kao_primarnu_akciju(qtbot):
    kartica = _kartica(qtbot)
    kartica.osvjezi()

    assert not kartica._btn_start.isHidden()
    assert kartica._btn_naplati.isHidden()
    assert "2.50 KM/h" in kartica._lbl_meta.text()


def test_aktivna_kartica_prikazuje_naplati_i_operativne_akcije(qtbot):
    kartica = _kartica(qtbot)
    kartica.session = SessionState(
        vreme_starta=datetime.now() - timedelta(minutes=15),
        tip="neograniceno",
    )
    kartica.kosarica = [Artikal("Kafa", 2.0, 2)]
    kartica.osvjezi()

    assert kartica._btn_start.isHidden()
    assert not kartica._btn_naplati.isHidden()
    assert not kartica._btn_prebaci.isHidden()
    assert not kartica._btn_vise.isHidden()
    assert kartica._lbl_kosarica.text() == "Artikli: 2 · 4.00 KM"


def test_prepaid_kartica_prikazuje_countdown(qtbot):
    kartica = _kartica(qtbot)
    kartica.session = SessionState(
        vreme_starta=datetime.now() - timedelta(minutes=1),
        limit_sekundi=10 * 60,
        is_prepaid=True,
        tip="prepaid",
    )
    kartica.osvjezi()

    assert kartica._lbl_badge.text().startswith("⚠ PREPAID")
    assert kartica._lbl_earning.text().startswith("Preostalo:")
    assert kartica._progress.isVisibleTo(kartica)


def _rezervacija(uredjaj_id=1, *, za_minuta=12):
    pocetak = datetime.now() + timedelta(minutes=za_minuta)
    return {
        "id": 1,
        "uredjaj_id": uredjaj_id,
        "ime_gosta": "Marko",
        "pocetak": pocetak.isoformat(),
        "kraj": (pocetak + timedelta(hours=1)).isoformat(),
        "status": "rezervisano",
    }


def test_naredna_rezervacija_se_prikazuje_na_kartici(qtbot):
    kartica = _kartica(qtbot)
    kartica.postavi_narednu_rezervaciju(_rezervacija())

    assert kartica.naredna_rezervacija is not None
    assert kartica._lbl_rezervacija.text().startswith("REZ ")
    assert "Marko" in kartica._lbl_rezervacija.text()


def test_alert_bar_prikazuje_rezervaciju_uskoro(qtbot, db):
    prozor, _actor = _prozor(qtbot, db)
    prozor.kartice[0].postavi_narednu_rezervaciju(_rezervacija())
    prozor._osvjezi_alert_bar()

    assert not prozor._alert_bar.isHidden()
    assert "rezervacija za" in prozor._btn_alert.text()
    assert "PC1" in prozor._btn_alert.text()


def test_alert_bar_prikazuje_sesiju_pred_istekom(qtbot, db):
    prozor, _actor = _prozor(qtbot, db)
    prozor.kartice[0].session = SessionState(
        vreme_starta=datetime.now() - timedelta(minutes=9),
        limit_sekundi=10 * 60,
        is_prepaid=True,
        tip="prepaid",
    )
    prozor._osvjezi_alert_bar()

    assert not prozor._alert_bar.isHidden()
    assert "ističe" in prozor._btn_alert.text()


def test_identican_tick_ne_radi_puni_rebuild(qtbot, db):
    prozor, _actor = _prozor(qtbot, db)
    prozor._render_kartice = Mock(wraps=prozor._render_kartice)

    prozor._tick()
    prozor._tick()

    prozor._render_kartice.assert_not_called()


def test_session_event_osvjezava_odgovarajucu_karticu(qtbot, db):
    prozor, _actor = _prozor(qtbot, db, uredjaji=2)
    prva, druga = prozor.kartice
    prva.osvjezi = Mock(wraps=prva.osvjezi)
    druga.osvjezi = Mock(wraps=druga.osvjezi)

    prva.session_changed.emit(prva.ime)

    prva.osvjezi.assert_called_once_with()
    druga.osvjezi.assert_not_called()


def test_reservation_event_osvjezava_podatke_kartice(
    qtbot, db, monkeypatch
):
    prozor, _actor = _prozor(qtbot, db)
    red = _rezervacija(prozor.kartice[0].uredjaj_id)
    monkeypatch.setattr(
        rezervacije_service,
        "dohvati_naredne_rezervacije_uredjaja",
        lambda _ids: {prozor.kartice[0].uredjaj_id: red},
    )

    prozor._osvjezi_rezervacije_kartica()

    assert prozor.kartice[0].naredna_rezervacija == red
    assert "Marko" in prozor.kartice[0]._lbl_rezervacija.text()


def test_pazar_status_se_osvjezava_samo_na_dogadjaj(
    qtbot, db, monkeypatch
):
    prozor, _actor = _prozor(qtbot, db)
    AppState().postavi_smjenu(7, "Radnik")
    prozor._smjena_pocetak = datetime.now() - timedelta(hours=1)
    dohvati = Mock(return_value={"ukupno": 42.5})
    monkeypatch.setattr(glavni_ui, "dohvati_pazar_smjene", dohvati)

    prozor._pazar_promijenjen()
    prozor._tick()

    assert prozor._lbl_pazar.text() == "Pazar: 42.50 KM"
    dohvati.assert_called_once_with(7)


def test_logout_odmah_uklanja_stari_user_state(qtbot, db):
    prozor, actor = _prozor(qtbot, db)
    wrapper = GlavniProzor.__new__(GlavniProzor)
    wrapper.state = AppState()
    wrapper._window = prozor
    wrapper._qapp = Mock()
    wrapper._prijavi_korisnika = Mock(return_value=False)
    wrapper._otvori_glavni_prozor = Mock()

    wrapper._odjava()

    assert actor.id is not None
    assert AppState().trenutni_korisnik() is None
    assert prozor.isHidden()


def test_manji_prozor_mijenja_broj_kolona_bez_render_petlje(qtbot, db):
    prozor, _actor = _prozor(qtbot, db, uredjaji=8)
    prozor.show()
    prozor.resize(1400, 700)
    qtbot.wait(20)
    siroko = prozor._max_per_row
    prozor._render_kartice = Mock(wraps=prozor._render_kartice)

    prozor.resize(760, 700)
    qtbot.wait(20)
    usko = prozor._max_per_row
    pozivi = prozor._render_kartice.call_count
    prozor.resize(761, 700)
    qtbot.wait(20)

    assert usko < siroko
    assert pozivi >= 1
    assert prozor._render_kartice.call_count == pozivi


def test_prazno_stanje_bez_uredjaja_ne_pada(qtbot, db):
    prozor, _actor = _prozor(qtbot, db, uredjaji=0)
    tekstovi = [lbl.text() for lbl in prozor.findChildren(QLabel)]

    assert prozor.kartice == []
    assert "Nema uređaja u bazi" in tekstovi
