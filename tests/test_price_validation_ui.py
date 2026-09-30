import math

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

import ui.admin_panel as admin_module
from ui.admin_panel import AdminPanel
from ui.dijalog_start import IzborStartaDijalog


@pytest.fixture
def poruke(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[tuple[str, str]]]:
    zabiljezene = {"warning": [], "information": []}

    def warning(_parent, naslov, tekst, *args, **kwargs):
        zabiljezene["warning"].append((naslov, tekst))
        return QMessageBox.StandardButton.Ok

    def information(_parent, naslov, tekst, *args, **kwargs):
        zabiljezene["information"].append((naslov, tekst))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(QMessageBox, "information", information)
    return zabiljezene


@pytest.fixture
def admin_panel(qtbot, monkeypatch: pytest.MonkeyPatch) -> AdminPanel:
    monkeypatch.setattr(
        admin_module, "stanje_admin_lozinke", lambda: admin_module.AUTH_SPREMAN
    )
    monkeypatch.setattr(admin_module, "provjeri_admin_lozinku", lambda _lozinka: True)
    monkeypatch.setattr(
        admin_module.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("test-lozinka", True),
    )
    monkeypatch.setattr(admin_module, "ucitaj_artikle", lambda: [])
    monkeypatch.setattr(admin_module, "ucitaj_uredjaje", lambda: [])
    monkeypatch.setattr(admin_module, "ucitaj_logove", lambda _filter=None: [])

    panel = AdminPanel(None)
    qtbot.addWidget(panel)
    assert panel.auth_ok is True
    return panel


@pytest.mark.parametrize(
    "cijena",
    [
        pytest.param(0.0, id="nula"),
        pytest.param(-1.0, id="negativna"),
        pytest.param(math.nan, id="nan"),
        pytest.param(math.inf, id="inf"),
    ],
)
def test_izbor_starta_odbija_nevalidnu_cijenu_uredjaja(
    qtbot,
    poruke,
    cijena,
):
    dijalog = IzborStartaDijalog(None, "PC", cijena)
    qtbot.addWidget(dijalog)

    dijalog._potvrdi()

    assert dijalog.rezultat is None
    assert dijalog.result() == QDialog.DialogCode.Rejected
    assert len(poruke["warning"]) == 1


@pytest.mark.parametrize(
    "unos",
    [
        pytest.param("0", id="nula"),
        pytest.param("-1", id="negativan"),
        pytest.param("NaN", id="nan"),
        pytest.param("inf", id="inf"),
        pytest.param("nije-broj", id="tekst"),
    ],
)
def test_prepaid_odbija_nevalidan_iznos(qtbot, poruke, unos):
    dijalog = IzborStartaDijalog(None, "PC", 2.0)
    qtbot.addWidget(dijalog)
    dijalog._tabs.setCurrentIndex(1)
    dijalog._entry_prepaid.setText(unos)

    dijalog._potvrdi()

    assert dijalog.rezultat is None
    assert dijalog.result() == QDialog.DialogCode.Rejected
    assert len(poruke["warning"]) == 1


@pytest.mark.parametrize(
    "unos",
    [
        pytest.param("", id="prazan"),
        pytest.param("nije-broj", id="tekst"),
        pytest.param("0", id="nula"),
        pytest.param("-1", id="negativan"),
        pytest.param("NaN", id="nan"),
        pytest.param("inf", id="inf"),
    ],
)
def test_admin_novi_uredjaj_odbija_nevalidnu_cijenu(
    admin_panel,
    monkeypatch: pytest.MonkeyPatch,
    poruke,
    unos,
):
    pozivi = []
    monkeypatch.setattr(
        admin_module,
        "dodaj_uredjaj",
        lambda *args: pozivi.append(args),
    )
    admin_panel._entry_urd_ime.setText("PC Test")
    admin_panel._entry_urd_cena.setText(unos)

    admin_panel._dodaj_uredjaj()

    assert pozivi == []
    assert len(poruke["warning"]) == 1


@pytest.mark.parametrize(
    "unos",
    [
        pytest.param("", id="prazan"),
        pytest.param("nije-broj", id="tekst"),
        pytest.param("0", id="nula"),
        pytest.param("-1", id="negativan"),
        pytest.param("NaN", id="nan"),
        pytest.param("inf", id="inf"),
    ],
)
def test_admin_promjena_cijene_grupe_odbija_nevalidnu_vrijednost(
    admin_panel,
    monkeypatch: pytest.MonkeyPatch,
    poruke,
    unos,
):
    pozivi = []
    monkeypatch.setattr(
        admin_module,
        "postavi_cijenu_grupe",
        lambda *args: pozivi.append(args),
    )
    admin_panel._entry_cijene["Classic"].setText(unos)

    admin_panel._postavi_cijenu_grupe("Classic")

    assert pozivi == []
    assert len(poruke["warning"]) == 1


def test_validna_pozitivna_cijena_uredjaja_pokrece_sesiju_bez_upozorenja(
    qtbot,
    poruke,
):
    dijalog = IzborStartaDijalog(None, "PC", 2.50)
    qtbot.addWidget(dijalog)

    dijalog._potvrdi()

    assert dijalog.result() == QDialog.DialogCode.Accepted
    assert dijalog.rezultat == {
        "tip": "neograniceno",
        "iznos": 0.0,
        "limit_sekundi": None,
    }
    assert poruke["warning"] == []


def test_validan_prepaid_iznos_prolazi_bez_upozorenja(qtbot, poruke):
    dijalog = IzborStartaDijalog(None, "PC", 2.0)
    qtbot.addWidget(dijalog)
    dijalog._tabs.setCurrentIndex(1)
    dijalog._entry_prepaid.setText("5,00")

    dijalog._potvrdi()

    assert dijalog.result() == QDialog.DialogCode.Accepted
    assert dijalog.rezultat == {
        "tip": "prepaid",
        "iznos": 5.0,
        "limit_sekundi": 9000,
    }
    assert poruke["warning"] == []


def test_admin_validna_cijena_novog_uredjaja_prolazi_bez_upozorenja(
    admin_panel,
    monkeypatch: pytest.MonkeyPatch,
    poruke,
):
    pozivi = []
    monkeypatch.setattr(
        admin_module,
        "dodaj_uredjaj",
        lambda *args: pozivi.append(args),
    )
    admin_panel._entry_urd_ime.setText("PC Test")
    admin_panel._entry_urd_cena.setText("2,50")

    admin_panel._dodaj_uredjaj()

    assert pozivi == [("PC Test", 2.5, "PC", "Classic")]
    assert poruke["warning"] == []


def test_admin_validna_cijena_grupe_prolazi_bez_upozorenja(
    admin_panel,
    monkeypatch: pytest.MonkeyPatch,
    poruke,
):
    pozivi = []

    def postavi(grupa, cijena):
        pozivi.append((grupa, cijena))
        return 3

    monkeypatch.setattr(admin_module, "postavi_cijenu_grupe", postavi)
    admin_panel._entry_cijene["Classic"].setText("3,25")

    admin_panel._postavi_cijenu_grupe("Classic")

    assert pozivi == [("Classic", 3.25)]
    assert poruke["warning"] == []
    assert len(poruke["information"]) == 1
