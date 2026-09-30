from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from models.artikal import Artikal
from models.session_state import SessionState
from ui.bocni_panel import BocniPanel


@pytest.fixture
def panel(qtbot):
    smjena = {"id": 1}
    widget = BocniPanel(
        smjena_id_getter=lambda: smjena["id"],
        radnik_getter=lambda: "Tester",
    )
    qtbot.addWidget(widget)
    return widget, smjena


@pytest.fixture
def prati_osvjezi(panel, monkeypatch: pytest.MonkeyPatch):
    widget, _smjena = panel
    spy = Mock(wraps=widget.osvjezi)
    monkeypatch.setattr(widget, "osvjezi", spy)
    return spy


def _kartica(
    ime: str,
    *,
    aktivna: bool = True,
    kosarica: list[Artikal] | None = None,
    session=None,
):
    if not aktivna:
        session = None
    elif session is None:
        session = object()
    return SimpleNamespace(
        ime=ime,
        session=session,
        kosarica=list(kosarica or []),
    )


def test_prvi_poziv_sa_stanjem_radi_puni_osvjezi(panel, prati_osvjezi):
    widget, _smjena = panel
    kartice = [_kartica("PC 1")]

    widget.osvjezi_ako_promijenjeno(kartice)

    prati_osvjezi.assert_called_once_with(kartice)


def test_isto_stanje_ne_radi_novi_puni_refresh(panel, prati_osvjezi):
    widget, _smjena = panel
    kartice = [_kartica("PC 1")]

    widget.osvjezi_ako_promijenjeno(kartice)
    widget.osvjezi_ako_promijenjeno(kartice)

    assert prati_osvjezi.call_count == 1


def test_promjena_aktivnih_uredjaja_izaziva_refresh(panel, prati_osvjezi):
    widget, _smjena = panel
    pc1 = _kartica("PC 1")
    pc2 = _kartica("PC 2", aktivna=False)
    kartice = [pc1, pc2]
    widget.osvjezi_ako_promijenjeno(kartice)

    pc2.session = object()
    widget.osvjezi_ako_promijenjeno(kartice)

    assert prati_osvjezi.call_count == 2


def test_promjena_odabranog_uredjaja_izaziva_refresh(panel, prati_osvjezi):
    widget, _smjena = panel
    kartice = [_kartica("PC 1"), _kartica("PC 2")]
    widget.osvjezi_ako_promijenjeno(kartice)
    assert widget._combo_uredjaj.currentText() == "PC 1"

    widget._combo_uredjaj.setCurrentText("PC 2")
    widget.osvjezi_ako_promijenjeno(kartice)

    assert prati_osvjezi.call_count == 2


@pytest.mark.parametrize("promjena", ["sadrzaj", "kolicina"])
def test_promjena_sank_kosarice_izaziva_refresh(
    panel,
    prati_osvjezi,
    promjena,
):
    widget, _smjena = panel
    kartice = [_kartica("PC 1")]
    if promjena == "kolicina":
        widget.sank_kosarica = [Artikal("Kafa", 1.50)]
    widget.osvjezi_ako_promijenjeno(kartice)

    if promjena == "sadrzaj":
        widget.sank_kosarica.append(Artikal("Sok", 2.00))
    else:
        widget.sank_kosarica[0].kolicina += 1
    widget.osvjezi_ako_promijenjeno(kartice)

    assert prati_osvjezi.call_count == 2


@pytest.mark.parametrize("promjena", ["sadrzaj", "kolicina"])
def test_promjena_kosarice_odabranog_uredjaja_izaziva_refresh(
    panel,
    prati_osvjezi,
    promjena,
):
    widget, _smjena = panel
    pocetna_kosarica = [Artikal("Kafa", 1.50)] if promjena == "kolicina" else []
    pc1 = _kartica("PC 1", kosarica=pocetna_kosarica)
    kartice = [pc1]
    widget.osvjezi_ako_promijenjeno(kartice)

    if promjena == "sadrzaj":
        pc1.kosarica.append(Artikal("Sok", 2.00))
    else:
        pc1.kosarica[0].kolicina += 1
    widget.osvjezi_ako_promijenjeno(kartice)

    assert prati_osvjezi.call_count == 2


def test_promjena_postojanja_smjene_izaziva_refresh(panel, prati_osvjezi):
    widget, smjena = panel
    kartice = [_kartica("PC 1")]
    widget.osvjezi_ako_promijenjeno(kartice)

    smjena["id"] = None
    widget.osvjezi_ako_promijenjeno(kartice)

    assert prati_osvjezi.call_count == 2


def test_promjene_timera_i_progressa_ne_izazivaju_puni_rebuild(
    panel,
    prati_osvjezi,
):
    widget, _smjena = panel
    sesija = SessionState(
        vreme_starta=datetime.now(),
        limit_sekundi=3600,
        is_prepaid=True,
        tip="prepaid",
    )
    kartice = [_kartica("PC 1", session=sesija)]
    widget.osvjezi_ako_promijenjeno(kartice)

    sesija.vreme_starta -= timedelta(minutes=15)
    sesija.limit_sekundi = 1800
    widget.osvjezi_ako_promijenjeno(kartice)

    assert prati_osvjezi.call_count == 1
