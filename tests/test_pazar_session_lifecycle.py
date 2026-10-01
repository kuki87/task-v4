from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import database.db as db_module
import services.pazar as pazar_service
import services.smjena as smjena_service
from models.artikal import Artikal
from models.session_state import SessionState
from ui.kartica_uredjaja import UredjajKartica
from tests.helpers import napravi_test_korisnika


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Svaki test koristi zasebnu produkcijsku SQLite šemu u privremenom folderu."""
    db_module.zatvori_bazu()
    db_path = tmp_path / "caffe-test.sqlite3"
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


def _nova_sesija(*, sati_unazad: int = 1) -> SessionState:
    return SessionState(
        vreme_starta=datetime.now() - timedelta(hours=sati_unazad, seconds=5),
        tip="neograniceno",
    )


@pytest.fixture
def actor(db):
    return napravi_test_korisnika(db)


def _dodaj_staru_smjenu(db) -> int:
    vrijeme = (datetime.now() - timedelta(days=1)).isoformat()
    cursor = db.execute(
        """INSERT INTO smjene (pocetak, kraj, radnik, pazar)
           VALUES (?, ?, ?, ?)""",
        (vrijeme, vrijeme, "Stari radnik", 0.0),
    )
    db.commit()
    return cursor.lastrowid


def test_ponovljeno_dodavanje_artikla_cuva_sve_komade_do_naplate(db, actor):
    smjena_id = smjena_service.otvori_smjenu(actor)
    sesija = _nova_sesija()
    pazar_service.start_sesija("PC 1", sesija, smjena_id, actor=actor)

    # Pozivamo stvarni handler bez kreiranja Qt widgeta, pa pytest-qt nije potreban.
    kartica = SimpleNamespace(
        kosarica=[],
        state=SimpleNamespace(
            trenutna_smjena_id=smjena_id,
            trenutni_korisnik=lambda: actor,
        ),
        ime="PC 1",
        osvjezi=lambda: None,
    )
    for _ in range(3):
        UredjajKartica.dodaj_u_kosaricu(
            kartica, Artikal("Kafa", 1.50)
        )

    assert len(kartica.kosarica) == 1
    assert kartica.kosarica[0].kolicina == 3

    nenaplaceni = pazar_service.dohvati_nenaplacene_artikle(
        smjena_id, "PC 1"
    )
    assert nenaplaceni == [Artikal("Kafa", 1.50, 3)]

    pazar_service.naplati_uredjaj(
        "PC 1",
        sesija,
        [Artikal("Kafa", 1.50, 3)],
        2.0,
        smjena_id,
        actor=actor,
    )

    stanje = db.execute(
        """SELECT COUNT(*) AS broj, SUM(kolicina) AS kolicina,
                  SUM(ukupna_cijena) AS ukupno, SUM(naplaceno) AS naplaceno
           FROM prodaja_artikala
           WHERE smjena_id = ? AND uredjaj = ? AND naziv_artikla = ?""",
        (smjena_id, "PC 1", "Kafa"),
    ).fetchone()
    assert stanje["broj"] == 3
    assert stanje["kolicina"] == 3
    assert stanje["ukupno"] == pytest.approx(4.50)
    assert stanje["naplaceno"] == 3

    artikal_pazar = db.execute(
        """SELECT COUNT(*) AS broj, SUM(iznos) AS ukupno
           FROM pazar_arhiva
           WHERE smjena_id = ? AND uredjaj = ? AND tip_prodaje = 'artikal'""",
        (smjena_id, "PC 1"),
    ).fetchone()
    assert artikal_pazar["broj"] == 1
    assert artikal_pazar["ukupno"] == pytest.approx(4.50)


def test_start_i_naplata_koriste_jedan_lifecycle_red(db, actor):
    smjena_id = smjena_service.otvori_smjenu(actor)
    sesija = _nova_sesija()

    pazar_service.start_sesija("PC 1", sesija, smjena_id, actor=actor)

    redovi_prije = db.execute(
        "SELECT * FROM sesije_log WHERE smjena_id = ? AND uredjaj = ?",
        (smjena_id, "PC 1"),
    ).fetchall()
    assert len(redovi_prije) == 1
    lifecycle_id = redovi_prije[0]["id"]
    assert redovi_prije[0]["vreme_kraja"] is None
    assert redovi_prije[0]["iznos"] is None

    pazar_service.naplati_uredjaj(
        "PC 1", sesija, [], 2.0, smjena_id, actor=actor
    )

    redovi_poslije = db.execute(
        "SELECT * FROM sesije_log WHERE smjena_id = ? AND uredjaj = ?",
        (smjena_id, "PC 1"),
    ).fetchall()
    assert len(redovi_poslije) == 1
    assert redovi_poslije[0]["id"] == lifecycle_id
    assert redovi_poslije[0]["vreme_kraja"] is not None
    assert redovi_poslije[0]["iznos"] is not None
    assert db.execute(
        "SELECT COUNT(*) FROM sesije_log WHERE vreme_kraja IS NULL"
    ).fetchone()[0] == 0


def test_zatvaranje_smjene_naplacuje_sve_sesije_i_pazar_racuna_iz_baze(db, actor):
    smjena_id = smjena_service.otvori_smjenu(actor)
    prva = _nova_sesija(sati_unazad=1)
    druga = _nova_sesija(sati_unazad=2)
    pazar_service.start_sesija("PC 1", prva, smjena_id, actor=actor)
    pazar_service.start_sesija("PC 2", druga, smjena_id, actor=actor)
    pazar_service.dodaj_artikal_na_uredjaj(
        smjena_id, "PC 1", "Sok", 2, 1.50, actor=actor
    )

    vrijeme = datetime.now().isoformat()
    db.execute(
        """INSERT INTO pazar_arhiva
           (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (vrijeme, "Šank", 3.25, smjena_id, vrijeme, "sank"),
    )
    db.commit()

    rezultat = smjena_service.zatvori_smjenu(
        smjena_id,
        {
            "PC 1": (prva, [Artikal("Sok", 1.50, 2)], 2.0),
            "PC 2": (druga, [], 2.0),
        },
        [],
        actor=actor,
    )

    assert db.execute(
        """SELECT COUNT(*) FROM sesije_log
           WHERE smjena_id = ? AND vreme_kraja IS NULL""",
        (smjena_id,),
    ).fetchone()[0] == 0
    zatvorene = db.execute(
        """SELECT uredjaj, iznos FROM sesije_log
           WHERE smjena_id = ? ORDER BY uredjaj""",
        (smjena_id,),
    ).fetchall()
    assert [red["uredjaj"] for red in zatvorene] == ["PC 1", "PC 2"]
    assert all(red["iznos"] is not None for red in zatvorene)

    db_pazar = db.execute(
        "SELECT SUM(iznos) FROM pazar_arhiva WHERE smjena_id = ?",
        (smjena_id,),
    ).fetchone()[0]
    smjena = db.execute(
        "SELECT kraj, pazar FROM smjene WHERE id = ?", (smjena_id,)
    ).fetchone()
    assert smjena["kraj"] is not None
    assert smjena["pazar"] == pytest.approx(db_pazar)
    assert rezultat["pazar"] == pytest.approx(db_pazar)
    assert set(rezultat["naplacene_sesije"]) == {"PC 1", "PC 2"}

    vrste = db.execute(
        """SELECT tip_prodaje, COUNT(*) AS broj
           FROM pazar_arhiva WHERE smjena_id = ?
           GROUP BY tip_prodaje""",
        (smjena_id,),
    ).fetchall()
    assert {red["tip_prodaje"]: red["broj"] for red in vrste} == {
        "artikal": 1,
        "racunar": 2,
        "sank": 1,
    }


