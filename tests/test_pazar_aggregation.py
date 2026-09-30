from datetime import datetime, timedelta
from pathlib import Path

import pytest

import database.db as db_module
import services.pazar as pazar_service


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Svaki test koristi zasebnu migriranu SQLite bazu u privremenom folderu."""
    db_module.zatvori_bazu()
    db_path = tmp_path / "pazar-aggregation-test.sqlite3"
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


def _nova_smjena(db) -> int:
    vrijeme = datetime(2026, 1, 1, 12, 0, 0).isoformat()
    cursor = db.execute(
        """INSERT INTO smjene (pocetak, kraj, radnik, pazar)
           VALUES (?, NULL, ?, ?)""",
        (vrijeme, "Tester", 0.0),
    )
    db.commit()
    return cursor.lastrowid


def _upisi_transakcije(db, smjena_id: int, transakcije: list[tuple[str, float]]):
    pocetak = datetime(2026, 1, 1, 12, 0, 0)
    redovi = []
    for indeks, (tip_prodaje, iznos) in enumerate(transakcije):
        vrijeme = (pocetak + timedelta(seconds=indeks)).isoformat()
        redovi.append(
            (
                vrijeme,
                f"Uredjaj {indeks + 1}",
                iznos,
                smjena_id,
                vrijeme,
                tip_prodaje,
            )
        )

    db.executemany(
        """INSERT INTO pazar_arhiva
           (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
           VALUES (?, ?, ?, ?, ?, ?)""",
        redovi,
    )
    db.commit()


def _assert_agregati(
    rezultat: dict,
    *,
    ukupno: float,
    racunari: float,
    artikli: float,
    sank: float,
    broj_transakcija: int,
):
    assert rezultat["ukupno"] == pytest.approx(ukupno)
    assert rezultat["racunari"] == pytest.approx(racunari)
    assert rezultat["artikli"] == pytest.approx(artikli)
    assert rezultat["sank"] == pytest.approx(sank)
    assert len(rezultat["transakcije"]) == broj_transakcija


def test_prazna_smjena_vraca_nule_i_ispravnu_strukturu(db):
    smjena_id = _nova_smjena(db)

    rezultat = pazar_service.dohvati_pazar_smjene(smjena_id)

    assert set(rezultat) == {
        "ukupno",
        "racunari",
        "artikli",
        "sank",
        "transakcije",
    }
    assert rezultat == {
        "ukupno": 0,
        "racunari": 0,
        "artikli": 0,
        "sank": 0,
        "transakcije": [],
    }


@pytest.mark.parametrize(
    "tip_prodaje, iznos",
    [
        pytest.param("racunar", 4.25, id="samo-racunar"),
        pytest.param("minecraft", 3.50, id="samo-minecraft"),
        pytest.param("prepaid", 5.00, id="samo-prepaid"),
        pytest.param("pass1", 7.00, id="samo-pass1"),
        pytest.param("pass2", 8.00, id="samo-pass2"),
    ],
)
def test_racunarski_tipovi_ulaze_samo_u_racunare(db, tip_prodaje, iznos):
    smjena_id = _nova_smjena(db)
    _upisi_transakcije(db, smjena_id, [(tip_prodaje, iznos)])

    rezultat = pazar_service.dohvati_pazar_smjene(smjena_id)

    _assert_agregati(
        rezultat,
        ukupno=iznos,
        racunari=iznos,
        artikli=0.0,
        sank=0.0,
        broj_transakcija=1,
    )
    assert rezultat["transakcije"][0]["tip_prodaje"] == tip_prodaje


@pytest.mark.parametrize(
    "dodatni_tip, dodatni_iznos, ocekivani_artikli, ocekivani_sank",
    [
        pytest.param("artikal", 2.50, 2.50, 0.0, id="racunar-i-artikal"),
        pytest.param("sank", 3.75, 0.0, 3.75, id="racunar-i-sank"),
    ],
)
def test_artikal_i_sank_ne_ulaze_u_racunarske_prihode(
    db,
    dodatni_tip,
    dodatni_iznos,
    ocekivani_artikli,
    ocekivani_sank,
):
    smjena_id = _nova_smjena(db)
    _upisi_transakcije(
        db,
        smjena_id,
        [("racunar", 6.00), (dodatni_tip, dodatni_iznos)],
    )

    rezultat = pazar_service.dohvati_pazar_smjene(smjena_id)

    _assert_agregati(
        rezultat,
        ukupno=6.00 + dodatni_iznos,
        racunari=6.00,
        artikli=ocekivani_artikli,
        sank=ocekivani_sank,
        broj_transakcija=2,
    )


def test_kombinacija_racunara_minecrafta_artikla_i_sanka(db):
    smjena_id = _nova_smjena(db)
    _upisi_transakcije(
        db,
        smjena_id,
        [
            ("racunar", 6.00),
            ("minecraft", 2.00),
            ("artikal", 1.50),
            ("sank", 3.00),
        ],
    )

    rezultat = pazar_service.dohvati_pazar_smjene(smjena_id)

    _assert_agregati(
        rezultat,
        ukupno=12.50,
        racunari=8.00,
        artikli=1.50,
        sank=3.00,
        broj_transakcija=4,
    )


def test_svaki_red_ulazi_u_ukupno_tacno_jednom_i_samo_u_svoju_kategoriju(db):
    smjena_id = _nova_smjena(db)
    transakcije = [
        ("racunar", 10.00),
        ("minecraft", 2.00),
        ("prepaid", 5.00),
        ("pass1", 7.00),
        ("pass2", 8.00),
        ("artikal", 1.50),
        ("artikal", 2.50),
        ("sank", 3.00),
        ("sank", 4.00),
    ]
    _upisi_transakcije(db, smjena_id, transakcije)

    rezultat = pazar_service.dohvati_pazar_smjene(smjena_id)

    _assert_agregati(
        rezultat,
        ukupno=sum(iznos for _, iznos in transakcije),
        racunari=32.00,
        artikli=4.00,
        sank=7.00,
        broj_transakcija=len(transakcije),
    )
    assert rezultat["ukupno"] == pytest.approx(
        rezultat["racunari"] + rezultat["artikli"] + rezultat["sank"]
    )
    assert {
        red["tip_prodaje"] for red in rezultat["transakcije"]
    } == {
        "racunar",
        "minecraft",
        "prepaid",
        "pass1",
        "pass2",
        "artikal",
        "sank",
    }
