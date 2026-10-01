from datetime import date, datetime, timedelta
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QDialog, QMessageBox

import ui.rezervacije as rezervacije_ui
from models.app_state import AppState
from models.user import UserIdentity
from ui.kartica_uredjaja import UredjajKartica
from ui.rezervacije import GrupnaRezervacijaDijalog, RezervacijeDijalog
from ui.timeline_rezervacija import RezervacijeTimeline


TEST_ACTOR = UserIdentity(1, "tester", "Tester", "admin")
UREDJAJI = [
    {"id": 11, "ime": "PC1", "cena": 2.0, "tip": "PC", "grupa": "Classic"},
    {"id": 12, "ime": "PC2", "cena": 2.0, "tip": "PC", "grupa": "Classic"},
    {"id": 13, "ime": "PC3", "cena": 3.0, "tip": "PC", "grupa": "VIP"},
]


def _red(
    rezervacija_id=1,
    *,
    uredjaj_id=11,
    uredjaj="PC1",
    sat=18,
    status="rezervisano",
    grupa_id=None,
    grupa_velicina=None,
):
    pocetak = (datetime.now() + timedelta(days=2)).replace(
        hour=sat, minute=0, second=0, microsecond=0
    )
    return {
        "id": rezervacija_id,
        "uredjaj_id": uredjaj_id,
        "uredjaj": uredjaj,
        "tip_uredjaja": "PC",
        "ime_gosta": "Ivan" if grupa_id else "Marko",
        "telefon": None,
        "pocetak": pocetak.isoformat(),
        "kraj": (pocetak + timedelta(hours=2)).isoformat(),
        "status": status,
        "napomena": None,
        "kreirao_radnik": "Tester",
        "grupa_id": grupa_id,
        "grupa_velicina": grupa_velicina,
    }


def _grupa():
    pocetak = (datetime.now() + timedelta(days=2)).replace(
        hour=18, minute=0, second=0, microsecond=0
    )
    return {
        "id": 7,
        "ime_gosta": "Ivan",
        "telefon": "061111222",
        "pocetak": pocetak.isoformat(),
        "kraj": (pocetak + timedelta(hours=2)).isoformat(),
        "status": "rezervisano",
        "napomena": "Tim",
        "uredjaji": [UREDJAJI[0], UREDJAJI[1]],
    }


@pytest.fixture
def ui_servisi(monkeypatch):
    stanje = {"redovi": [_red()]}
    dohvati = Mock(side_effect=lambda **_kwargs: list(stanje["redovi"]))
    kreiraj_grupu = Mock(return_value=7)
    izmijeni_grupu = Mock()
    status_grupe = Mock()
    monkeypatch.setattr(rezervacije_ui, "ucitaj_uredjaje", lambda: UREDJAJI)
    monkeypatch.setattr(rezervacije_ui, "dohvati_rezervacije", dohvati)
    monkeypatch.setattr(
        rezervacije_ui, "dohvati_rezervacijsku_grupu", lambda _gid: _grupa()
    )
    monkeypatch.setattr(
        rezervacije_ui, "kreiraj_rezervacijsku_grupu", kreiraj_grupu
    )
    monkeypatch.setattr(
        rezervacije_ui, "izmijeni_rezervacijsku_grupu", izmijeni_grupu
    )
    monkeypatch.setattr(
        rezervacije_ui,
        "promijeni_status_rezervacijske_grupe",
        status_grupe,
    )
    return stanje, dohvati, kreiraj_grupu, izmijeni_grupu, status_grupe


def _dijalog(qtbot, ui_servisi):
    dijalog = RezervacijeDijalog(
        actor_getter=lambda: TEST_ACTOR, smjena_id_getter=lambda: 9
    )
    qtbot.addWidget(dijalog)
    return dijalog


def test_timeline_se_kreira(qtbot):
    timeline = RezervacijeTimeline()
    qtbot.addWidget(timeline)
    assert timeline._scroll.widget().objectName() == "timelineCanvas"


