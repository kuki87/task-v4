from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QDialog, QMessageBox

import services.rezervacije as rezervacije_service
import ui.rezervacije as rezervacije_ui
from models.app_state import AppState
from ui.kartica_uredjaja import UredjajKartica
from ui.rezervacije import RezervacijaFormaDijalog, RezervacijeDijalog


def _red(rezervacija_id=1, *, status="rezervisano", gost="Marko", uredjaj="PC1"):
    pocetak = (datetime.now() + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    return {
        "id": rezervacija_id,
        "uredjaj_id": 11 if uredjaj == "PC1" else 12,
        "uredjaj": uredjaj,
        "tip_uredjaja": "PC",
        "ime_gosta": gost,
        "telefon": "061111222",
        "pocetak": pocetak.isoformat(),
        "kraj": (pocetak + timedelta(hours=1)).isoformat(),
        "status": status,
        "napomena": "Prozor",
        "kreirano": datetime.now().isoformat(),
        "izmijenjeno": datetime.now().isoformat(),
        "kreirao_radnik": "Tester",
    }


@pytest.fixture
def ui_servisi(monkeypatch):
    uredjaji = [
        {"id": 11, "ime": "PC1", "cena": 2.0, "tip": "PC", "grupa": "Classic"},
        {"id": 12, "ime": "PC2", "cena": 2.0, "tip": "PC", "grupa": "Classic"},
    ]
    stanje = {"redovi": [_red()]}

    def dohvati(**filteri):
        redovi = list(stanje["redovi"])
        if filteri.get("uredjaj_id") is not None:
            redovi = [r for r in redovi if r["uredjaj_id"] == filteri["uredjaj_id"]]
        if filteri.get("status") is not None:
            redovi = [r for r in redovi if r["status"] == filteri["status"]]
        trazeno = (filteri.get("pretraga") or "").lower()
        if trazeno:
            redovi = [r for r in redovi if trazeno in r["ime_gosta"].lower()]
        return redovi

    dohvati_mock = Mock(side_effect=dohvati)
    kreiraj_mock = Mock(return_value=5)
    izmijeni_mock = Mock()
    status_mock = Mock()
    monkeypatch.setattr(rezervacije_ui, "ucitaj_uredjaje", lambda: uredjaji)
    monkeypatch.setattr(rezervacije_ui, "dohvati_rezervacije", dohvati_mock)
    monkeypatch.setattr(rezervacije_ui, "kreiraj_rezervaciju", kreiraj_mock)
    monkeypatch.setattr(rezervacije_ui, "izmijeni_rezervaciju", izmijeni_mock)
    monkeypatch.setattr(
        rezervacije_ui, "promijeni_status_rezervacije", status_mock
    )
    return stanje, dohvati_mock, kreiraj_mock, izmijeni_mock, status_mock


def _dijalog(qtbot, ui_servisi):
    dijalog = RezervacijeDijalog(
        radnik_getter=lambda: "Tester", smjena_id_getter=lambda: 7
    )
    qtbot.addWidget(dijalog)
    return dijalog


def test_stranica_rezervacija_se_kreira(qtbot, ui_servisi):
    dijalog = _dijalog(qtbot, ui_servisi)
    assert dijalog.windowTitle() == "Rezervacije"
    assert dijalog.tabela.columnCount() == 7


def test_tabela_prikazuje_servisne_podatke(qtbot, ui_servisi):
    dijalog = _dijalog(qtbot, ui_servisi)
    assert dijalog.tabela.rowCount() == 1
    assert dijalog.tabela.item(0, 1).text() == "PC1"
    assert dijalog.tabela.item(0, 2).text() == "Marko"
    assert dijalog.tabela.item(0, 4).text() == "Rezervisano"


def test_prazno_stanje_ne_pada(qtbot, ui_servisi):
    stanje, *_ = ui_servisi
    stanje["redovi"] = []
    dijalog = _dijalog(qtbot, ui_servisi)
    assert dijalog.tabela.rowCount() == 0
    assert not dijalog.btn_izmijeni.isEnabled()


def test_refresh_ne_duplira_redove(qtbot, ui_servisi):
    dijalog = _dijalog(qtbot, ui_servisi)
    dijalog.osvjezi()
    dijalog.osvjezi()
    assert dijalog.tabela.rowCount() == 1


def test_filter_uredjaja_i_statusa_mijenja_prikaz(qtbot, ui_servisi):
    stanje, dohvati_mock, *_ = ui_servisi
    stanje["redovi"] = [_red(1), _red(2, uredjaj="PC2", status="otkazano")]
    dijalog = _dijalog(qtbot, ui_servisi)
    dijalog.cmb_uredjaj.setCurrentIndex(dijalog.cmb_uredjaj.findData(12))
    dijalog.cmb_status.setCurrentIndex(
        dijalog.cmb_status.findData("otkazano")
    )
    assert dijalog.tabela.rowCount() == 1
    assert dijalog.tabela.item(0, 1).text() == "PC2"
    assert dohvati_mock.call_args.kwargs["status"] == "otkazano"


def test_tekstualna_pretraga_mijenja_prikaz(qtbot, ui_servisi):
    stanje, *_ = ui_servisi
    stanje["redovi"] = [_red(1, gost="Marko"), _red(2, gost="Amina")]
    dijalog = _dijalog(qtbot, ui_servisi)
    dijalog.inp_pretraga.setText("amina")
    dijalog.osvjezi()
    assert dijalog.tabela.rowCount() == 1
    assert dijalog.tabela.item(0, 2).text() == "Amina"


def test_forma_odbija_neispravan_interval(qtbot, monkeypatch):
    forma = RezervacijaFormaDijalog(None, [{"id": 11, "ime": "PC1"}])
    qtbot.addWidget(forma)
    forma.inp_gost.setText("Marko")
    forma.inp_pocetak.setTime(QTime(12, 0))
    forma.inp_kraj.setTime(QTime(11, 0))
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    forma._potvrdi()
    warning.assert_called_once()
    assert forma.rezultat is None


def test_forma_prihvata_validan_unos(qtbot):
    forma = RezervacijaFormaDijalog(None, [{"id": 11, "ime": "PC1"}])
    qtbot.addWidget(forma)
    forma.inp_gost.setText("Marko")
    forma.inp_datum.setDate(QDate.currentDate().addDays(1))
    forma.inp_pocetak.setTime(QTime(10, 0))
    forma.inp_kraj.setTime(QTime(11, 0))
    forma._potvrdi()
    assert forma.rezultat["uredjaj_id"] == 11
    assert forma.rezultat["ime_gosta"] == "Marko"


def test_nova_forma_nudi_buduci_pocetak(qtbot):
    forma = RezervacijaFormaDijalog(None, [{"id": 11, "ime": "PC1"}])
    qtbot.addWidget(forma)
    datum = forma.inp_datum.date().toPython()
    pocetak = datetime.combine(datum, forma.inp_pocetak.time().toPython())
    assert pocetak > datetime.now()


class _PrihvacenaForma:
    rezultat = {
        "uredjaj_id": 11,
        "ime_gosta": "Novi gost",
        "telefon": None,
        "pocetak": datetime.now() + timedelta(days=2),
        "kraj": datetime.now() + timedelta(days=2, hours=1),
        "napomena": None,
    }

    def __init__(self, *_args, **_kwargs):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted


def test_nova_rezervacija_poziva_servis_i_emitira_signal(
    qtbot, ui_servisi, monkeypatch
):
    *_, kreiraj_mock, _izmijeni, _status = ui_servisi
    dijalog = _dijalog(qtbot, ui_servisi)
    monkeypatch.setattr(rezervacije_ui, "RezervacijaFormaDijalog", _PrihvacenaForma)
    with qtbot.waitSignal(dijalog.rezervacije_changed, timeout=1000):
        dijalog._nova()
    assert kreiraj_mock.call_args.kwargs["radnik"] == "Tester"
    assert kreiraj_mock.call_args.kwargs["smjena_id"] == 7


def test_konflikt_prikazuje_warning(qtbot, ui_servisi, monkeypatch):
    *_, kreiraj_mock, _izmijeni, _status = ui_servisi
    dijalog = _dijalog(qtbot, ui_servisi)
    kreiraj_mock.side_effect = ValueError("Termin se preklapa")
    monkeypatch.setattr(rezervacije_ui, "RezervacijaFormaDijalog", _PrihvacenaForma)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    dijalog._nova()
    assert "preklapa" in warning.call_args.args[2]


def test_izmjena_poziva_servis(qtbot, ui_servisi, monkeypatch):
    *_prvi, izmijeni_mock, _status = ui_servisi
    dijalog = _dijalog(qtbot, ui_servisi)
    dijalog.tabela.selectRow(0)
    monkeypatch.setattr(rezervacije_ui, "RezervacijaFormaDijalog", _PrihvacenaForma)
    dijalog._izmijeni()
    assert izmijeni_mock.call_args.args[0] == 1
    assert izmijeni_mock.call_args.kwargs["radnik"] == "Tester"


@pytest.mark.parametrize(
    "status", ["stigao", "otkazano", "no_show"]
)
def test_statusne_akcije_pozivaju_servis(qtbot, ui_servisi, status):
    *_, status_mock = ui_servisi
    dijalog = _dijalog(qtbot, ui_servisi)
    dijalog.tabela.selectRow(0)
    dijalog._promijeni_status(status)
    status_mock.assert_called_with(1, status, "Tester", 7)


def test_zavrsetak_stigle_rezervacije(qtbot, ui_servisi):
    stanje, *_sredina, status_mock = ui_servisi
    stanje["redovi"] = [_red(status="stigao")]
    dijalog = _dijalog(qtbot, ui_servisi)
    dijalog.tabela.selectRow(0)
    assert dijalog.btn_zavrsi.isEnabled()
    dijalog._promijeni_status("zavrseno")
    status_mock.assert_called_with(1, "zavrseno", "Tester", 7)


def test_kartica_prikazuje_najblizu_rezervaciju(qtbot):
    kartica = UredjajKartica(
        "PC1", "PC", 2.0, AppState(), lambda: [], uredjaj_id=11
    )
    qtbot.addWidget(kartica)
    kartica.postavi_narednu_rezervaciju(_red())
    assert kartica._lbl_rezervacija.isVisibleTo(kartica)
    assert "Marko" in kartica._lbl_rezervacija.text()
    assert "10:00" in kartica._lbl_rezervacija.text()
    kartica.postavi_narednu_rezervaciju(None)
    assert kartica._lbl_rezervacija.isHidden()


def test_start_sesije_upozorava_na_blisku_rezervaciju(qtbot, monkeypatch):
    pocetak = datetime.now() + timedelta(minutes=20)
    red = _red()
    red["pocetak"] = pocetak.isoformat()
    red["kraj"] = (pocetak + timedelta(hours=1)).isoformat()
    monkeypatch.setattr(
        rezervacije_service, "dohvati_narednu_rezervaciju_uredjaja", lambda *_: red
    )
    pitanje = Mock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "question", pitanje)
    kartica = UredjajKartica(
        "PC1", "PC", 2.0, AppState(), lambda: [], uredjaj_id=11
    )
    qtbot.addWidget(kartica)
    assert not kartica._potvrdi_start_uz_rezervaciju(
        {"tip": "neograniceno", "limit_sekundi": None}
    )
    assert "Marko" in pitanje.call_args.args[2]
