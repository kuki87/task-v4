from datetime import datetime
from pathlib import Path

import pytest

import database.db as db_module
from services.izvjestaj_perioda import dohvati_izvjestaj_perioda


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    db_path = tmp_path / "period-report.sqlite3"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.inicijalizuj_bazu()
    conn = db_module.get_db()
    yield conn
    db_module.zatvori_bazu()


def _pazar(db, vreme, tip, iznos, *, uredjaj="PC1", smjena_id=1, start=None):
    db.execute(
        """INSERT INTO pazar_arhiva
           (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (vreme, uredjaj, iznos, smjena_id, start or vreme, tip),
    )
    db.commit()


def _smjena(db, pocetak, *, kraj=None, radnik="Tester", pazar=0.0):
    cursor = db.execute(
        """INSERT INTO smjene (pocetak, kraj, radnik, pazar)
           VALUES (?, ?, ?, ?)""",
        (pocetak, kraj, radnik, pazar),
    )
    db.commit()
    return cursor.lastrowid


def _sesija(
    db,
    pocetak,
    *,
    kraj=None,
    tip="neograniceno",
    uredjaj="PC1",
    smjena_id=1,
    iznos=0.0,
):
    cursor = db.execute(
        """INSERT INTO sesije_log
           (smjena_id, uredjaj, vreme_starta, vreme_kraja, iznos, tip)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (smjena_id, uredjaj, pocetak, kraj, iznos, tip),
    )
    db.commit()
    return cursor.lastrowid


def _artikal(db, vreme, naziv, kolicina, ukupno, *, naplaceno=1):
    db.execute(
        """INSERT INTO prodaja_artikala
           (vreme, smjena_id, uredjaj, naziv_artikla, kolicina,
            ukupna_cijena, naplaceno)
           VALUES (?, 1, 'PC1', ?, ?, ?, ?)""",
        (vreme, naziv, kolicina, ukupno, naplaceno),
    )
    db.commit()


def test_prazan_period_vraca_nule_i_prazne_liste(db):
    rezultat = dohvati_izvjestaj_perioda("2026-09-01", "2026-09-01")

    assert rezultat["sazetak"] == {
        "ukupno": 0.0,
        "racunari": 0.0,
        "artikli": 0.0,
        "sank": 0.0,
        "broj_zavrsenih_smjena": 0,
        "broj_sesija": 0,
        "prosjek_po_smjeni": 0.0,
        "prosjek_po_zavrsenoj_sesiji": 0.0,
    }
    assert rezultat["smjene"] == []
    assert rezultat["artikli"]["top_po_kolicini"] == []
    assert len(rezultat["trend"]["tacke"]) == 24


def test_jedan_dan_ukljucuje_samo_taj_dan(db):
    _pazar(db, "2026-09-10T12:00:00", "racunar", 4.0)
    _pazar(db, "2026-09-11T12:00:00", "racunar", 9.0)

    rezultat = dohvati_izvjestaj_perioda("2026-09-10", "2026-09-10")

    assert rezultat["sazetak"]["ukupno"] == pytest.approx(4.0)
    assert rezultat["trend"]["granularnost"] == "sat"


def test_vise_dana_sabira_cijeli_period(db):
    _pazar(db, "2026-09-01T10:00:00", "racunar", 2.0)
    _pazar(db, "2026-09-03T10:00:00", "sank", 3.0)

    rezultat = dohvati_izvjestaj_perioda("2026-09-01", "2026-09-03")

    assert rezultat["sazetak"]["ukupno"] == pytest.approx(5.0)
    assert len(rezultat["trend"]["tacke"]) == 3


def test_granica_tacno_na_pocetku_perioda_je_ukljucena(db):
    _pazar(db, "2026-09-01T00:00:00", "racunar", 1.0)

    rezultat = dohvati_izvjestaj_perioda("2026-09-01", "2026-09-30")

    assert rezultat["sazetak"]["ukupno"] == pytest.approx(1.0)