def test_timeline_praznog_dana_ne_pada(qtbot):
    timeline = RezervacijeTimeline()
    qtbot.addWidget(timeline)
    timeline.set_podaci(UREDJAJI, [], date.today())
    assert timeline.blokovi == []


def test_pojedinacna_rezervacija_se_prikazuje(qtbot):
    timeline = RezervacijeTimeline()
    qtbot.addWidget(timeline)
    timeline.set_podaci(UREDJAJI, [_red()], date.today())
    assert len(timeline.blokovi) == 1
    assert timeline.blokovi[0].text() == "Marko"


def test_grupna_rezervacija_se_prikazuje_na_vise_uredjaja(qtbot):
    timeline = RezervacijeTimeline()
    qtbot.addWidget(timeline)
    redovi = [
        _red(1, grupa_id=7, grupa_velicina=2),
        _red(2, uredjaj_id=12, uredjaj="PC2", grupa_id=7, grupa_velicina=2),
    ]
    timeline.set_podaci(UREDJAJI, redovi, date.today())
    assert [blok.text() for blok in timeline.blokovi] == [
        "Grupa Ivan (2)", "Grupa Ivan (2)"
    ]


def test_ista_vremenska_pozicija_je_konzistentna_po_redovima(qtbot):
    timeline = RezervacijeTimeline()
    qtbot.addWidget(timeline)
    redovi = [
        _red(1),
        _red(2, uredjaj_id=12, uredjaj="PC2"),
    ]
    timeline.set_podaci(UREDJAJI, redovi, date.today())
    assert timeline.blokovi[0].x() == timeline.blokovi[1].x()
    assert timeline.blokovi[0].width() == timeline.blokovi[1].width()


def test_promjena_datuma_refreshuje_timeline(qtbot, ui_servisi):
    dijalog = _dijalog(qtbot, ui_servisi)
    _stanje, dohvati, *_ = ui_servisi
    broj_prije = dohvati.call_count
    dijalog.inp_datum.setDate(QDate.currentDate().addDays(1))
    assert dohvati.call_count == broj_prije + 1


def test_klik_bloka_otvara_izmjenu(qtbot, ui_servisi, monkeypatch):
    dijalog = _dijalog(qtbot, ui_servisi)
    izmijeni = Mock()
    monkeypatch.setattr(dijalog, "_izmijeni", izmijeni)
    qtbot.mouseClick(dijalog.timeline.blokovi[0], Qt.MouseButton.LeftButton)
    izmijeni.assert_called_once_with()


def test_grupni_dijalog_se_kreira(qtbot, monkeypatch):
    monkeypatch.setattr(
        rezervacije_ui,
        "dohvati_slobodne_uredjaje_za_period",
        lambda *_args, **_kwargs: UREDJAJI,
    )
    forma = GrupnaRezervacijaDijalog(None, UREDJAJI)
    qtbot.addWidget(forma)
    assert forma.windowTitle() == "Nova grupna rezervacija"
    assert forma.lista_uredjaja.count() == 3


def test_grupni_dijalog_podrzava_multi_select(qtbot, monkeypatch):
    monkeypatch.setattr(
        rezervacije_ui,
        "dohvati_slobodne_uredjaje_za_period",
        lambda *_args, **_kwargs: UREDJAJI,
    )
    forma = GrupnaRezervacijaDijalog(None, UREDJAJI)
    qtbot.addWidget(forma)
    forma.lista_uredjaja.item(0).setSelected(True)
    forma.lista_uredjaja.item(1).setSelected(True)
    assert len(forma.lista_uredjaja.selectedItems()) == 2


def test_prijedlog_odabire_slobodne_uredjaje(qtbot, monkeypatch):
    servis = Mock(return_value=UREDJAJI[:2])
    monkeypatch.setattr(
        rezervacije_ui, "dohvati_slobodne_uredjaje_za_period", servis
    )
    forma = GrupnaRezervacijaDijalog(None, UREDJAJI)
    qtbot.addWidget(forma)
    forma._predlozi()
    odabrani = {
        stavka.data(Qt.ItemDataRole.UserRole)
        for stavka in forma.lista_uredjaja.selectedItems()
    }
    assert odabrani == {11, 12}
    assert servis.call_args.kwargs["broj"] == 2


