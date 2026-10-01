from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import database.db as db_module
import services.rezervacije as rezervacije
from services.uredjaji import brisi_uredjaj


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_module.zatvori_bazu()
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "rezervacije.sqlite3"))
    db_module.inicijalizuj_bazu()
    conn = db_module.get_db()
    conn.executemany(
        "INSERT INTO uredjaji (ime, cena, tip, grupa) VALUES (?, ?, ?, ?)",
        [("PC1", 2.0, "PC", "Classic"), ("PC2", 2.0, "PC", "Classic")],
    )
    conn.commit()
    yield conn
    db_module.zatvori_bazu()


def _uredjaj(db, ime="PC1"):
    return db.execute("SELECT id FROM uredjaji WHERE ime = ?", (ime,)).fetchone()[0]


def _termin(*, dani=1, sat=10, minuta=0, trajanje=60):
    pocetak = (datetime.now() + timedelta(days=dani)).replace(
        hour=sat, minute=minuta, second=0, microsecond=0
    )
    return pocetak, pocetak + timedelta(minutes=trajanje)


def _kreiraj(db, *, uredjaj="PC1", gost="Marko", pocetak=None, kraj=None, **kwargs):
    if pocetak is None:
        pocetak, kraj = _termin()
    return rezervacije.kreiraj_rezervaciju(
        _uredjaj(db, uredjaj), gost, pocetak, kraj, "Tester", **kwargs
    )


def test_migracija_kreira_tabelu_constraints_i_indekse(db):
    tabela = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("rezervacije",),
    ).fetchone()[0]
    indeksi = {
        red[0]
        for red in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
            ("rezervacije",),
        )
    }

    assert "ON DELETE RESTRICT" in tabela
    assert "CHECK (pocetak < kraj)" in tabela
    assert "idx_rezervacije_uredjaj_termin" in indeksi
    assert "idx_rezervacije_pocetak_status" in indeksi


def test_validna_rezervacija_se_kreira_i_dohvata(db):
    pocetak, kraj = _termin()
    rid = _kreiraj(
        db, gost="Marko M.", pocetak=pocetak, kraj=kraj,
        telefon="061 111 222", napomena="Prozor"
    )

    red = rezervacije.dohvati_rezervaciju(rid)
    assert red["uredjaj"] == "PC1"
    assert red["ime_gosta"] == "Marko M."
    assert red["status"] == "rezervisano"
    assert red["kreirao_radnik"] == "Tester"


@pytest.mark.parametrize("gost", ["", "   "])
def test_ime_gosta_je_obavezno(db, gost):
    pocetak, kraj = _termin()
    with pytest.raises(ValueError, match="Ime gosta"):
        _kreiraj(db, gost=gost, pocetak=pocetak, kraj=kraj)


def test_pocetak_mora_biti_prije_kraja(db):
    pocetak, kraj = _termin()
    with pytest.raises(ValueError, match="prije kraja"):
        _kreiraj(db, pocetak=kraj, kraj=pocetak)


def test_termin_u_proslosti_se_odbija(db):
    kraj = datetime.now() - timedelta(hours=1)
    with pytest.raises(ValueError, match="prošlosti"):
        _kreiraj(db, pocetak=kraj - timedelta(hours=1), kraj=kraj)


def test_potpuno_preklapanje_se_odbija(db):
    pocetak, kraj = _termin()
    _kreiraj(db, pocetak=pocetak, kraj=kraj)
    with pytest.raises(ValueError, match="preklapa"):
        _kreiraj(
            db, gost="Drugi", pocetak=pocetak + timedelta(minutes=10),
            kraj=kraj - timedelta(minutes=10)
        )


def test_djelimicno_preklapanje_se_odbija(db):
    pocetak, kraj = _termin()
    _kreiraj(db, pocetak=pocetak, kraj=kraj)
    with pytest.raises(ValueError, match="preklapa"):
        _kreiraj(
            db, gost="Drugi", pocetak=kraj - timedelta(minutes=15),
            kraj=kraj + timedelta(minutes=30)
        )


