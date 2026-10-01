from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QMessageBox

import database.db as db_module
import services.pazar as pazar_service
import services.smjena as smjena_service
import services.uredjaji as uredjaji_service
import ui.glavni_prozor as glavni_prozor_module
from models.app_state import AppState
from models.artikal import Artikal
from models.session_state import SessionState
from tests.helpers import napravi_test_korisnika
from ui.glavni_prozor import _MainWindow


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    AppState().zatvori_smjenu()
    db_path = tmp_path / "recovery-test.sqlite3"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))

    db_module.inicijalizuj_bazu()
    conn = db_module.get_db()
    stvarna_putanja = Path(
        conn.execute("PRAGMA database_list").fetchone()["file"]
    ).resolve()
    assert stvarna_putanja == db_path.resolve()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    yield conn

    AppState().zatvori_smjenu()
    db_module.zatvori_bazu()


def _snimak_recovery_tabela(conn):
    return {
        tabela: [dict(red) for red in conn.execute(
            f"SELECT * FROM {tabela} ORDER BY id"
        ).fetchall()]
        for tabela in ("sesije_log", "prodaja_artikala", "pazar_arhiva")
    }


@pytest.fixture
def actor(db):
    korisnik = napravi_test_korisnika(db)
    AppState().prijavi_korisnika(korisnik)
    yield korisnik
    AppState().odjavi_korisnika()


