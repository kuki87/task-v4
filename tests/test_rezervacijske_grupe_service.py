from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import database.db as db_module
import services.rezervacije as rezervacije
from models.user import UserIdentity
from tests.helpers import napravi_test_korisnika


TEST_ACTOR = UserIdentity(1, "tester", "Tester", "admin")


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "grupe.sqlite3"))
    db_module.inicijalizuj_bazu()
    conn = db_module.get_db()
    assert napravi_test_korisnika(conn) == TEST_ACTOR
    conn.executemany(
        "INSERT INTO uredjaji (ime, cena, tip, grupa) VALUES (?, ?, ?, ?)",
        [
            ("PC1", 2.0, "PC", "Classic"),
            ("PC2", 2.0, "PC", "Classic"),
            ("PC3", 3.0, "PC", "VIP"),
            ("PC4", 3.0, "PC", "VIP"),
            ("PC5", 3.0, "PC", "VIP"),
            ("PS5-1", 4.0, "PS5", "PS5"),
        ],
    )
    conn.commit()
    yield conn
    db_module.zatvori_bazu()


def _ids(db, *imena):
    placeholders = ", ".join("?" for _ in imena)
    redovi = db.execute(
        f"SELECT id, ime FROM uredjaji WHERE ime IN ({placeholders})", imena
    ).fetchall()
    mapa = {red["ime"]: red["id"] for red in redovi}
    return [mapa[ime] for ime in imena]


def _termin(*, dani=2, sat=18, minuta=0, trajanje=120):
    pocetak = (datetime.now() + timedelta(days=dani)).replace(
        hour=sat, minute=minuta, second=0, microsecond=0
    )
    return pocetak, pocetak + timedelta(minutes=trajanje)


def _grupa(db, imena=("PC1", "PC2"), *, pocetak=None, kraj=None, **kwargs):
    if pocetak is None:
        pocetak, kraj = _termin()
    return rezervacije.kreiraj_rezervacijsku_grupu(
        _ids(db, *imena), "Grupni gost", pocetak, kraj,
        actor=TEST_ACTOR, **kwargs
    )


def _uredjaji_grupe(db, grupa_id):
    return {
        red[0]
        for red in db.execute(
            """SELECT u.ime FROM rezervacije r
               JOIN uredjaji u ON u.id = r.uredjaj_id
               WHERE r.grupa_id = ?""",
            (grupa_id,),
        )
    }


def test_kreiranje_grupe_sa_dva_uredjaja(db):
    grupa_id = _grupa(db)
    grupa = rezervacije.dohvati_rezervacijsku_grupu(grupa_id)
    assert grupa["ime_gosta"] == "Grupni gost"
    assert {u["ime"] for u in grupa["uredjaji"]} == {"PC1", "PC2"}


def test_kreiranje_grupe_sa_pet_uredjaja(db):
    imena = ("PC1", "PC2", "PC3", "PC4", "PC5")
    grupa_id = _grupa(db, imena)
    assert _uredjaji_grupe(db, grupa_id) == set(imena)


def test_grupa_sa_manje_od_dva_uredjaja_se_odbija(db):
    pocetak, kraj = _termin()
    with pytest.raises(ValueError, match="najmanje 2"):
        rezervacije.kreiraj_rezervacijsku_grupu(
            _ids(db, "PC1"), "Gost", pocetak, kraj, actor=TEST_ACTOR
        )


def test_konflikt_jednog_uredjaja_rusi_cijelu_grupu(db):
    pocetak, kraj = _termin()
    rezervacije.kreiraj_rezervaciju(
        _ids(db, "PC2")[0], "Pojedinac", pocetak, kraj, actor=TEST_ACTOR
    )
    with pytest.raises(ValueError, match="PC2"):
        _grupa(db, pocetak=pocetak, kraj=kraj)


def test_nijedan_child_ni_parent_ne_ostaje_nakon_konflikta(db):
    pocetak, kraj = _termin()
    rezervacije.kreiraj_rezervaciju(
        _ids(db, "PC2")[0], "Pojedinac", pocetak, kraj, actor=TEST_ACTOR
    )
    with pytest.raises(ValueError):
        _grupa(db, pocetak=pocetak, kraj=kraj)
    assert db.execute("SELECT COUNT(*) FROM rezervacijske_grupe").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM rezervacije WHERE grupa_id IS NOT NULL").fetchone()[0] == 0


def test_isti_termin_na_drugim_slobodnim_uredjajima_prolazi(db):
    pocetak, kraj = _termin()
    prva = _grupa(db, ("PC1", "PC2"), pocetak=pocetak, kraj=kraj)
    druga = _grupa(db, ("PC3", "PC4"), pocetak=pocetak, kraj=kraj)
    assert prva != druga