def test_istovremeni_konfliktni_upisi_ne_mogu_obje_proci(db):
    pocetak, kraj = _termin()

    def upis(gost):
        try:
            return _kreiraj(db, gost=gost, pocetak=pocetak, kraj=kraj)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        rezultati = list(executor.map(upis, ("Prvi", "Drugi")))

    assert sum(rezultat is not None for rezultat in rezultati) == 1
    assert db.execute("SELECT COUNT(*) FROM rezervacije").fetchone()[0] == 1


def test_dodir_krajnjih_tacaka_je_dozvoljen(db):
    pocetak, kraj = _termin()
    _kreiraj(db, pocetak=pocetak, kraj=kraj)
    drugi = _kreiraj(db, gost="Drugi", pocetak=kraj, kraj=kraj + timedelta(hours=1))
    assert rezervacije.dohvati_rezervaciju(drugi) is not None


def test_isti_termin_na_drugom_uredjaju_je_dozvoljen(db):
    pocetak, kraj = _termin()
    _kreiraj(db, pocetak=pocetak, kraj=kraj)
    drugi = _kreiraj(db, uredjaj="PC2", pocetak=pocetak, kraj=kraj)
    assert rezervacije.dohvati_rezervaciju(drugi)["uredjaj"] == "PC2"


def test_otkazana_rezervacija_ne_blokira_termin(db):
    pocetak, kraj = _termin()
    rid = _kreiraj(db, pocetak=pocetak, kraj=kraj)
    rezervacije.otkazi_rezervaciju(rid, "Tester")
    novi = _kreiraj(db, gost="Drugi", pocetak=pocetak, kraj=kraj)
    assert novi != rid


def test_stigao_status_i_dalje_blokira_termin(db):
    pocetak, kraj = _termin()
    rid = _kreiraj(db, pocetak=pocetak, kraj=kraj)
    rezervacije.promijeni_status_rezervacije(rid, "stigao", "Tester")
    with pytest.raises(ValueError, match="preklapa"):
        _kreiraj(db, gost="Drugi", pocetak=pocetak, kraj=kraj)


def test_izmjena_iskljucuje_vlastiti_id_ali_otkriva_drugi_konflikt(db):
    p1, k1 = _termin(sat=10)
    p2, k2 = _termin(sat=12)
    rid = _kreiraj(db, pocetak=p1, kraj=k1)
    _kreiraj(db, gost="Drugi", pocetak=p2, kraj=k2)
    rezervacije.izmijeni_rezervaciju(
        rid, _uredjaj(db), "Marko", p1, k1, "Tester"
    )
    with pytest.raises(ValueError, match="preklapa"):
        rezervacije.izmijeni_rezervaciju(
            rid, _uredjaj(db), "Marko", p2, k2, "Tester"
        )


def test_dozvoljene_statusne_tranzicije(db):
    rid = _kreiraj(db)
    rezervacije.promijeni_status_rezervacije(rid, "stigao", "Ana")
    rezervacije.promijeni_status_rezervacije(rid, "zavrseno", "Ana")
    assert rezervacije.dohvati_rezervaciju(rid)["status"] == "zavrseno"


@pytest.mark.parametrize("novi_status", ["zavrseno", "rezervisano", "nepoznato"])
def test_nedozvoljena_statusna_tranzicija_se_odbija(db, novi_status):
    rid = _kreiraj(db)
    with pytest.raises(ValueError):
        rezervacije.promijeni_status_rezervacije(rid, novi_status, "Tester")


def test_zavrsena_rezervacija_ostaje_u_historiji(db):
    rid = _kreiraj(db)
    rezervacije.promijeni_status_rezervacije(rid, "stigao", "Tester")
    rezervacije.promijeni_status_rezervacije(rid, "zavrseno", "Tester")
    assert [red["id"] for red in rezervacije.dohvati_rezervacije()] == [rid]


