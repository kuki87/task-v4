from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QMessageBox

import database.db as db_module
import services.izvjestaj as izvjestaj_module
import services.smjena as smjena_service
import ui.glavni_prozor as glavni_prozor_module
from models.app_state import AppState
from tests.helpers import napravi_test_korisnika
from ui.glavni_prozor import _MainWindow


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    db_path = tmp_path / "izvjestaj-ui-test.sqlite3"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))

    db_module.inicijalizuj_bazu()
    conn = db_module.get_db()
    stvarna_putanja = Path(
        conn.execute("PRAGMA database_list").fetchone()["file"]
    ).resolve()
    assert stvarna_putanja == db_path.resolve()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    yield conn

    db_module.zatvori_bazu()


@pytest.fixture
def prozor(qtbot, db):
    AppState().zatvori_smjenu()
    actor = napravi_test_korisnika(
        db, username="test-radnik", ime="Test radnik"
    )
    AppState().prijavi_korisnika(actor)
    widget = _MainWindow()
    qtbot.addWidget(widget)
    widget._timer.stop()

    smjena_id = smjena_service.otvori_smjenu(actor)
    widget.state.postavi_smjenu(smjena_id, "Test radnik")
    widget._session_cache["privremeno"] = (object(), [])
    widget._osvjezi_status_bar()

    yield widget, smjena_id

    widget._timer.stop()
    AppState().zatvori_smjenu()
    AppState().odjavi_korisnika()


@pytest.fixture
def snimljene_poruke(monkeypatch: pytest.MonkeyPatch):
    poruke = []

    def warning(_parent, naslov, tekst, *args, **kwargs):
        poruke.append((naslov, tekst))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(glavni_prozor_module.QMessageBox, "warning", warning)
    return poruke


def _provjeri_zatvorenu_smjenu(db, prozor, smjena_id, sql_naredbe):
    red = db.execute(
        "SELECT kraj, radnik, pazar FROM smjene WHERE id = ?",
        (smjena_id,),
    ).fetchone()

    assert red["kraj"] is not None
    assert red["radnik"] == "Test radnik"
    assert red["pazar"] == pytest.approx(0.0)
    assert smjena_service.dohvati_aktivnu_smjenu() is None
    assert db.in_transaction is False
    assert not any("ROLLBACK" in naredba.upper() for naredba in sql_naredbe)

    assert prozor.state.trenutna_smjena_id is None
    assert prozor.state.ime_radnika == ""
    assert prozor._session_cache == {}
    assert prozor._bocni.sank_kosarica == []
    assert all(k.session is None and k.kosarica == [] for k in prozor.kartice)
    assert prozor._lbl_radnik.text() == "Korisnik: Test radnik (admin)"
    assert prozor._lbl_smjena.text() == "NEMA OTVORENE SMJENE"
    assert prozor._lbl_aktivno.text() == f"0/{len(prozor.kartice)} aktivno"
    assert prozor._lbl_pazar.text() == "Pazar: 0.00 KM"


def _provjeri_upozorenje_i_log(snimljene_poruke, log_error, greska):
    assert len(snimljene_poruke) == 1
    naslov, poruka = snimljene_poruke[0]
    assert naslov == "Greška izvještaja"
    assert "Smjena je uspješno zatvorena" in poruka
    assert "izvještaj nije moguće generisati ili prikazati" in poruka
    assert str(greska) in poruka

    log_error.assert_called_once()
    log_poruka = log_error.call_args.args[0]
    assert "nije generisan ili prikazan" in log_poruka
    assert str(greska) in log_poruka