def test_dodirni_termini_prolaze(db):
    pocetak, kraj = _termin()
    _grupa(db, pocetak=pocetak, kraj=kraj)
    druga = _grupa(
        db, pocetak=kraj, kraj=kraj + timedelta(hours=1)
    )
    assert druga > 0


def test_prijedlog_vraca_tacno_trazeni_broj_slobodnih(db):
    pocetak, kraj = _termin()
    rezultat = rezervacije.dohvati_slobodne_uredjaje_za_period(
        pocetak, kraj, tip="PC", broj=3
    )
    assert len(rezultat) == 3
    assert all(red["tip"] == "PC" for red in rezultat)


def test_prijedlog_vraca_manje_kada_nema_dovoljno_slobodnih(db):
    pocetak, kraj = _termin()
    _grupa(db, ("PC1", "PC2", "PC3", "PC4"), pocetak=pocetak, kraj=kraj)
    rezultat = rezervacije.dohvati_slobodne_uredjaje_za_period(
        pocetak, kraj, tip="PC", broj=3
    )
    assert [red["ime"] for red in rezultat] == ["PC5"]


def test_prijedlog_filtrira_po_tipu_i_grupi(db):
    pocetak, kraj = _termin()
    vip = rezervacije.dohvati_slobodne_uredjaje_za_period(
        pocetak, kraj, tip="PC", grupa="VIP"
    )
    ps5 = rezervacije.dohvati_slobodne_uredjaje_za_period(
        pocetak, kraj, tip="PS5"
    )
    assert {red["ime"] for red in vip} == {"PC3", "PC4", "PC5"}
    assert [red["ime"] for red in ps5] == ["PS5-1"]


def test_izmjena_vremena_bez_konflikta(db):
    grupa_id = _grupa(db)
    pocetak, kraj = _termin(sat=21)
    rezervacije.izmijeni_rezervacijsku_grupu(
        grupa_id, _ids(db, "PC1", "PC2"), "Novo ime", pocetak, kraj,
        actor=TEST_ACTOR,
    )
    grupa = rezervacije.dohvati_rezervacijsku_grupu(grupa_id)
    assert grupa["pocetak"] == pocetak.isoformat()
    assert grupa["ime_gosta"] == "Novo ime"


def test_izmjena_vremena_sa_konfliktom_ne_mijenja_grupu(db):
    grupa_id = _grupa(db)
    stari = rezervacije.dohvati_rezervacijsku_grupu(grupa_id)
    pocetak, kraj = _termin(sat=21)
    rezervacije.kreiraj_rezervaciju(
        _ids(db, "PC1")[0], "Drugi", pocetak, kraj, actor=TEST_ACTOR
    )
    with pytest.raises(ValueError, match="PC1"):
        rezervacije.izmijeni_rezervacijsku_grupu(
            grupa_id, _ids(db, "PC1", "PC2"), "Novo", pocetak, kraj,
            actor=TEST_ACTOR,
        )
    poslije = rezervacije.dohvati_rezervacijsku_grupu(grupa_id)
    assert poslije["pocetak"] == stari["pocetak"]
    assert poslije["ime_gosta"] == stari["ime_gosta"]


def test_izmjena_dodaje_uredjaj(db):
    grupa_id = _grupa(db)
    pocetak, kraj = _termin()
    rezervacije.izmijeni_rezervacijsku_grupu(
        grupa_id, _ids(db, "PC1", "PC2", "PC3"), "Gost", pocetak, kraj,
        actor=TEST_ACTOR,
    )
    assert _uredjaji_grupe(db, grupa_id) == {"PC1", "PC2", "PC3"}


def test_izmjena_uklanja_uredjaj_ali_cuva_najmanje_dva(db):
    grupa_id = _grupa(db, ("PC1", "PC2", "PC3"))
    pocetak, kraj = _termin()
    rezervacije.izmijeni_rezervacijsku_grupu(
        grupa_id, _ids(db, "PC1", "PC2"), "Gost", pocetak, kraj,
        actor=TEST_ACTOR,
    )
    assert _uredjaji_grupe(db, grupa_id) == {"PC1", "PC2"}


def test_izmjena_zamjenjuje_uredjaj(db):
    grupa_id = _grupa(db)
    pocetak, kraj = _termin()
    rezervacije.izmijeni_rezervacijsku_grupu(
        grupa_id, _ids(db, "PC1", "PC3"), "Gost", pocetak, kraj,
        actor=TEST_ACTOR,
    )
    assert _uredjaji_grupe(db, grupa_id) == {"PC1", "PC3"}


def test_status_grupe_se_propagira_na_svu_djecu(db):
    grupa_id = _grupa(db, ("PC1", "PC2", "PC3"))
    rezervacije.promijeni_status_rezervacijske_grupe(
        grupa_id, "stigao", TEST_ACTOR
    )
    statusi = {
        red[0] for red in db.execute(
            "SELECT status FROM rezervacije WHERE grupa_id = ?", (grupa_id,)
        )
    }
    assert statusi == {"stigao"}
    assert rezervacije.dohvati_rezervacijsku_grupu(grupa_id)["status"] == "stigao"