def test_filteri_po_datumu_uredjaju_statusu_i_pretrazi(db):
    pocetak, kraj = _termin(dani=2, sat=14)
    rid = _kreiraj(
        db, uredjaj="PC2", gost="Jasmin Alić", pocetak=pocetak, kraj=kraj,
        telefon="062123"
    )
    rezultat = rezervacije.dohvati_rezervacije(
        datum=pocetak.date(), uredjaj_id=_uredjaj(db, "PC2"),
        status="rezervisano", pretraga="Jasmin"
    )
    assert [red["id"] for red in rezultat] == [rid]
    assert rezervacije.dohvati_rezervacije(datum=(pocetak + timedelta(days=1)).date()) == []


def test_najbliza_rezervacija_po_uredjaju(db):
    kasnije, kasnije_kraj = _termin(sat=14)
    ranije, ranije_kraj = _termin(sat=10)
    _kreiraj(db, gost="Kasnije", pocetak=kasnije, kraj=kasnije_kraj)
    raniji_id = _kreiraj(db, gost="Ranije", pocetak=ranije, kraj=ranije_kraj)

    red = rezervacije.dohvati_narednu_rezervaciju_uredjaja(
        _uredjaj(db), sada=ranije - timedelta(hours=1)
    )
    mapa = rezervacije.dohvati_naredne_rezervacije_uredjaja(
        [_uredjaj(db), _uredjaj(db, "PC2")], sada=ranije - timedelta(hours=1)
    )
    assert red["id"] == raniji_id
    assert mapa[_uredjaj(db)]["id"] == raniji_id
    assert _uredjaj(db, "PC2") not in mapa


def test_svaka_izmjena_upisuje_audit_bez_telefona(db):
    pocetak, kraj = _termin()
    rid = _kreiraj(db, pocetak=pocetak, kraj=kraj, telefon="061-TAJNO")
    rezervacije.izmijeni_rezervaciju(
        rid, _uredjaj(db), "Marko", pocetak, kraj, "Ana", telefon="062-TAJNO"
    )
    rezervacije.promijeni_status_rezervacije(rid, "stigao", "Ana")
    logovi = db.execute(
        "SELECT radnik, uredjaj, akcija FROM logovi ORDER BY id"
    ).fetchall()
    assert len(logovi) == 3
    assert logovi[-1]["radnik"] == "Ana"
    assert logovi[-1]["uredjaj"] == "PC1"
    assert all("TAJNO" not in red["akcija"] for red in logovi)


def test_kreiranje_se_rollbackuje_ako_audit_padne(db, monkeypatch):
    def greska(*_args, **_kwargs):
        raise RuntimeError("audit nije dostupan")

    monkeypatch.setattr(rezervacije, "upisi_log_u_transakciji", greska)
    with pytest.raises(RuntimeError, match="audit"):
        _kreiraj(db)
    assert db.execute("SELECT COUNT(*) FROM rezervacije").fetchone()[0] == 0


def test_status_se_rollbackuje_ako_audit_padne(db, monkeypatch):
    rid = _kreiraj(db)
    monkeypatch.setattr(
        rezervacije, "upisi_log_u_transakciji",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit")),
    )
    with pytest.raises(RuntimeError):
        rezervacije.promijeni_status_rezervacije(rid, "stigao", "Tester")
    assert rezervacije.dohvati_rezervaciju(rid)["status"] == "rezervisano"


def test_uredjaj_sa_bilo_kojom_rezervacijom_ne_moze_biti_obrisan(db):
    uid = _uredjaj(db)
    rid = _kreiraj(db)
    with pytest.raises(ValueError, match="aktivnu rezervaciju"):
        brisi_uredjaj(uid)
    rezervacije.otkazi_rezervaciju(rid, "Tester")
    with pytest.raises(ValueError, match="historiju rezervacija"):
        brisi_uredjaj(uid)
    assert db.execute("SELECT 1 FROM uredjaji WHERE id = ?", (uid,)).fetchone()
