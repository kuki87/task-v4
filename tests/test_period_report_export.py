from pathlib import Path

import pytest

import database.db as db_module
import services.izvjestaj as izvjestaj_service
from services.izvjestaj_perioda import dohvati_izvjestaj_perioda


@pytest.fixture
def izvjestaj_podaci(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    db_path = tmp_path / "period-export.sqlite3"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    monkeypatch.setattr(izvjestaj_service, "IZVJESTAJI_DIR", str(tmp_path / "izvjestaji"))
    db_module.inicijalizuj_bazu()
    conn = db_module.get_db()
    smjena_id = conn.execute(
        """INSERT INTO smjene (pocetak, kraj, radnik, pazar)
           VALUES (?, ?, ?, ?)""",
        ("2026-09-01T08:00:00", "2026-09-01T16:00:00", "Tester", 12.5),
    ).lastrowid
    conn.execute(
        """INSERT INTO pazar_arhiva
           (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            "2026-09-01T12:00:00",
            "PC1",
            12.5,
            smjena_id,
            "2026-09-01T10:00:00",
            "racunar",
        ),
    )
    conn.commit()
    podaci = dohvati_izvjestaj_perioda("2026-09-01", "2026-09-01")
    yield smjena_id, podaci, tmp_path
    db_module.zatvori_bazu()


def test_txt_perioda_nastane_sa_periodom_i_kljucnim_zbirom(izvjestaj_podaci):
    _smjena_id, podaci, _tmp_path = izvjestaj_podaci

    putanja = Path(izvjestaj_service.generisi_txt_perioda(
        "2026-09-01", "2026-09-01", podaci
    ))

    assert putanja.exists()
    assert putanja.name == "izvjestaj_2026-09-01_2026-09-01.txt"
    sadrzaj = putanja.read_text(encoding="utf-8")
    assert "Period: 2026-09-01 — 2026-09-01" in sadrzaj
    assert "Ukupno             : 12.50 KM" in sadrzaj
    assert "Računari           : 12.50 KM" in sadrzaj


def test_pdf_perioda_nastane_sa_ispravnim_nazivom(izvjestaj_podaci):
    _smjena_id, podaci, _tmp_path = izvjestaj_podaci

    putanja_txt = izvjestaj_service.generisi_pdf_perioda(
        "2026-09-01", "2026-09-01", podaci
    )

    assert putanja_txt
    putanja = Path(putanja_txt)
    assert putanja.exists()
    assert putanja.name == "izvjestaj_2026-09-01_2026-09-01.pdf"
    assert putanja.stat().st_size > 1000


def test_postojeci_tekstualni_izvjestaj_smjene_i_dalje_radi(izvjestaj_podaci):
    smjena_id, _podaci, _tmp_path = izvjestaj_podaci

    sadrzaj = izvjestaj_service.generiši_tekstualni(smjena_id, {})

    assert "IZVJEŠTAJ SMJENE" in sadrzaj
    assert f"Smjena ID : {smjena_id}" in sadrzaj
    assert "UKUPNO    : 12.50 KM" in sadrzaj