def test_posljednji_trenutak_datuma_do_je_ukljucen(db):
    _pazar(db, "2026-09-30T23:59:59.999999", "racunar", 2.0)

    rezultat = dohvati_izvjestaj_perioda("2026-09-01", "2026-09-30")

    assert rezultat["sazetak"]["ukupno"] == pytest.approx(2.0)


def test_prvi_trenutak_sljedeceg_dana_je_iskljucen(db):
    _pazar(db, "2026-10-01T00:00:00", "racunar", 7.0)

    rezultat = dohvati_izvjestaj_perioda("2026-09-01", "2026-09-30")

    assert rezultat["sazetak"]["ukupno"] == 0.0


def test_racunari_artikli_i_sank_se_ne_dupliraju(db):
    _pazar(db, "2026-09-05T10:00:00", "racunar", 4.0)
    _pazar(db, "2026-09-05T10:01:00", "prepaid", 5.0)
    _pazar(db, "2026-09-05T10:02:00", "artikal", 2.5)
    _pazar(db, "2026-09-05T10:03:00", "sank", 3.5, uredjaj="Šank")

    rezultat = dohvati_izvjestaj_perioda("2026-09-05", "2026-09-05")

    assert rezultat["sazetak"]["racunari"] == pytest.approx(9.0)
    assert rezultat["sazetak"]["artikli"] == pytest.approx(2.5)
    assert rezultat["sazetak"]["sank"] == pytest.approx(3.5)
    assert rezultat["sazetak"]["ukupno"] == pytest.approx(15.0)


def test_vise_smjena_u_periodu(db):
    prva = _smjena(
        db, "2026-09-03T08:00:00", kraj="2026-09-03T16:00:00", radnik="A"
    )
    druga = _smjena(
        db, "2026-09-04T08:00:00", kraj="2026-09-04T16:00:00", radnik="B"
    )
    _pazar(db, "2026-09-03T12:00:00", "racunar", 10.0, smjena_id=prva)
    _pazar(db, "2026-09-04T12:00:00", "racunar", 20.0, smjena_id=druga)

    rezultat = dohvati_izvjestaj_perioda("2026-09-03", "2026-09-04")

    assert rezultat["sazetak"]["broj_zavrsenih_smjena"] == 2
    assert rezultat["sazetak"]["prosjek_po_smjeni"] == pytest.approx(15.0)
    assert [s["id"] for s in rezultat["smjene"]] == [druga, prva]


def test_otvorena_i_zatvorena_smjena_imaju_jasan_status_i_trajanje(db):
    _smjena(db, "2026-09-06T08:00:00", kraj="2026-09-06T12:00:00")
    _smjena(db, "2026-09-06T13:00:00", kraj=None)

    rezultat = dohvati_izvjestaj_perioda("2026-09-06", "2026-09-06")
    otvorena, zatvorena = rezultat["smjene"]

    assert otvorena["status"] == "otvorena"
    assert otvorena["trajanje_sekundi"] is None
    assert zatvorena["status"] == "zavrsena"
    assert zatvorena["trajanje_sekundi"] == 4 * 3600
    assert rezultat["sazetak"]["broj_zavrsenih_smjena"] == 1


def test_svi_tipovi_sesija_i_aktivne_ne_ulaze_u_trajanje(db):
    tipovi = ["neograniceno", "prepaid", "pass1", "pass2", "minecraft"]
    for indeks, tip in enumerate(tipovi):
        _sesija(
            db,
            f"2026-09-07T1{indeks}:00:00",
            kraj=f"2026-09-07T1{indeks}:30:00",
            tip=tip,
            uredjaj=f"PC{indeks}",
        )
    _sesija(db, "2026-09-07T20:00:00", kraj=None, tip="prepaid", uredjaj="PC9")

    rezultat = dohvati_izvjestaj_perioda("2026-09-07", "2026-09-07")

    assert rezultat["sesije"]["tipovi"] == {
        "neograniceno": 1,
        "prepaid": 2,
        "pass1": 1,
        "pass2": 1,
        "minecraft": 1,
    }
    assert rezultat["sesije"]["aktivne"] == 1
    assert rezultat["sesije"]["zavrsene"] == 5
    assert rezultat["sesije"]["ukupno_trajanje_zavrsenih"] == 5 * 30 * 60


