from datetime import datetime, timedelta
from typing import List
from database.db import get_db
from models.session_state import SessionState
from models.artikal import Artikal
from constants import CIJENA_MINECRAFT


def izracunaj_iznos_sesije(session: SessionState, cena_po_satu: float) -> float:
    if session.tip == "minecraft":
        elapsed_sati = session.elapsed_sekundi() / 3600
        return round(elapsed_sati * CIJENA_MINECRAFT, 2)
    if session.tip in ("prepaid", "pass1", "pass2"):
        # Iznos je već naplacen pri startu
        return 0.0
    # Neograniceno i sve nepoznate vrijednosti — po satu
    elapsed_sati = session.elapsed_sekundi() / 3600
    return round(elapsed_sati * cena_po_satu, 2)


def naplati_uredjaj(
    uredjaj_ime: str,
    session: SessionState,
    kosarica: List[Artikal],
    cena_po_satu: float,
    smjena_id: int,
    *,
    commit: bool = True
) -> float:
    conn = get_db()
    now = datetime.now().isoformat()

    iznos_sesije = izracunaj_iznos_sesije(session, cena_po_satu)

    # tip_prodaje
    tip_mapa = {
        "neograniceno": "racunar",
        "prepaid": "prepaid",
        "pass1": "pass1",
        "pass2": "pass2",
        "minecraft": "minecraft",
    }
    tip_prodaje = tip_mapa.get(session.tip, "racunar")

    # Zatvori aktivni zapis kreiran pri START-u.
    cursor = conn.execute(
        """UPDATE sesije_log
           SET vreme_kraja = ?, iznos = ?
           WHERE smjena_id = ? AND uredjaj = ? AND vreme_kraja IS NULL""",
        (now, iznos_sesije, smjena_id, uredjaj_ime)
    )
    if cursor.rowcount == 0:
        if commit:
            conn.rollback()
        raise RuntimeError(
            f"Nije pronađena aktivna sesija za uređaj '{uredjaj_ime}' u smjeni {smjena_id}."
        )

    # Upis sesije u pazar_arhiva
    conn.execute(
        """INSERT INTO pazar_arhiva (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (now, uredjaj_ime, iznos_sesije, smjena_id,
         session.vreme_starta.isoformat(), tip_prodaje)
    )

    # Naplata artikala iz košarice
    ukupno_artikli = 0.0
    for artikal in kosarica:
        ukupno_artikli += artikal.ukupno()
        conn.execute(
            """INSERT INTO pazar_arhiva (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (now, uredjaj_ime, artikal.ukupno(), smjena_id,
             session.vreme_starta.isoformat(), "artikal")
        )
        conn.execute(
            """UPDATE prodaja_artikala SET naplaceno = 1
               WHERE uredjaj = ? AND naziv_artikla = ? AND naplaceno = 0 AND smjena_id = ?""",
            (uredjaj_ime, artikal.naziv, smjena_id)
        )

    if commit:
        conn.commit()
    return round(iznos_sesije + ukupno_artikli, 2)


def naplati_sank_kosaricu(stavke: List[Artikal], smjena_id: int) -> float:
    if not stavke:
        return 0.0
    conn = get_db()
    now = datetime.now().isoformat()
    ukupno = 0.0
    for artikal in stavke:
        ukupno += artikal.ukupno()
        conn.execute(
            """INSERT INTO pazar_arhiva (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (now, "Šank", artikal.ukupno(), smjena_id, now, "sank")
        )
    conn.commit()
    return round(ukupno, 2)


def dohvati_pazar_smjene(smjena_id: int) -> dict:
    conn = get_db()
    rows = conn.execute(
        "SELECT uredjaj, iznos, tip_prodaje, vreme FROM pazar_arhiva WHERE smjena_id = ? ORDER BY vreme DESC",
        (smjena_id,)
    ).fetchall()

    ukupno = sum(r["iznos"] for r in rows)
    sank = sum(r["iznos"] for r in rows if r["tip_prodaje"] == "sank")
    artikli = sum(r["iznos"] for r in rows if r["tip_prodaje"] == "artikal")
    racunari = sum(
        r["iznos"] for r in rows if r["tip_prodaje"] not in ("sank", "artikal")
    )

    return {
        "ukupno": round(ukupno, 2),
        "racunari": round(racunari, 2),
        "artikli": round(artikli, 2),
        "sank": round(sank, 2),
        "transakcije": [dict(r) for r in rows],
    }


def dohvati_dashboard_smjene(
    smjena_id: int,
    uskoro_prag_sekundi: int = 15 * 60,
) -> dict:
    """Vrati read-only operativni presjek jedne smjene."""
    conn = get_db()
    pazar = dohvati_pazar_smjene(smjena_id)

    smjena = conn.execute(
        "SELECT pocetak, kraj, radnik FROM smjene WHERE id = ?",
        (smjena_id,),
    ).fetchone()

    uredjaji = conn.execute(
        "SELECT ime FROM uredjaji ORDER BY ime"
    ).fetchall()
    imena_uredjaja = {row["ime"] for row in uredjaji}

    aktivni_redovi = conn.execute(
        """SELECT uredjaj, vreme_starta, tip, limit_sekundi
           FROM sesije_log
           WHERE smjena_id = ? AND vreme_kraja IS NULL
           ORDER BY vreme_starta, id""",
        (smjena_id,),
    ).fetchall()
    aktivni_redovi = [
        row for row in aktivni_redovi if row["uredjaj"] in imena_uredjaja
    ]
    aktivna_imena = {row["uredjaj"] for row in aktivni_redovi}

    prepaid_pass_imena = {
        row["uredjaj"]
        for row in aktivni_redovi
        if row["tip"] in ("prepaid", "pass1", "pass2")
    }

    sada = datetime.now()
    uskoro_isticu = []
    for row in aktivni_redovi:
        if row["limit_sekundi"] is None:
            continue
        try:
            vreme_starta = datetime.fromisoformat(row["vreme_starta"])
        except (TypeError, ValueError):
            continue
        vreme_isteka = vreme_starta + timedelta(
            seconds=int(row["limit_sekundi"])
        )
        preostalo = max(0, int((vreme_isteka - sada).total_seconds()))
        if preostalo <= uskoro_prag_sekundi:
            uskoro_isticu.append({
                "uredjaj": row["uredjaj"],
                "tip": row["tip"] or "neograniceno",
                "vreme_isteka": vreme_isteka.isoformat(),
                "preostalo_sekundi": preostalo,
            })
    uskoro_isticu.sort(
        key=lambda red: (red["preostalo_sekundi"], red["uredjaj"])
    )

    top_artikli = conn.execute(
        """SELECT naziv_artikla,
                  SUM(kolicina) AS kolicina,
                  ROUND(SUM(ukupna_cijena), 2) AS ukupno
           FROM prodaja_artikala
           WHERE smjena_id = ? AND naplaceno = 1
           GROUP BY naziv_artikla
           ORDER BY kolicina DESC, ukupno DESC, naziv_artikla ASC
           LIMIT 5""",
        (smjena_id,),
    ).fetchall()
    top_artikli = [dict(row) for row in top_artikli]
    broj_prodanih_artikala = sum(
        int(row["kolicina"]) for row in top_artikli
    )
    if len(top_artikli) == 5:
        red = conn.execute(
            """SELECT COALESCE(SUM(kolicina), 0) AS kolicina
               FROM prodaja_artikala
               WHERE smjena_id = ? AND naplaceno = 1""",
            (smjena_id,),
        ).fetchone()
        broj_prodanih_artikala = int(red["kolicina"])

    kretanje_pazara = []
    kumulativno = 0.0
    for transakcija in reversed(pazar["transakcije"]):
        kumulativno = round(kumulativno + float(transakcija["iznos"]), 2)
        kretanje_pazara.append({
            "vreme": transakcija["vreme"],
            "ukupno": kumulativno,
        })

    return {
        "smjena_id": smjena_id,
        "pocetak_smjene": smjena["pocetak"] if smjena else None,
        "kraj_smjene": smjena["kraj"] if smjena else None,
        "radnik": smjena["radnik"] if smjena else None,
        "ukupno": pazar["ukupno"],
        "racunari": pazar["racunari"],
        "artikli": pazar["artikli"],
        "sank": pazar["sank"],
        "broj_transakcija": len(pazar["transakcije"]),
        "posljednje_transakcije": pazar["transakcije"][:5],
        "ukupno_uredjaja": len(imena_uredjaja),
        "aktivni_uredjaji": len(aktivna_imena),
        "slobodni_uredjaji": max(0, len(imena_uredjaja) - len(aktivna_imena)),
        "aktivne_prepaid_pass": len(prepaid_pass_imena),
        "uskoro_isticu": uskoro_isticu,
        "broj_prodanih_artikala": broj_prodanih_artikala,
        "top_artikli": top_artikli,
        "kretanje_pazara": kretanje_pazara[-20:],
    }


def dohvati_historiju_sesija(
    *,
    datum_od: str | None = None,
    datum_do: str | None = None,
    uredjaj: str | None = None,
    tip: str | None = None,
    status: str | None = None,
    pretraga: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Vrati filtriranu stranicu sesija bez izmjene finansijskih zapisa."""
    conn = get_db()
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    uslovi = []
    parametri = []
    if datum_od:
        uslovi.append("date(s.vreme_starta) >= date(?)")
        parametri.append(datum_od)
    if datum_do:
        uslovi.append("date(s.vreme_starta) <= date(?)")
        parametri.append(datum_do)
    if uredjaj:
        uslovi.append("s.uredjaj = ?")
        parametri.append(uredjaj)
    if tip:
        uslovi.append("s.tip = ?")
        parametri.append(tip)
    if status == "aktivna":
        uslovi.append("s.vreme_kraja IS NULL")
    elif status == "zavrsena":
        uslovi.append("s.vreme_kraja IS NOT NULL")
    elif status not in (None, "", "sve"):
        raise ValueError("Status mora biti 'aktivna', 'zavrsena' ili 'sve'.")
    if pretraga and pretraga.strip():
        obrazac = f"%{pretraga.strip().lower()}%"
        uslovi.append(
            "(LOWER(COALESCE(s.uredjaj, '')) LIKE ? "
            "OR LOWER(COALESCE(s.tip, '')) LIKE ? "
            "OR LOWER(COALESCE(sm.radnik, '')) LIKE ? "
            "OR CAST(s.id AS TEXT) LIKE ?)"
        )
        parametri.extend([obrazac, obrazac, obrazac, obrazac])

    where_sql = " WHERE " + " AND ".join(uslovi) if uslovi else ""
    from_sql = (
        " FROM sesije_log s "
        "LEFT JOIN smjene sm ON sm.id = s.smjena_id"
    )
    ukupno = conn.execute(
        "SELECT COUNT(*)" + from_sql + where_sql,
        tuple(parametri),
    ).fetchone()[0]

    stranica_sql = (
        "SELECT s.id, s.smjena_id, s.uredjaj, s.vreme_starta, "
        "s.vreme_kraja, s.iznos, s.tip, s.limit_sekundi, sm.radnik"
        + from_sql
        + where_sql
        + " ORDER BY s.vreme_starta DESC, s.id DESC LIMIT ? OFFSET ?"
    )
    redovi = conn.execute(
        """WITH stranica AS ("""
        + stranica_sql
        + """
        )
        SELECT s.*,
               CASE
                   WHEN SUM(CASE WHEN p.tip_prodaje NOT IN ('artikal', 'sank')
                                      THEN 1 ELSE 0 END) > 0
                   THEN COALESCE(SUM(CASE
                       WHEN p.tip_prodaje NOT IN ('artikal', 'sank')
                       THEN p.iznos ELSE 0 END), 0)
                   ELSE COALESCE(s.iznos, 0)
               END AS iznos_racunara,
               COALESCE(SUM(CASE WHEN p.tip_prodaje = 'artikal'
                                 THEN p.iznos ELSE 0 END), 0) AS iznos_artikala
        FROM stranica s
        LEFT JOIN pazar_arhiva p
          ON p.smjena_id = s.smjena_id
         AND p.vreme_starta = s.vreme_starta
        GROUP BY s.id, s.smjena_id, s.uredjaj, s.vreme_starta,
                 s.vreme_kraja, s.iznos, s.tip, s.limit_sekundi, s.radnik
        ORDER BY s.vreme_starta DESC, s.id DESC
        """,
        tuple(parametri) + (limit, offset),
    ).fetchall()

    sada = datetime.now()
    stavke = []
    for row in redovi:
        stavka = dict(row)
        pocetak = _parse_iso_vrijeme(stavka["vreme_starta"])
        kraj = _parse_iso_vrijeme(stavka["vreme_kraja"])
        referentno_vrijeme = kraj or sada
        trajanje = None
        if pocetak is not None:
            trajanje = max(0, int((referentno_vrijeme - pocetak).total_seconds()))

        stavka["status"] = "aktivna" if stavka["vreme_kraja"] is None else "zavrsena"
        stavka["trajanje_sekundi"] = trajanje
        stavka["iznos_racunara"] = round(float(stavka["iznos_racunara"]), 2)
        stavka["iznos_artikala"] = round(float(stavka["iznos_artikala"]), 2)
        stavka["ukupno"] = round(
            stavka["iznos_racunara"] + stavka["iznos_artikala"], 2
        )
        stavka["artikli_detalji_dostupni"] = False
        stavke.append(stavka)

    return {
        "stavke": stavke,
        "ukupno": int(ukupno),
        "limit": limit,
        "offset": offset,
    }


def dohvati_opcije_historije_sesija() -> dict:
    """Vrati historijske uređaje i tipove za filtere."""
    conn = get_db()
    uredjaji = conn.execute(
        """SELECT DISTINCT uredjaj FROM sesije_log
           WHERE uredjaj IS NOT NULL AND TRIM(uredjaj) <> ''
           ORDER BY uredjaj COLLATE NOCASE"""
    ).fetchall()
    tipovi = conn.execute(
        """SELECT DISTINCT tip FROM sesije_log
           WHERE tip IS NOT NULL AND TRIM(tip) <> ''
           ORDER BY tip COLLATE NOCASE"""
    ).fetchall()
    return {
        "uredjaji": [row["uredjaj"] for row in uredjaji],
        "tipovi": [row["tip"] for row in tipovi],
    }


def _parse_iso_vrijeme(vrijednost):
    if not vrijednost:
        return None
    try:
        return datetime.fromisoformat(vrijednost)
    except (TypeError, ValueError):
        return None


def dodaj_artikal_na_uredjaj(
    smjena_id: int,
    uredjaj: str,
    naziv: str,
    kolicina: int,
    cijena: float
):
    conn = get_db()
    now = datetime.now().isoformat()
    ukupna = round(cijena * kolicina, 2)
    conn.execute(
        """INSERT INTO prodaja_artikala (vreme, smjena_id, uredjaj, naziv_artikla, kolicina, ukupna_cijena, naplaceno)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (now, smjena_id, uredjaj, naziv, kolicina, ukupna)
    )
    conn.commit()


def prebaci_sesiju_na_uredjaj(
    smjena_id: int,
    radnik: str,
    izvor_uredjaj: str,
    cilj_uredjaj: str
) -> None:
    conn = get_db()
    now = datetime.now().isoformat()
    try:
        cilj_aktivan = conn.execute(
            """SELECT 1 FROM sesije_log
               WHERE uredjaj = ? AND vreme_kraja IS NULL
               LIMIT 1""",
            (cilj_uredjaj,)
        ).fetchone()
        if cilj_aktivan:
            raise ValueError(f"Uređaj '{cilj_uredjaj}' već ima aktivnu sesiju.")

        cursor = conn.execute(
            """UPDATE sesije_log SET uredjaj = ?
               WHERE smjena_id = ? AND uredjaj = ? AND vreme_kraja IS NULL""",
            (cilj_uredjaj, smjena_id, izvor_uredjaj)
        )
        if cursor.rowcount != 1:
            raise RuntimeError(
                f"Aktivna sesija uređaja '{izvor_uredjaj}' nije pronađena ili nije jedinstvena."
            )

        conn.execute(
            """UPDATE prodaja_artikala SET uredjaj = ?
               WHERE smjena_id = ? AND uredjaj = ? AND naplaceno = 0""",
            (cilj_uredjaj, smjena_id, izvor_uredjaj)
        )
        conn.execute(
            """INSERT INTO logovi (vreme, smjena_id, radnik, uredjaj, akcija)
               VALUES (?, ?, ?, ?, ?)""",
            (now, smjena_id, radnik, izvor_uredjaj,
             f"PRIJENOS → {cilj_uredjaj}")
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def start_sesija(
    uredjaj: str,
    session: SessionState,
    smjena_id: int,
    iznos: float = 0.0
) -> None:
    conn = get_db()
    vreme_starta = session.vreme_starta.isoformat()
    try:
        conn.execute(
            """INSERT INTO sesije_log
               (smjena_id, uredjaj, vreme_starta, vreme_kraja, iznos, tip,
                limit_sekundi)
               VALUES (?, ?, ?, NULL, NULL, ?, ?)""",
            (
                smjena_id,
                uredjaj,
                vreme_starta,
                session.tip,
                session.limit_sekundi,
            )
        )

        if session.tip in ("prepaid", "pass1", "pass2") and iznos > 0:
            conn.execute(
                """INSERT INTO pazar_arhiva
                   (vreme, uredjaj, iznos, smjena_id, vreme_starta, tip_prodaje)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (vreme_starta, uredjaj, iznos, smjena_id,
                 vreme_starta, session.tip)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def dohvati_nenaplacene_artikle(
    smjena_id: int,
    uredjaj: str,
) -> List[Artikal]:
    conn = get_db()
    rows = conn.execute(
        """SELECT naziv_artikla, kolicina, ukupna_cijena
           FROM prodaja_artikala
           WHERE smjena_id = ? AND uredjaj = ? AND naplaceno = 0
           ORDER BY id""",
        (smjena_id, uredjaj)
    ).fetchall()

    agregirani = {}
    for row in rows:
        kolicina = int(row["kolicina"])
        if kolicina <= 0:
            continue
        cijena = round(float(row["ukupna_cijena"]) / kolicina, 10)
        kljuc = (row["naziv_artikla"], cijena)
        agregirani[kljuc] = agregirani.get(kljuc, 0) + kolicina

    return [
        Artikal(naziv, cijena, kolicina)
        for (naziv, cijena), kolicina in agregirani.items()
    ]