class _PrihvacenaGrupnaForma:
    pocetak = datetime.now() + timedelta(days=3)
    rezultat = {
        "uredjaj_ids": [11, 12],
        "ime_gosta": "Ivan",
        "telefon": None,
        "pocetak": pocetak,
        "kraj": pocetak + timedelta(hours=2),
        "napomena": None,
    }

    def __init__(self, *_args, **_kwargs):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted


def test_konflikt_grupe_prikazuje_warning(qtbot, ui_servisi, monkeypatch):
    dijalog = _dijalog(qtbot, ui_servisi)
    _stanje, _dohvati, kreiraj, *_ = ui_servisi
    kreiraj.side_effect = ValueError("Konflikt na PC2")
    monkeypatch.setattr(
        rezervacije_ui, "GrupnaRezervacijaDijalog", _PrihvacenaGrupnaForma
    )
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    dijalog._nova_grupa()
    assert "PC2" in warning.call_args.args[2]


def test_validna_grupa_se_sacuvava(qtbot, ui_servisi, monkeypatch):
    dijalog = _dijalog(qtbot, ui_servisi)
    _stanje, _dohvati, kreiraj, *_ = ui_servisi
    monkeypatch.setattr(
        rezervacije_ui, "GrupnaRezervacijaDijalog", _PrihvacenaGrupnaForma
    )
    with qtbot.waitSignal(dijalog.rezervacije_changed, timeout=1000):
        dijalog._nova_grupa()
    assert kreiraj.call_args.kwargs["actor"] == TEST_ACTOR
    assert kreiraj.call_args.kwargs["smjena_id"] == 9


def test_edit_grupne_rezervacije_poziva_grupni_servis(
    qtbot, ui_servisi, monkeypatch
):
    stanje, _dohvati, _kreiraj, izmijeni, _status = ui_servisi
    stanje["redovi"] = [_red(grupa_id=7, grupa_velicina=2)]
    dijalog = _dijalog(qtbot, ui_servisi)
    dijalog.tabela.selectRow(0)
    monkeypatch.setattr(
        rezervacije_ui, "GrupnaRezervacijaDijalog", _PrihvacenaGrupnaForma
    )
    dijalog._izmijeni()
    assert izmijeni.call_args.args[0] == 7
    assert izmijeni.call_args.kwargs["actor"] == TEST_ACTOR


def test_status_grupe_refreshuje_timeline(qtbot, ui_servisi, monkeypatch):
    stanje, _dohvati, _kreiraj, _izmijeni, status = ui_servisi
    stanje["redovi"] = [_red(grupa_id=7, grupa_velicina=2)]
    dijalog = _dijalog(qtbot, ui_servisi)
    dijalog.tabela.selectRow(0)
    osvjezi_timeline = Mock(wraps=dijalog.timeline.set_podaci)
    monkeypatch.setattr(dijalog.timeline, "set_podaci", osvjezi_timeline)
    dijalog._promijeni_status("stigao")
    status.assert_called_with(7, "stigao", TEST_ACTOR, 9)
    osvjezi_timeline.assert_called_once()


def test_kartica_prikazuje_grupnu_rezervaciju(qtbot):
    kartica = UredjajKartica(
        "PC1", "PC", 2.0, AppState(), lambda: [], uredjaj_id=11
    )
    qtbot.addWidget(kartica)
    kartica.postavi_narednu_rezervaciju(
        _red(grupa_id=7, grupa_velicina=5)
    )
    assert "Grupa Ivan (5 PC)" in kartica._lbl_rezervacija.text()


def test_refresh_timelinea_ne_duplira_blokove(qtbot, ui_servisi):
    dijalog = _dijalog(qtbot, ui_servisi)
    dijalog.osvjezi()
    dijalog.osvjezi()
    assert len(dijalog.timeline.blokovi) == 1
