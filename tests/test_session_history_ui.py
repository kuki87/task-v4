from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

import ui.historija_sesija as historija_ui
from ui.historija_sesija import HistorijaSesijaDijalog


def _sesija(
    sesija_id: int,
    uredjaj: str,
    *,
    tip="neograniceno",
    status="zavrsena",
):
    pocetak = datetime(2026, 1, sesija_id, 10, 0)
    kraj = pocetak + timedelta(hours=1) if status == "zavrsena" else None
    return {
        "id": sesija_id,
        "smjena_id": 7,
        "uredjaj": uredjaj,
        "vreme_starta": pocetak.isoformat(),
        "vreme_kraja": kraj.isoformat() if kraj else None,
        "iznos": 2.0 if kraj else None,
        "tip": tip,
        "limit_sekundi": None,
        "radnik": "Tester",
        "iznos_racunara": 2.0,
        "iznos_artikala": 1.5,
        "status": status,
        "trajanje_sekundi": 3600,
        "ukupno": 3.5,
        "artikli_detalji_dostupni": False,
    }


@pytest.fixture
def servisi(monkeypatch: pytest.MonkeyPatch):
    sve = [
        _sesija(2, "PC2", tip="prepaid", status="aktivna"),
        _sesija(1, "PC1"),
    ]

    def historija(**filteri):
        stavke = sve
        if filteri.get("uredjaj"):
            stavke = [s for s in stavke if s["uredjaj"] == filteri["uredjaj"]]
        if filteri.get("tip"):
            stavke = [s for s in stavke if s["tip"] == filteri["tip"]]
        if filteri.get("status") not in (None, "sve"):
            stavke = [s for s in stavke if s["status"] == filteri["status"]]
        return {
            "stavke": list(stavke),
            "ukupno": len(stavke),
            "limit": filteri["limit"],
            "offset": filteri["offset"],
        }

    historija_mock = Mock(side_effect=historija)
    opcije_mock = Mock(return_value={
        "uredjaji": ["PC1", "PC2"],
        "tipovi": ["neograniceno", "prepaid"],
    })
    monkeypatch.setattr(historija_ui, "dohvati_historiju_sesija", historija_mock)
    monkeypatch.setattr(
        historija_ui,
        "dohvati_opcije_historije_sesija",
        opcije_mock,
    )
    return historija_mock, opcije_mock


def test_stranica_se_kreira(qtbot, servisi):
    dijalog = HistorijaSesijaDijalog()
    qtbot.addWidget(dijalog)

    historija_mock, opcije_mock = servisi
    assert dijalog.windowTitle() == "Historija sesija"
    assert dijalog._tbl.columnCount() == 10
    historija_mock.assert_called_once()
    opcije_mock.assert_called_once_with()


def test_tabela_i_detalji_prikazuju_servisne_podatke(qtbot, servisi):
    dijalog = HistorijaSesijaDijalog()
    qtbot.addWidget(dijalog)

    assert dijalog._tbl.rowCount() == 2
    assert dijalog._tbl.item(0, 0).text() == "2"
    assert dijalog._tbl.item(0, 2).text() == "PC2"
    assert dijalog._tbl.item(0, 4).text() == "Aktivna"
    assert "Sesija #2" in dijalog._lbl_detalji.text()
    assert "Nazivi i količine artikala nisu dostupni" in dijalog._lbl_detalji.text()


def test_filter_uredjaja_mijenja_prikaz(qtbot, servisi):
    dijalog = HistorijaSesijaDijalog()
    qtbot.addWidget(dijalog)

    dijalog._combo_uredjaj.setCurrentIndex(
        dijalog._combo_uredjaj.findData("PC1")
    )

    assert dijalog._tbl.rowCount() == 1
    assert dijalog._tbl.item(0, 2).text() == "PC1"
    assert servisi[0].call_args.kwargs["uredjaj"] == "PC1"


def test_prazno_stanje_ne_pada(qtbot, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        historija_ui,
        "dohvati_opcije_historije_sesija",
        lambda: {"uredjaji": [], "tipovi": []},
    )
    monkeypatch.setattr(
        historija_ui,
        "dohvati_historiju_sesija",
        lambda **_kwargs: {
            "stavke": [],
            "ukupno": 0,
            "limit": 100,
            "offset": 0,
        },
    )

    dijalog = HistorijaSesijaDijalog()
    qtbot.addWidget(dijalog)

    assert dijalog._tbl.rowCount() == 0
    assert dijalog._lbl_rezultati.text() == "0 sesija · prikaz 0–0"
    assert dijalog._lbl_detalji.text() == "Nema sesija za odabrane filtere."


def test_refresh_ne_duplira_redove_ni_widgete(qtbot, servisi):
    dijalog = HistorijaSesijaDijalog()
    qtbot.addWidget(dijalog)
    broj_widgeta = len(dijalog.findChildren(QWidget))

    qtbot.mouseClick(dijalog._btn_osvjezi, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(dijalog._btn_osvjezi, Qt.MouseButton.LeftButton)

    assert dijalog._tbl.rowCount() == 2
    assert len(dijalog.findChildren(QWidget)) == broj_widgeta
    assert servisi[0].call_count == 3