def test_top_uredjaji_po_sesijama_i_prihodu(db):
    for sat in range(3):
        _sesija(db, f"2026-09-08T1{sat}:00:00", kraj=f"2026-09-08T1{sat}:30:00", uredjaj="PC1")
    _sesija(db, "2026-09-08T15:00:00", kraj="2026-09-08T16:00:00", uredjaj="PC2")
    _pazar(db, "2026-09-08T18:00:00", "racunar", 4.0, uredjaj="PC1")
    _pazar(db, "2026-09-08T18:01:00", "racunar", 10.0, uredjaj="PC2")

    rezultat = dohvati_izvjestaj_perioda("2026-09-08", "2026-09-08")

    assert rezultat["sesije"]["top_uredjaji_po_sesijama"][0] == {
        "uredjaj": "PC1", "broj_sesija": 3
    }
    assert rezultat["sesije"]["top_uredjaji_po_prihodu"][0] == {
        "uredjaj": "PC2", "prihod": 10.0
    }


def test_top_artikli_po_kolicini_i_prihodu(db):
    _artikal(db, "2026-09-09T10:00:00", "Kafa", 5, 7.5)
    _artikal(db, "2026-09-09T10:01:00", "Red Bull", 2, 8.0)
    _artikal(db, "2026-09-09T10:02:00", "Nenaplaćeno", 100, 100.0, naplaceno=0)

    rezultat = dohvati_izvjestaj_perioda("2026-09-09", "2026-09-09")

    assert rezultat["artikli"]["ukupna_kolicina"] == 7
    assert rezultat["artikli"]["top_po_kolicini"][0]["naziv"] == "Kafa"
    assert rezultat["artikli"]["top_po_prihodu"][0]["naziv"] == "Red Bull"


def test_isti_artikal_sa_vise_cijena_sabira_kolicinu_i_prihod_bez_jedinicne_cijene(db):
    _artikal(db, "2026-09-12T10:00:00", "Kafa", 2, 3.0)
    _artikal(db, "2026-09-12T11:00:00", "Kafa", 3, 6.0)

    rezultat = dohvati_izvjestaj_perioda("2026-09-12", "2026-09-12")
    kafa = rezultat["artikli"]["top_po_kolicini"][0]

    assert kafa == {"naziv": "Kafa", "kolicina": 5, "prihod": 9.0}
    assert "cijena" not in kafa


def test_dnevni_trend_je_po_satu_i_popunjava_nulte_sate(db):
    _pazar(db, "2026-09-13T03:15:00", "racunar", 3.0)
    _pazar(db, "2026-09-13T03:45:00", "sank", 2.0)

    trend = dohvati_izvjestaj_perioda("2026-09-13", "2026-09-13")["trend"]

    assert trend["granularnost"] == "sat"
    assert len(trend["tacke"]) == 24
    assert trend["tacke"][3] == {"oznaka": "03:00", "iznos": 5.0}
    assert trend["tacke"][4]["iznos"] == 0.0


def test_visednevni_trend_je_po_danu_i_popunjava_prazan_dan(db):
    _pazar(db, "2026-09-14T10:00:00", "racunar", 2.0)
    _pazar(db, "2026-09-16T10:00:00", "racunar", 4.0)

    trend = dohvati_izvjestaj_perioda("2026-09-14", "2026-09-16")["trend"]

    assert trend == {
        "granularnost": "dan",
        "tacke": [
            {"oznaka": "2026-09-14", "iznos": 2.0},
            {"oznaka": "2026-09-15", "iznos": 0.0},
            {"oznaka": "2026-09-16", "iznos": 4.0},
        ],
    }
