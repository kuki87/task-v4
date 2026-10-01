from unittest.mock import Mock

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QMessageBox, QWidget

import ui.izvjestaji as izvjestaji_ui
from ui.izvjestaji import IzvjestajiDijalog


def _podaci(datum_od="2026-09-01", datum_do="2026-09-01", *, prazno=False):
    prihod = 0.0 if prazno else 15.0
    return {
        "period": {
            "datum_od": datum_od,
            "datum_do": datum_do,
            "pocetak": f"{datum_od}T00:00:00",
            "kraj_iskljucivo": f"{datum_do}T00:00:00",
        },
        "sazetak": {
            "ukupno": prihod,
            "racunari": 8.0 if not prazno else 0.0,
            "artikli": 3.0 if not prazno else 0.0,
            "sank": 4.0 if not prazno else 0.0,
            "broj_zavrsenih_smjena": 1 if not prazno else 0,
            "broj_sesija": 2 if not prazno else 0,
            "prosjek_po_smjeni": prihod,
            "prosjek_po_zavrsenoj_sesiji": 7.5 if not prazno else 0.0,
        },
        "sesije": {
            "ukupno": 2 if not prazno else 0,
            "aktivne": 1 if not prazno else 0,
            "zavrsene": 1 if not prazno else 0,
            "tipovi": {
                "neograniceno": 1 if not prazno else 0,
                "prepaid": 1 if not prazno else 0,
                "pass1": 0,
                "pass2": 0,
                "minecraft": 0,
            },
            "ukupno_trajanje_zavrsenih": 3600 if not prazno else 0,
            "prosjek_trajanja_zavrsenih": 3600 if not prazno else 0,
            "top_uredjaji_po_sesijama": (
                [{"uredjaj": "PC1", "broj_sesija": 2}] if not prazno else []
            ),
            "top_uredjaji_po_prihodu": (
                [{"uredjaj": "PC1", "prihod": 11.0}] if not prazno else []
            ),
        },
        "artikli": {
            "ukupna_kolicina": 2 if not prazno else 0,
            "ukupan_prihod_po_evidenciji": 3.0 if not prazno else 0.0,
            "top_po_kolicini": (
                [{"naziv": "Kafa", "kolicina": 2, "prihod": 3.0}]
                if not prazno else []
            ),
            "top_po_prihodu": (
                [{"naziv": "Kafa", "kolicina": 2, "prihod": 3.0}]
                if not prazno else []
            ),
        },
        "smjene": (
            [{
                "id": 1,
                "radnik": "Tester",
                "pocetak": "2026-09-01T08:00:00",
                "kraj": "2026-09-01T16:00:00",
                "pazar": prihod,
                "status": "zavrsena",
                "trajanje_sekundi": 8 * 3600,
            }] if not prazno else []
        ),
        "trend": {
            "granularnost": "sat",
            "tacke": [{"oznaka": "10:00", "iznos": prihod}],
        },
        "ogranicenja": [],
    }


@pytest.fixture
def servis(monkeypatch: pytest.MonkeyPatch):
    def rezultat(od, do):
        return _podaci(od, do)

    mock = Mock(side_effect=rezultat)
    monkeypatch.setattr(izvjestaji_ui, "dohvati_izvjestaj_perioda", mock)
    return mock


def test_stranica_se_kreira(qtbot, servis):
    dijalog = IzvjestajiDijalog()
    qtbot.addWidget(dijalog)

    assert dijalog.windowTitle() == "Poslovni izvještaji"
    assert dijalog._tbl_smjene.columnCount() == 6
    servis.assert_called_once()


def test_preset_danas(qtbot, servis):
    dijalog = IzvjestajiDijalog()
    qtbot.addWidget(dijalog)
    danas = QDate.currentDate().toString("yyyy-MM-dd")

    qtbot.mouseClick(dijalog._btn_danas, Qt.MouseButton.LeftButton)

    assert servis.call_args.args == (danas, danas)