def test_greska_jedne_naplate_rollbackuje_cijelo_zatvaranje_smjene(
    db, actor, monkeypatch: pytest.MonkeyPatch
):
    smjena_id = smjena_service.otvori_smjenu(actor)
    prva = _nova_sesija(sati_unazad=1)
    druga = _nova_sesija(sati_unazad=2)
    pazar_service.start_sesija("PC 1", prva, smjena_id, actor=actor)
    pazar_service.start_sesija("PC 2", druga, smjena_id, actor=actor)
    pazar_service.dodaj_artikal_na_uredjaj(
        smjena_id, "PC 1", "Kafa", 1, 1.50, actor=actor
    )

    stvarna_naplata = pazar_service.naplati_uredjaj
    pozivi = []

    def naplata_sa_greskom(*args, **kwargs):
        pozivi.append(args[0])
        assert kwargs["commit"] is False
        if len(pozivi) == 2:
            raise RuntimeError("Simulirana greška druge naplate")
        return stvarna_naplata(*args, **kwargs)

    monkeypatch.setattr(
        smjena_service, "naplati_uredjaj", naplata_sa_greskom
    )

    with pytest.raises(RuntimeError, match="Simulirana greška"):
        smjena_service.zatvori_smjenu(
            smjena_id,
            {
                "PC 1": (prva, [Artikal("Kafa", 1.50)], 2.0),
                "PC 2": (druga, [], 2.0),
            },
            [],
            actor=actor,
        )

    assert pozivi == ["PC 1", "PC 2"]
    assert db.execute(
        """SELECT COUNT(*) FROM sesije_log
           WHERE smjena_id = ? AND vreme_kraja IS NULL AND iznos IS NULL""",
        (smjena_id,),
    ).fetchone()[0] == 2
    assert db.execute(
        "SELECT COUNT(*) FROM pazar_arhiva WHERE smjena_id = ?",
        (smjena_id,),
    ).fetchone()[0] == 0
    assert db.execute(
        """SELECT COUNT(*) FROM prodaja_artikala
           WHERE smjena_id = ? AND naplaceno = 0""",
        (smjena_id,),
    ).fetchone()[0] == 1
    smjena = db.execute(
        "SELECT kraj, pazar FROM smjene WHERE id = ?", (smjena_id,)
    ).fetchone()
    assert smjena["kraj"] is None
    assert smjena["pazar"] == pytest.approx(0.0)


