from datetime import datetime, timedelta
from pathlib import Path

import pytest

import database.db as db_module
from services.pazar import (
    dohvati_historiju_sesija,
    dohvati_opcije_historije_sesija,
)


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    db_path = tmp_path / "session-history.sqlite3"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.inicijalizuj_bazu()
    conn = db_module.get_db()
    yield conn
    db_module.zatvori_bazu()


def _smjena(db, radnik="Tester") -> int:
    cursor = db.execute(
        "INSERT INTO smjene (pocetak, radnik, pazar) VALUES (?, ?, 0)",
        (datetime(2026, 1, 1, 8, 0).isoformat(), radnik),
    )
    db.commit()
    return cursor.lastrowid


def _sesija(
    db,
    smjena_id: int,
    *,
    uredjaj="PC1",
    tip="neograniceno",
    pocetak: datetime,
    trajanje_minuta: int | None = 60,
    iznos=2.0,
) -> tuple[int, str]:
    kraj = (
        (pocetak + timedelta(minutes=trajanje_minuta)).isoformat()
        if trajanje_minuta is not None else None
    )
    cursor = db.execute(
        """INSERT INTO sesije_log
           (smjena_id, uredjaj, vreme_starta, vreme_kraja, iznos, tip)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (smjena_id, uredjaj, pocetak.isoformat(), kraj, iznos, tip),
    )
    db.commit()
    return cursor.lastrowid, pocetak.isoformat()


def _pazar(db, smjena_id, pocetak, tip, iznos, uredjaj="PC1"):
    db.execute(
        """INSERT INTO pazar_arhiva
           (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), uredjaj, iznos, smjena_id, pocetak, tip),
    )
    db.commit()


def test_prazna_historija(db):
    rezultat = dohvati_historiju_sesija()

    assert rezultat == {
        "stavke": [],
        "ukupno": 0,
        "limit": 100,
        "offset": 0,
    }


def test_vise_sesija_prikazuje_aktivne_zavrsene_i_finansije(db):
    smjena_id = _smjena(db)
    _, zavrsena_start = _sesija(
        db,
        smjena_id,
        uredjaj="PC1",
        pocetak=datetime(2026, 1, 2, 10, 0),
        trajanje_minuta=90,
        iznos=3.0,
    )
    _pazar(db, smjena_id, zavrsena_start, "racunar", 3.0)
    _pazar(db, smjena_id, zavrsena_start, "artikal", 2.5)

    _, aktivna_start = _sesija(
        db,
        smjena_id,
        uredjaj="PC2",
        tip="prepaid",
        pocetak=datetime.now() - timedelta(minutes=15),
        trajanje_minuta=None,
        iznos=None,
    )
    _pazar(db, smjena_id, aktivna_start, "prepaid", 5.0, "PC2")

    rezultat = dohvati_historiju_sesija()

    assert rezultat["ukupno"] == 2
    aktivna, zavrsena = rezultat["stavke"]
    assert aktivna["status"] == "aktivna"
    assert aktivna["vreme_kraja"] is None
    assert aktivna["trajanje_sekundi"] >= 14 * 60
    assert aktivna["iznos_racunara"] == pytest.approx(5.0)
    assert zavrsena["status"] == "zavrsena"
    assert zavrsena["trajanje_sekundi"] == 90 * 60
    assert zavrsena["iznos_racunara"] == pytest.approx(3.0)
    assert zavrsena["iznos_artikala"] == pytest.approx(2.5)
    assert zavrsena["ukupno"] == pytest.approx(5.5)
    assert zavrsena["artikli_detalji_dostupni"] is False


def test_filter_datuma_od_i_do(db):
    smjena_id = _smjena(db)
    for dan in (1, 10, 20):
        _sesija(
            db,
            smjena_id,
            pocetak=datetime(2026, 2, dan, 12, 0),
        )

    rezultat = dohvati_historiju_sesija(
        datum_od="2026-02-05",
        datum_do="2026-02-15",
    )

    assert rezultat["ukupno"] == 1
    assert rezultat["stavke"][0]["vreme_starta"].startswith("2026-02-10")