def _restartuj_aplikaciju(qtbot, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    AppState().zatvori_smjenu()
    monkeypatch.setattr(
        glavni_prozor_module.QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    prozor = _MainWindow()
    qtbot.addWidget(prozor)
    prozor._timer.stop()
    return prozor, db_module.get_db()


def _kartica(prozor, ime):
    return next(kartica for kartica in prozor.kartice if kartica.ime == ime)


def test_isti_naziv_sa_razlicitim_cijenama_ne_pravi_prosjecnu_cijenu(db, actor):
    smjena_id = smjena_service.otvori_smjenu(actor)
    pazar_service.dodaj_artikal_na_uredjaj(
        smjena_id, "PC1", "Kafa", 1, 1.50, actor=actor
    )
    pazar_service.dodaj_artikal_na_uredjaj(
        smjena_id, "PC1", "Kafa", 2, 1.50, actor=actor
    )
    pazar_service.dodaj_artikal_na_uredjaj(
        smjena_id, "PC1", "Kafa", 1, 2.00, actor=actor
    )

    artikli = pazar_service.dohvati_nenaplacene_artikle(smjena_id, "PC1")

    assert artikli == [
        Artikal("Kafa", 1.50, 3),
        Artikal("Kafa", 2.00, 1),
    ]


def test_restart_obnavlja_regularnu_sesiju_i_agregiranu_kosaricu_bez_upisa(
    db,
    actor,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
):
    uredjaji_service.dodaj_uredjaj(
        "PC1", 2.0, "PC", "Classic", actor=actor
    )
    smjena_id = smjena_service.otvori_smjenu(actor)
    pocetak = datetime.now() - timedelta(minutes=30)
    sesija = SessionState(vreme_starta=pocetak, tip="neograniceno")
    pazar_service.start_sesija("PC1", sesija, smjena_id, actor=actor)

    for _ in range(3):
        pazar_service.dodaj_artikal_na_uredjaj(
            smjena_id, "PC1", "Kafa", 1, 1.50, actor=actor
        )
    db.execute(
        """INSERT INTO prodaja_artikala
           (vreme, smjena_id, uredjaj, naziv_artikla, kolicina,
            ukupna_cijena, naplaceno)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (datetime.now().isoformat(), smjena_id, "PC1", "Sok", 2, 4.00),
    )
    db.commit()

    prije_recoveryja = _snimak_recovery_tabela(db)
    prozor, conn = _restartuj_aplikaciju(qtbot, monkeypatch)
    kartica = _kartica(prozor, "PC1")

    assert kartica.session is not None
    assert kartica.session.vreme_starta == pocetak
    assert kartica.session.tip == "neograniceno"
    assert kartica.kosarica == [Artikal("Kafa", 1.50, 3)]
    assert _snimak_recovery_tabela(conn) == prije_recoveryja

    kartica.naplati()

    assert kartica.session is None
    assert kartica.kosarica == []
    lifecycle = conn.execute(
        """SELECT vreme_kraja, iznos FROM sesije_log
           WHERE smjena_id = ? AND uredjaj = ?""",
        (smjena_id, "PC1"),
    ).fetchone()
    assert lifecycle["vreme_kraja"] is not None
    assert lifecycle["iznos"] is not None

    artikli = conn.execute(
        """SELECT naziv_artikla, naplaceno FROM prodaja_artikala
           WHERE smjena_id = ? ORDER BY id""",
        (smjena_id,),
    ).fetchall()
    assert [(red["naziv_artikla"], red["naplaceno"]) for red in artikli] == [
        ("Kafa", 1),
        ("Kafa", 1),
        ("Kafa", 1),
        ("Sok", 1),
    ]
    artikal_pazar = conn.execute(
        """SELECT COUNT(*) AS broj, SUM(iznos) AS ukupno
           FROM pazar_arhiva
           WHERE smjena_id = ? AND uredjaj = ? AND tip_prodaje = 'artikal'""",
        (smjena_id, "PC1"),
    ).fetchone()
    assert artikal_pazar["broj"] == 1
    assert artikal_pazar["ukupno"] == pytest.approx(4.50)


@pytest.mark.parametrize(
    ("tip", "limit_sekundi", "iznos", "is_prepaid", "is_pass2"),
    [
        pytest.param("prepaid", 7200, 4.0, True, False, id="prepaid"),
        pytest.param("pass1", 18000, 6.0, False, False, id="pass1"),
        pytest.param("pass2", None, 6.0, False, True, id="pass2"),
    ],
)
def test_restart_cuva_tip_i_limit_prepaid_i_pass_sesije(
    db,
    actor,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    tip,
    limit_sekundi,
    iznos,
    is_prepaid,
    is_pass2,
):
    uredjaji_service.dodaj_uredjaj(
        "PC1", 2.0, "PC", "Classic", actor=actor
    )
    smjena_id = smjena_service.otvori_smjenu(actor)
    sesija = SessionState(
        vreme_starta=datetime.now() - timedelta(minutes=5),
        limit_sekundi=limit_sekundi,
        is_prepaid=is_prepaid,
        is_pass2=is_pass2,
        tip=tip,
    )
    pazar_service.start_sesija(
        "PC1", sesija, smjena_id, iznos, actor=actor
    )
    prije_recoveryja = _snimak_recovery_tabela(db)

    prozor, conn = _restartuj_aplikaciju(qtbot, monkeypatch)
    obnovljena = _kartica(prozor, "PC1").session

    assert obnovljena is not None
    assert obnovljena.tip == tip
    assert obnovljena.limit_sekundi == limit_sekundi
    assert obnovljena.is_prepaid is is_prepaid
    assert obnovljena.is_pass2 is is_pass2
    assert _snimak_recovery_tabela(conn) == prije_recoveryja


def test_orphan_aktivna_sesija_se_loguje_i_prijavljuje_bez_promjene_baze(
    db,
    actor,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
):
    uredjaji_service.dodaj_uredjaj(
        "OBRISANI-PC", 2.0, "PC", "Classic", actor=actor
    )
    uredjaj_id = db.execute(
        "SELECT id FROM uredjaji WHERE ime = ?", ("OBRISANI-PC",)
    ).fetchone()["id"]
    smjena_id = smjena_service.otvori_smjenu(actor)
    sesija = SessionState(vreme_starta=datetime.now(), tip="neograniceno")
    pazar_service.start_sesija(
        "OBRISANI-PC", sesija, smjena_id, actor=actor
    )
    uredjaji_service.brisi_uredjaj(uredjaj_id, actor=actor)
    prije_recoveryja = _snimak_recovery_tabela(db)

    upozorenja = []
    log_error = Mock()

    def warning(_parent, naslov, tekst, *args, **kwargs):
        upozorenja.append((naslov, tekst))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(glavni_prozor_module.QMessageBox, "warning", warning)
    monkeypatch.setattr(glavni_prozor_module.log, "error", log_error)

    _prozor, conn = _restartuj_aplikaciju(qtbot, monkeypatch)

    assert len(upozorenja) == 1
    assert upozorenja[0][0] == "Neobnovljene sesije"
    assert "OBRISANI-PC" in upozorenja[0][1]
    log_error.assert_called_once()
    assert "OBRISANI-PC" in log_error.call_args.args[0]
    assert _snimak_recovery_tabela(conn) == prije_recoveryja
    assert conn.execute(
        """SELECT COUNT(*) FROM sesije_log
           WHERE smjena_id = ? AND uredjaj = ? AND vreme_kraja IS NULL""",
        (smjena_id, "OBRISANI-PC"),
    ).fetchone()[0] == 1