def test_transfer_mijenja_samo_aktivnu_sesiju_i_nenaplacene_artikle(db, actor):
    stara_smjena_id = _dodaj_staru_smjenu(db)
    smjena_id = smjena_service.otvori_smjenu(actor)
    sesija = _nova_sesija()
    pazar_service.start_sesija("PC 1", sesija, smjena_id, actor=actor)
    aktivni_id = db.execute(
        """SELECT id FROM sesije_log
           WHERE smjena_id = ? AND uredjaj = ? AND vreme_kraja IS NULL""",
        (smjena_id, "PC 1"),
    ).fetchone()["id"]

    staro_vrijeme = (datetime.now() - timedelta(days=1)).isoformat()
    istorijska_sesija_id = db.execute(
        """INSERT INTO sesije_log
           (smjena_id, uredjaj, vreme_starta, vreme_kraja, iznos, tip)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (stara_smjena_id, "PC 1", staro_vrijeme, staro_vrijeme, 2.0, "neograniceno"),
    ).lastrowid
    pazar_service.dodaj_artikal_na_uredjaj(
        smjena_id, "PC 1", "Sok", 2, 2.0, actor=actor
    )
    naplaceni_id = db.execute(
        """INSERT INTO prodaja_artikala
           (vreme, smjena_id, uredjaj, naziv_artikla, kolicina, ukupna_cijena, naplaceno)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (staro_vrijeme, smjena_id, "PC 1", "Stara kafa", 1, 1.50),
    ).lastrowid
    stari_nenaplaceni_id = db.execute(
        """INSERT INTO prodaja_artikala
           (vreme, smjena_id, uredjaj, naziv_artikla, kolicina, ukupna_cijena, naplaceno)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (staro_vrijeme, stara_smjena_id, "PC 1", "Stari dug", 1, 2.50),
    ).lastrowid
    db.commit()

    pazar_service.prebaci_sesiju_na_uredjaj(
        smjena_id, "PC 1", "PC 2", actor=actor
    )

    aktivna = db.execute(
        "SELECT uredjaj, vreme_kraja FROM sesije_log WHERE id = ?",
        (aktivni_id,),
    ).fetchone()
    istorijska = db.execute(
        "SELECT uredjaj, vreme_kraja FROM sesije_log WHERE id = ?",
        (istorijska_sesija_id,),
    ).fetchone()
    assert aktivna["uredjaj"] == "PC 2"
    assert aktivna["vreme_kraja"] is None
    assert istorijska["uredjaj"] == "PC 1"
    assert istorijska["vreme_kraja"] is not None

    trenutni_nenaplaceni = db.execute(
        """SELECT uredjaj FROM prodaja_artikala
           WHERE smjena_id = ? AND naziv_artikla = ? AND naplaceno = 0""",
        (smjena_id, "Sok"),
    ).fetchone()
    naplaceni = db.execute(
        "SELECT uredjaj, naplaceno FROM prodaja_artikala WHERE id = ?",
        (naplaceni_id,),
    ).fetchone()
    stari_nenaplaceni = db.execute(
        "SELECT uredjaj, naplaceno FROM prodaja_artikala WHERE id = ?",
        (stari_nenaplaceni_id,),
    ).fetchone()
    assert trenutni_nenaplaceni["uredjaj"] == "PC 2"
    assert (naplaceni["uredjaj"], naplaceni["naplaceno"]) == ("PC 1", 1)
    assert (stari_nenaplaceni["uredjaj"], stari_nenaplaceni["naplaceno"]) == (
        "PC 1",
        0,
    )

    broj_lifecycle_redova = db.execute(
        "SELECT COUNT(*) FROM sesije_log WHERE id = ?", (aktivni_id,)
    ).fetchone()[0]
    pazar_service.naplati_uredjaj(
        "PC 2", sesija, [Artikal("Sok", 2.0, 2)], 2.0, smjena_id,
        actor=actor,
    )
    zatvorena = db.execute(
        "SELECT uredjaj, vreme_kraja FROM sesije_log WHERE id = ?",
        (aktivni_id,),
    ).fetchone()
    assert broj_lifecycle_redova == 1
    assert zatvorena["uredjaj"] == "PC 2"
    assert zatvorena["vreme_kraja"] is not None
    assert db.execute(
        """SELECT COUNT(*) FROM sesije_log
           WHERE smjena_id = ? AND vreme_kraja IS NULL""",
        (smjena_id,),
    ).fetchone()[0] == 0
    assert db.execute(
        """SELECT naplaceno FROM prodaja_artikala
           WHERE smjena_id = ? AND naziv_artikla = ?""",
        (smjena_id, "Sok"),
    ).fetchone()[0] == 1


def test_transfer_na_uredjaj_sa_aktivnom_sesijom_se_odbija(db, actor):
    smjena_id = smjena_service.otvori_smjenu(actor)
    izvorna = _nova_sesija()
    ciljna = _nova_sesija()
    pazar_service.start_sesija("PC 1", izvorna, smjena_id, actor=actor)
    pazar_service.start_sesija("PC 2", ciljna, smjena_id, actor=actor)
    pazar_service.dodaj_artikal_na_uredjaj(
        smjena_id, "PC 1", "Kafa", 1, 1.50, actor=actor
    )

    with pytest.raises(ValueError):
        pazar_service.prebaci_sesiju_na_uredjaj(
            smjena_id, "PC 1", "PC 2", actor=actor
        )

    aktivni = db.execute(
        """SELECT uredjaj FROM sesije_log
           WHERE smjena_id = ? AND vreme_kraja IS NULL ORDER BY uredjaj""",
        (smjena_id,),
    ).fetchall()
    assert [red["uredjaj"] for red in aktivni] == ["PC 1", "PC 2"]
    artikal = db.execute(
        """SELECT uredjaj, naplaceno FROM prodaja_artikala
           WHERE smjena_id = ? AND naziv_artikla = ?""",
        (smjena_id, "Kafa"),
    ).fetchone()
    assert (artikal["uredjaj"], artikal["naplaceno"]) == ("PC 1", 0)
    assert db.execute(
        """SELECT COUNT(*) FROM logovi
           WHERE smjena_id = ? AND akcija = 'SESSION_TRANSFERRED'""",
        (smjena_id,),
    ).fetchone()[0] == 0
