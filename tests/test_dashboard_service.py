from datetime import datetime, timedelta
from pathlib import Path

import pytest

import database.db as db_module
from services.pazar import dohvati_dashboard_smjene


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    db_path = tmp_path / "dashboard-test.sqlite3"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.inicijalizuj_bazu()
    conn = db_module.get_db()
    yield conn
    db_module.zatvori_bazu()


def _smjena(db) -> int:
    cursor = db.execute(
        "INSERT INTO smjene (pocetak, radnik, pazar) VALUES (?, ?, 0)",
        (datetime.now().isoformat(), "Tester"),
    )
    db.commit()
    return cursor.lastrowid


def _uredjaji(db, *imena: str):
    db.executemany(
        "INSERT INTO uredjaji (ime, cena, tip, grupa) VALUES (?, ?, ?, ?)",
        [(ime, 2.0, "PC", "Classic") for ime in imena],
    )
    db.commit()


def _transakcije(db, smjena_id: int, redovi: list[tuple[str, str, float]]):
    pocetak = datetime(2026, 1, 1, 12, 0)
    db.executemany(
        """INSERT INTO pazar_arhiva
           (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (
                (pocetak + timedelta(minutes=indeks)).isoformat(),
                uredjaj,
                iznos,
                smjena_id,
                pocetak.isoformat(),
                tip,
            )
            for indeks, (uredjaj, tip, iznos) in enumerate(redovi)
        ],
    )
    db.commit()


def _sesija(
    db,
    smjena_id: int,
    uredjaj: str,
    tip: str = "neograniceno",
    *,
    limit_sekundi=None,
    zavrsena: bool = False,
):
    pocetak = datetime.now() - timedelta(minutes=1)
    db.execute(
        """INSERT INTO sesije_log
           (smjena_id, uredjaj, vreme_starta, vreme_kraja, iznos, tip, limit_sekundi)
           VALUES (?, ?, ?, ?, NULL, ?, ?)""",
        (
            smjena_id,
            uredjaj,
            pocetak.isoformat(),
            datetime.now().isoformat() if zavrsena else None,
            tip,
            limit_sekundi,
        ),
    )
    db.commit()


def _prodaja_artikla(
    db,
    smjena_id: int,
    naziv: str,
    kolicina: int,
    *,
    naplaceno: int = 1,
    cijena: float = 1.5,
):
    db.execute(
        """INSERT INTO prodaja_artikala
           (vreme, smjena_id, uredjaj, naziv_artikla, kolicina,
            ukupna_cijena, naplaceno)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),
            smjena_id,
            "PC1",
            naziv,
            kolicina,
            cijena * kolicina,
            naplaceno,
        ),
    )
    db.commit()


def test_prazna_smjena_vraca_nule_i_operativnu_strukturu(db):
    smjena_id = _smjena(db)
    _uredjaji(db, "PC1", "PC2", "PS5-1")

    rezultat = dohvati_dashboard_smjene(smjena_id)

    assert rezultat["ukupno"] == 0
    assert rezultat["racunari"] == 0
    assert rezultat["artikli"] == 0
    assert rezultat["sank"] == 0
    assert rezultat["aktivni_uredjaji"] == 0
    assert rezultat["slobodni_uredjaji"] == 3
    assert rezultat["aktivne_prepaid_pass"] == 0
    assert rezultat["broj_prodanih_artikala"] == 0
    assert rezultat["top_artikli"] == []
    assert rezultat["posljednje_transakcije"] == []
    assert rezultat["kretanje_pazara"] == []


def test_dashboard_sa_samo_racunarskim_prihodima(db):
    smjena_id = _smjena(db)
    _transakcije(
        db,
        smjena_id,
        [("PC1", "racunar", 4.0), ("PC2", "minecraft", 3.5)],
    )

    rezultat = dohvati_dashboard_smjene(smjena_id)

    assert rezultat["ukupno"] == pytest.approx(7.5)
    assert rezultat["racunari"] == pytest.approx(7.5)
    assert rezultat["artikli"] == 0
    assert rezultat["sank"] == 0


