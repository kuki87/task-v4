from datetime import datetime, timedelta
from pathlib import Path

import pytest

import database.db as db_module
import services.smjena as smjena_service


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    db_path = tmp_path / "smjena-test.sqlite3"
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


def test_otvorena_smjena_blokira_drugu_i_cuva_value_error_ugovor(db):
    prva_id = smjena_service.otvori_smjenu("Ana")
    prije = dict(db.execute("SELECT * FROM smjene WHERE id = ?", (prva_id,)).fetchone())

    with pytest.raises(ValueError) as greska:
        smjena_service.otvori_smjenu("Boris")

    assert "Ana" in str(greska.value)
    assert db.execute("SELECT COUNT(*) FROM smjene").fetchone()[0] == 1
    poslije = dict(
        db.execute("SELECT * FROM smjene WHERE id = ?", (prva_id,)).fetchone()
    )
    assert poslije == prije
    assert smjena_service.dohvati_aktivnu_smjenu() == {
        "id": prva_id,
        "pocetak": prije["pocetak"],
        "radnik": "Ana",
    }


def test_zatvorena_smjena_ne_blokira_otvaranje_nove(db):
    prva_id = smjena_service.otvori_smjenu("Ana")
    rezultat = smjena_service.zatvori_smjenu(prva_id, {}, [])

    druga_id = smjena_service.otvori_smjenu("Boris")

    assert druga_id != prva_id
    prva = db.execute("SELECT * FROM smjene WHERE id = ?", (prva_id,)).fetchone()
    assert prva["kraj"] is not None
    assert prva["pazar"] == pytest.approx(0.0)
    assert rezultat["smjena_id"] == prva_id
    assert smjena_service.dohvati_aktivnu_smjenu()["id"] == druga_id


def test_zatecena_otvorena_smjena_ostaje_netaknuta_do_zatvaranja(db):
    pocetak = (datetime.now() - timedelta(hours=8)).isoformat()
    cursor = db.execute(
        """INSERT INTO smjene (pocetak, kraj, radnik, pazar)
           VALUES (?, NULL, ?, ?)""",
        (pocetak, "Zatečeni radnik", 17.25),
    )
    smjena_id = cursor.lastrowid
    vrijeme_prodaje = (datetime.now() - timedelta(hours=1)).isoformat()
    db.execute(
        """INSERT INTO pazar_arhiva
           (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            vrijeme_prodaje,
            "Šank",
            17.25,
            smjena_id,
            vrijeme_prodaje,
            "sank",
        ),
    )
    db.commit()
    prije = dict(db.execute("SELECT * FROM smjene WHERE id = ?", (smjena_id,)).fetchone())

    aktivna = smjena_service.dohvati_aktivnu_smjenu()
    assert aktivna == {
        "id": smjena_id,
        "pocetak": pocetak,
        "radnik": "Zatečeni radnik",
    }
    with pytest.raises(ValueError):
        smjena_service.otvori_smjenu("Novi radnik")
    assert dict(
        db.execute("SELECT * FROM smjene WHERE id = ?", (smjena_id,)).fetchone()
    ) == prije

    smjena_service.zatvori_smjenu(smjena_id, {}, [])
    zatvorena = dict(
        db.execute("SELECT * FROM smjene WHERE id = ?", (smjena_id,)).fetchone()
    )
    assert zatvorena["pocetak"] == prije["pocetak"]
    assert zatvorena["radnik"] == prije["radnik"]
    assert zatvorena["kraj"] is not None
    assert zatvorena["pazar"] == pytest.approx(17.25)

    nova_id = smjena_service.otvori_smjenu("Novi radnik")
    assert nova_id != smjena_id