def test_nedozvoljena_statusna_tranzicija_ne_mijenja_grupu(db):
    grupa_id = _grupa(db)
    broj_logova = db.execute("SELECT COUNT(*) FROM logovi").fetchone()[0]
    with pytest.raises(ValueError, match="nije dozvoljen"):
        rezervacije.promijeni_status_rezervacijske_grupe(
            grupa_id, "zavrseno", TEST_ACTOR
        )
    assert rezervacije.dohvati_rezervacijsku_grupu(grupa_id)["status"] == "rezervisano"
    assert db.execute("SELECT COUNT(*) FROM logovi").fetchone()[0] == broj_logova


def test_grupne_akcije_upisuju_ocekivani_audit(db):
    grupa_id = _grupa(db)
    rezervacije.promijeni_status_rezervacijske_grupe(
        grupa_id, "stigao", TEST_ACTOR, smjena_id=None
    )
    rezervacije.promijeni_status_rezervacijske_grupe(
        grupa_id, "zavrseno", TEST_ACTOR, smjena_id=None
    )
    akcije = [
        red[0] for red in db.execute(
            "SELECT akcija FROM logovi WHERE entitet = ? ORDER BY id",
            ("rezervacijska_grupa",),
        )
    ]
    assert akcije == [
        "RESERVATION_GROUP_CREATED",
        "RESERVATION_GROUP_ARRIVED",
        "RESERVATION_GROUP_COMPLETED",
    ]


def test_audit_failure_rollbackuje_parent_i_svu_djecu(db, monkeypatch):
    monkeypatch.setattr(
        rezervacije,
        "upisi_audit_u_transakciji",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit")),
    )
    with pytest.raises(RuntimeError, match="audit"):
        _grupa(db)
    assert db.execute("SELECT COUNT(*) FROM rezervacijske_grupe").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM rezervacije").fetchone()[0] == 0


def test_neaktivan_actor_nema_dozvolu_i_nema_parcijalnog_upisa(db):
    db.execute("UPDATE korisnici SET aktivan = 0 WHERE id = ?", (TEST_ACTOR.id,))
    db.commit()
    with pytest.raises(PermissionError):
        _grupa(db)
    assert db.execute("SELECT COUNT(*) FROM rezervacijske_grupe").fetchone()[0] == 0


def test_historijska_zavrsena_grupa_ostaje_citljiva(db):
    grupa_id = _grupa(db)
    rezervacije.promijeni_status_rezervacijske_grupe(
        grupa_id, "stigao", TEST_ACTOR
    )
    rezervacije.promijeni_status_rezervacijske_grupe(
        grupa_id, "zavrseno", TEST_ACTOR
    )
    grupa = rezervacije.dohvati_rezervacijsku_grupu(grupa_id)
    assert grupa["status"] == "zavrseno"
    assert len(grupa["uredjaji"]) == 2


def test_migracija_je_idempotentna_i_stari_red_ostaje_individualan(db):
    pocetak, kraj = _termin()
    red_id = rezervacije.kreiraj_rezervaciju(
        _ids(db, "PC1")[0], "Stari", pocetak, kraj, actor=TEST_ACTOR
    )
    prije = db.execute("SELECT COUNT(*) FROM rezervacije").fetchone()[0]
    db_module.inicijalizuj_bazu()
    db_module.inicijalizuj_bazu()
    poslije = db.execute("SELECT COUNT(*) FROM rezervacije").fetchone()[0]
    red = db.execute(
        "SELECT grupa_id FROM rezervacije WHERE id = ?", (red_id,)
    ).fetchone()
    strani_kljucevi = db.execute(
        "PRAGMA foreign_key_list(rezervacije)"
    ).fetchall()
    assert prije == poslije == 1
    assert red["grupa_id"] is None
    assert any(
        fk["table"] == "rezervacijske_grupe" and fk["from"] == "grupa_id"
        for fk in strani_kljucevi
    )


def test_paralelni_konfliktni_grupni_upisi_ne_mogu_oba_proci(db):
    pocetak, kraj = _termin()
    ids = _ids(db, "PC1", "PC2")

    def upis(gost):
        try:
            return rezervacije.kreiraj_rezervacijsku_grupu(
                ids, gost, pocetak, kraj, actor=TEST_ACTOR
            )
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        rezultati = list(executor.map(upis, ("Prva", "Druga")))

    assert sum(rezultat is not None for rezultat in rezultati) == 1
    assert db.execute("SELECT COUNT(*) FROM rezervacijske_grupe").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM rezervacije").fetchone()[0] == 2