def test_greska_tekstualnog_izvjestaja_dolazi_nakon_commita_smjene(
    prozor,
    db,
    monkeypatch: pytest.MonkeyPatch,
    snimljene_poruke,
):
    widget, smjena_id = prozor
    greska = RuntimeError("tekstualni izvještaj nije dostupan")
    sql_naredbe = []
    sql_prije_izvjestaja = []
    db.set_trace_callback(sql_naredbe.append)

    def tekstualni_sa_greskom(dobijeni_smjena_id, podaci):
        assert dobijeni_smjena_id == smjena_id
        assert podaci == {}
        zatvorena = db.execute(
            "SELECT kraj FROM smjene WHERE id = ?",
            (smjena_id,),
        ).fetchone()
        assert zatvorena["kraj"] is not None
        assert smjena_service.dohvati_aktivnu_smjenu() is None
        assert db.in_transaction is False
        sql_prije_izvjestaja.extend(sql_naredbe)
        raise greska

    pdf = Mock()
    prikaz = Mock()
    log_error = Mock()
    monkeypatch.setattr(
        izvjestaj_module,
        "generiši_tekstualni",
        tekstualni_sa_greskom,
    )
    monkeypatch.setattr(izvjestaj_module, "generiši_pdf", pdf)
    monkeypatch.setattr(glavni_prozor_module, "_PrikazIzvjestaja", prikaz)
    monkeypatch.setattr(glavni_prozor_module.log, "error", log_error)

    widget._zatvori_smjenu()
    db.set_trace_callback(None)

    assert any(naredba.upper() == "COMMIT" for naredba in sql_prije_izvjestaja)
    pdf.assert_not_called()
    prikaz.assert_not_called()
    _provjeri_upozorenje_i_log(snimljene_poruke, log_error, greska)
    _provjeri_zatvorenu_smjenu(db, widget, smjena_id, sql_naredbe)


def test_greska_pdf_izvjestaja_ne_vraca_zatvorenu_smjenu(
    prozor,
    db,
    monkeypatch: pytest.MonkeyPatch,
    snimljene_poruke,
):
    widget, smjena_id = prozor
    greska = RuntimeError("PDF izvještaj nije dostupan")
    sql_naredbe = []
    db.set_trace_callback(sql_naredbe.append)

    tekstualni = Mock(return_value="Tekst izvještaja")
    pdf = Mock(side_effect=greska)
    prikaz = Mock()
    log_error = Mock()
    monkeypatch.setattr(izvjestaj_module, "generiši_tekstualni", tekstualni)
    monkeypatch.setattr(izvjestaj_module, "generiši_pdf", pdf)
    monkeypatch.setattr(glavni_prozor_module, "_PrikazIzvjestaja", prikaz)
    monkeypatch.setattr(glavni_prozor_module.log, "error", log_error)

    widget._zatvori_smjenu()
    db.set_trace_callback(None)

    tekstualni.assert_called_once_with(smjena_id, {})
    pdf.assert_called_once_with(smjena_id, {})
    prikaz.assert_not_called()
    _provjeri_upozorenje_i_log(snimljene_poruke, log_error, greska)
    _provjeri_zatvorenu_smjenu(db, widget, smjena_id, sql_naredbe)


def test_greska_prikaza_izvjestaja_ne_vraca_zatvorenu_smjenu(
    prozor,
    db,
    monkeypatch: pytest.MonkeyPatch,
    snimljene_poruke,
):
    widget, smjena_id = prozor
    greska = RuntimeError("prikaz izvještaja nije dostupan")
    sql_naredbe = []
    db.set_trace_callback(sql_naredbe.append)

    tekstualni = Mock(return_value="Tekst izvještaja")
    pdf = Mock(return_value="izvjestaj.pdf")
    dijalog = Mock()
    dijalog.exec.side_effect = greska
    prikaz = Mock(return_value=dijalog)
    log_error = Mock()
    monkeypatch.setattr(izvjestaj_module, "generiši_tekstualni", tekstualni)
    monkeypatch.setattr(izvjestaj_module, "generiši_pdf", pdf)
    monkeypatch.setattr(glavni_prozor_module, "_PrikazIzvjestaja", prikaz)
    monkeypatch.setattr(glavni_prozor_module.log, "error", log_error)

    widget._zatvori_smjenu()
    db.set_trace_callback(None)

    tekstualni.assert_called_once_with(smjena_id, {})
    pdf.assert_called_once_with(smjena_id, {})
    prikaz.assert_called_once_with(widget, "Tekst izvještaja", "izvjestaj.pdf")
    dijalog.exec.assert_called_once_with()
    _provjeri_upozorenje_i_log(snimljene_poruke, log_error, greska)
    _provjeri_zatvorenu_smjenu(db, widget, smjena_id, sql_naredbe)