def test_filter_uredjaja(db):
    smjena_id = _smjena(db)
    _sesija(db, smjena_id, uredjaj="PC1", pocetak=datetime(2026, 3, 1, 10))
    _sesija(db, smjena_id, uredjaj="PS5-1", pocetak=datetime(2026, 3, 1, 11))

    rezultat = dohvati_historiju_sesija(uredjaj="PS5-1")

    assert rezultat["ukupno"] == 1
    assert rezultat["stavke"][0]["uredjaj"] == "PS5-1"


def test_filter_tipa(db):
    smjena_id = _smjena(db)
    _sesija(db, smjena_id, tip="minecraft", pocetak=datetime(2026, 3, 2, 10))
    _sesija(db, smjena_id, tip="pass1", pocetak=datetime(2026, 3, 2, 11))

    rezultat = dohvati_historiju_sesija(tip="minecraft")

    assert rezultat["ukupno"] == 1
    assert rezultat["stavke"][0]["tip"] == "minecraft"


@pytest.mark.parametrize(
    "status,ocekivani",
    [("aktivna", "aktivna"), ("zavrsena", "zavrsena")],
)
def test_filter_statusa(db, status, ocekivani):
    smjena_id = _smjena(db)
    _sesija(
        db,
        smjena_id,
        pocetak=datetime.now() - timedelta(hours=1),
        trajanje_minuta=None,
        iznos=None,
    )
    _sesija(db, smjena_id, pocetak=datetime(2026, 3, 3, 10))

    rezultat = dohvati_historiju_sesija(status=status)

    assert rezultat["ukupno"] == 1
    assert rezultat["stavke"][0]["status"] == ocekivani


def test_sortiranje_je_najnovije_prvo_i_id_je_stabilni_tiebreaker(db):
    smjena_id = _smjena(db)
    isto_vrijeme = datetime(2026, 4, 1, 12)
    prvi_id, _ = _sesija(db, smjena_id, uredjaj="PC1", pocetak=isto_vrijeme)
    drugi_id, _ = _sesija(db, smjena_id, uredjaj="PC2", pocetak=isto_vrijeme)
    najnoviji_id, _ = _sesija(
        db,
        smjena_id,
        uredjaj="PC3",
        pocetak=isto_vrijeme + timedelta(minutes=1),
    )

    rezultat = dohvati_historiju_sesija()

    assert [red["id"] for red in rezultat["stavke"]] == [
        najnoviji_id,
        drugi_id,
        prvi_id,
    ]


def test_limit_i_offset_ne_ucitavaju_cijelu_historiju(db):
    smjena_id = _smjena(db)
    for indeks in range(5):
        _sesija(
            db,
            smjena_id,
            uredjaj=f"PC{indeks}",
            pocetak=datetime(2026, 5, 1, 10) + timedelta(minutes=indeks),
        )

    prva = dohvati_historiju_sesija(limit=2, offset=0)
    druga = dohvati_historiju_sesija(limit=2, offset=2)

    assert prva["ukupno"] == 5
    assert len(prva["stavke"]) == 2
    assert len(druga["stavke"]) == 2
    assert {red["id"] for red in prva["stavke"]}.isdisjoint(
        red["id"] for red in druga["stavke"]
    )


def test_pretraga_i_opcije_ukljucuju_historijske_vrijednosti(db):
    smjena_id = _smjena(db, radnik="Amira")
    _sesija(
        db,
        smjena_id,
        uredjaj="OBRISANI-PC",
        tip="pass2",
        pocetak=datetime(2026, 6, 1, 10),
    )

    rezultat = dohvati_historiju_sesija(pretraga="amira")
    opcije = dohvati_opcije_historije_sesija()

    assert rezultat["ukupno"] == 1
    assert opcije == {
        "uredjaji": ["OBRISANI-PC"],
        "tipovi": ["pass2"],
    }