def test_preset_ova_sedmica_pocinje_ponedjeljkom(qtbot, servis):
    dijalog = IzvjestajiDijalog()
    qtbot.addWidget(dijalog)
    danas = QDate.currentDate()
    ponedjeljak = danas.addDays(1 - danas.dayOfWeek())

    qtbot.mouseClick(dijalog._btn_ova_sedmica, Qt.MouseButton.LeftButton)

    assert servis.call_args.args == (
        ponedjeljak.toString("yyyy-MM-dd"),
        danas.toString("yyyy-MM-dd"),
    )


def test_preset_ovaj_mjesec(qtbot, servis):
    dijalog = IzvjestajiDijalog()
    qtbot.addWidget(dijalog)
    danas = QDate.currentDate()
    prvi = QDate(danas.year(), danas.month(), 1)

    qtbot.mouseClick(dijalog._btn_ovaj_mjesec, Qt.MouseButton.LeftButton)

    assert servis.call_args.args == (
        prvi.toString("yyyy-MM-dd"),
        danas.toString("yyyy-MM-dd"),
    )


def test_custom_period(qtbot, servis):
    dijalog = IzvjestajiDijalog()
    qtbot.addWidget(dijalog)
    dijalog._datum_od.setDate(QDate(2026, 2, 3))
    dijalog._datum_do.setDate(QDate(2026, 2, 17))

    qtbot.mouseClick(dijalog._btn_prikazi, Qt.MouseButton.LeftButton)

    assert servis.call_args.args == ("2026-02-03", "2026-02-17")


def test_od_poslije_do_ne_salje_query(qtbot, servis, monkeypatch):
    upozorenje = Mock(return_value=QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(izvjestaji_ui.QMessageBox, "warning", upozorenje)
    dijalog = IzvjestajiDijalog()
    qtbot.addWidget(dijalog)
    pozivi_prije = servis.call_count
    dijalog._datum_od.setDate(QDate(2026, 3, 20))
    dijalog._datum_do.setDate(QDate(2026, 3, 1))

    qtbot.mouseClick(dijalog._btn_prikazi, Qt.MouseButton.LeftButton)

    assert servis.call_count == pozivi_prije
    assert "Datum OD" in upozorenje.call_args.args[2]


def test_prazan_period_se_prikazuje_bez_greske(qtbot, monkeypatch):
    monkeypatch.setattr(
        izvjestaji_ui,
        "dohvati_izvjestaj_perioda",
        lambda od, do: _podaci(od, do, prazno=True),
    )

    dijalog = IzvjestajiDijalog()
    qtbot.addWidget(dijalog)

    assert dijalog._lbl_ukupno.text() == "0.00 KM"
    assert dijalog._tbl_smjene.rowCount() == 0
    assert dijalog._tbl_artikli_kolicina.rowCount() == 0
    assert dijalog._lbl_trend.text() == "— nema transakcija —"


def test_refresh_ne_duplira_redove_ili_widgete(qtbot, servis):
    dijalog = IzvjestajiDijalog()
    qtbot.addWidget(dijalog)
    broj_widgeta = len(dijalog.findChildren(QWidget))

    qtbot.mouseClick(dijalog._btn_prikazi, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(dijalog._btn_prikazi, Qt.MouseButton.LeftButton)

    assert dijalog._tbl_smjene.rowCount() == 1
    assert dijalog._tbl_artikli_kolicina.rowCount() == 1
    assert len(dijalog.findChildren(QWidget)) == broj_widgeta


def test_prikaz_servisnih_podataka(qtbot, servis):
    dijalog = IzvjestajiDijalog()
    qtbot.addWidget(dijalog)

    assert dijalog._lbl_ukupno.text() == "15.00 KM"
    assert dijalog._lbl_racunari.text() == "8.00 KM"
    assert dijalog._lbl_artikli.text() == "3.00 KM"
    assert dijalog._lbl_sank.text() == "4.00 KM"
    assert dijalog._lbl_sesije.text() == "2"
    assert dijalog._tbl_uredjaji_sesije.item(0, 0).text() == "PC1"
    assert dijalog._tbl_smjene.item(0, 1).text() == "Tester"