def test_dashboard_kombinuje_racunare_artikle_i_sank_tacno_jednom(db):
    smjena_id = _smjena(db)
    _transakcije(
        db,
        smjena_id,
        [
            ("PC1", "racunar", 4.0),
            ("PC1", "artikal", 3.0),
            ("Šank", "sank", 2.5),
        ],
    )

    rezultat = dohvati_dashboard_smjene(smjena_id)

    assert rezultat["ukupno"] == pytest.approx(9.5)
    assert rezultat["racunari"] == pytest.approx(4.0)
    assert rezultat["artikli"] == pytest.approx(3.0)
    assert rezultat["sank"] == pytest.approx(2.5)
    assert rezultat["broj_transakcija"] == 3


def test_top_pet_artikala_i_broj_komada_koriste_samo_naplacene_redove(db):
    smjena_id = _smjena(db)
    for naziv, kolicina in [
        ("Kafa", 8),
        ("Voda", 5),
        ("Sok", 4),
        ("Čips", 3),
        ("Čaj", 2),
        ("Keks", 1),
    ]:
        _prodaja_artikla(db, smjena_id, naziv, kolicina)
    _prodaja_artikla(db, smjena_id, "Nenaplaćeno", 100, naplaceno=0)

    rezultat = dohvati_dashboard_smjene(smjena_id)

    assert rezultat["broj_prodanih_artikala"] == 23
    assert [red["naziv_artikla"] for red in rezultat["top_artikli"]] == [
        "Kafa",
        "Voda",
        "Sok",
        "Čips",
        "Čaj",
    ]
    assert [red["kolicina"] for red in rezultat["top_artikli"]] == [8, 5, 4, 3, 2]


def test_posljednjih_pet_transakcija_je_ograniceno_i_sortirano(db):
    smjena_id = _smjena(db)
    _transakcije(
        db,
        smjena_id,
        [(f"PC{i}", "racunar", float(i)) for i in range(1, 8)],
    )

    rezultat = dohvati_dashboard_smjene(smjena_id)

    assert len(rezultat["posljednje_transakcije"]) == 5
    assert [red["uredjaj"] for red in rezultat["posljednje_transakcije"]] == [
        "PC7",
        "PC6",
        "PC5",
        "PC4",
        "PC3",
    ]
    assert rezultat["kretanje_pazara"][-1]["ukupno"] == pytest.approx(28.0)


def test_vise_aktivnih_uredjaja_i_slobodni_broj(db):
    smjena_id = _smjena(db)
    _uredjaji(db, "PC1", "PC2", "PC3", "PC4")
    _sesija(db, smjena_id, "PC1")
    _sesija(db, smjena_id, "PC2", "minecraft")
    _sesija(db, smjena_id, "PC3", zavrsena=True)

    rezultat = dohvati_dashboard_smjene(smjena_id)

    assert rezultat["aktivni_uredjaji"] == 2
    assert rezultat["slobodni_uredjaji"] == 2


def test_prepaid_i_pass_sesije_i_sesije_koje_uskoro_isticu(db):
    smjena_id = _smjena(db)
    _uredjaji(db, "PC1", "PC2", "PC3", "PC4")
    _sesija(db, smjena_id, "PC1", "prepaid", limit_sekundi=10 * 60)
    _sesija(db, smjena_id, "PC2", "pass1", limit_sekundi=2 * 60 * 60)
    _sesija(db, smjena_id, "PC3", "pass2")
    _sesija(db, smjena_id, "PC4", "neograniceno")

    rezultat = dohvati_dashboard_smjene(smjena_id)

    assert rezultat["aktivne_prepaid_pass"] == 3
    assert [red["uredjaj"] for red in rezultat["uskoro_isticu"]] == ["PC1"]
    assert rezultat["uskoro_isticu"][0]["tip"] == "prepaid"
