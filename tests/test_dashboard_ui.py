from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QWidget

import ui.prikaz_pazara as dashboard_ui
from ui.prikaz_pazara import PrikazPazara


def _podaci(**izmjene):
    pocetni = {
        "smjena_id": 1,
        "pocetak_smjene": (datetime.now() - timedelta(hours=1)).isoformat(),
        "kraj_smjene": None,
        "radnik": "Tester",
        "ukupno": 15.5,
        "racunari": 8.0,
        "artikli": 3.5,
        "sank": 4.0,
        "broj_transakcija": 3,
        "posljednje_transakcije": [
            {
                "vreme": datetime.now().isoformat(),
                "uredjaj": "PC1",
                "tip_prodaje": "racunar",
                "iznos": 8.0,
            }
        ],
        "ukupno_uredjaja": 8,
        "aktivni_uredjaji": 3,
        "slobodni_uredjaji": 5,
        "aktivne_prepaid_pass": 2,
        "uskoro_isticu": [
            {
                "uredjaj": "PC2",
                "tip": "prepaid",
                "vreme_isteka": (datetime.now() + timedelta(minutes=8)).isoformat(),
                "preostalo_sekundi": 480,
            }
        ],
        "broj_prodanih_artikala": 6,
        "top_artikli": [
            {"naziv_artikla": "Kafa", "kolicina": 6, "ukupno": 9.0}
        ],
        "kretanje_pazara": [
            {"vreme": datetime.now().isoformat(), "ukupno": 8.0},
            {"vreme": datetime.now().isoformat(), "ukupno": 15.5},
        ],
    }
    pocetni.update(izmjene)
    return pocetni


@pytest.fixture
def servis(monkeypatch: pytest.MonkeyPatch):
    mock = Mock(return_value=_podaci())
    monkeypatch.setattr(dashboard_ui, "dohvati_dashboard_smjene", mock)
    return mock


def test_dashboard_moze_biti_kreiran(qtbot, servis):
    dijalog = PrikazPazara(None, smjena_id_getter=lambda: 1)
    qtbot.addWidget(dijalog)

    assert dijalog.windowTitle() == "Operativni dashboard smjene"
    servis.assert_called_once_with(1)


def test_dashboard_prikazuje_servisne_podatke(qtbot, servis):
    dijalog = PrikazPazara(None, smjena_id_getter=lambda: 1)
    qtbot.addWidget(dijalog)

    assert dijalog._lbl_ukupno.text() == "15.50 KM"
    assert dijalog._lbl_racunari.text() == "8.00 KM"
    assert dijalog._lbl_artikli.text() == "3.50 KM"
    assert dijalog._lbl_sank.text() == "4.00 KM"
    assert dijalog._lbl_aktivni.text() == "3"
    assert dijalog._lbl_slobodni.text() == "5"
    assert dijalog._lbl_prepaid.text() == "2"
    assert dijalog._lbl_artikli_broj.text() == "6"
    assert dijalog._tbl_top.rowCount() == 1
    assert dijalog._tbl_top.item(0, 0).text() == "Kafa"
    assert dijalog._tbl_isticu.item(0, 0).text() == "PC2"
    assert dijalog._tbl_posljednje.item(0, 1).text() == "PC1"


def test_refresh_ne_duplira_widgete(qtbot, servis):
    dijalog = PrikazPazara(None, smjena_id_getter=lambda: 1)
    qtbot.addWidget(dijalog)
    broj_widgeta = len(dijalog.findChildren(QWidget))

    dijalog.osvjezi_podatke()
    dijalog.osvjezi_podatke()

    assert len(dijalog.findChildren(QWidget)) == broj_widgeta
    assert dijalog._tbl_top.rowCount() == 1
    assert servis.call_count == 3


def test_prazno_stanje_ne_poziva_servis_i_ne_baca_exception(qtbot, servis):
    dijalog = PrikazPazara(None, smjena_id_getter=lambda: None)
    qtbot.addWidget(dijalog)

    assert dijalog._lbl_smjena.text() == "Nema otvorene smjene"
    assert dijalog._lbl_ukupno.text() == "0.00 KM"
    assert dijalog._lbl_aktivni.text() == "0"
    assert dijalog._tbl_top.rowCount() == 0
    assert dijalog._tbl_isticu.rowCount() == 0
    assert dijalog._tbl_posljednje.rowCount() == 0
    servis.assert_not_called()
