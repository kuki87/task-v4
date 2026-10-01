from __future__ import annotations

from datetime import date, datetime, time, timedelta

from database.db import get_db


def dohvati_izvjestaj_perioda(datum_od, datum_do) -> dict:
    """Vrati read-only poslovne agregate za uključivi kalendarski period."""
    od = _datum(datum_od, "datum_od")
    do = _datum(datum_do, "datum_do")
    if od > do:
        raise ValueError("Datum OD ne može biti poslije datuma DO.")

    pocetak = datetime.combine(od, time.min)
    kraj_iskljucivo = datetime.combine(do + timedelta(days=1), time.min)
    granice = (pocetak.isoformat(), kraj_iskljucivo.isoformat())
    conn = get_db()

    finansije = conn.execute(
        """SELECT
               COALESCE(SUM(iznos), 0) AS ukupno,
               COALESCE(SUM(CASE
                   WHEN tip_prodaje = 'artikal' THEN iznos ELSE 0 END), 0) AS artikli,
               COALESCE(SUM(CASE
                   WHEN tip_prodaje = 'sank' THEN iznos ELSE 0 END), 0) AS sank,
               COALESCE(SUM(CASE
                   WHEN tip_prodaje IS NULL
                     OR tip_prodaje NOT IN ('artikal', 'sank')
                   THEN iznos ELSE 0 END), 0) AS racunari
           FROM pazar_arhiva
           WHERE vreme >= ? AND vreme < ?""",
        granice,
    ).fetchone()

    smjena_redovi = conn.execute(
        """SELECT s.id, s.radnik, s.pocetak, s.kraj,
                  COALESCE(SUM(p.iznos), s.pazar, 0) AS pazar
           FROM smjene s
           LEFT JOIN pazar_arhiva p ON p.smjena_id = s.id
           WHERE s.pocetak >= ? AND s.pocetak < ?
           GROUP BY s.id, s.radnik, s.pocetak, s.kraj, s.pazar
           ORDER BY s.pocetak DESC, s.id DESC""",
        granice,
    ).fetchall()
    smjene = []
    for row in smjena_redovi:
        stavka = dict(row)
        pocetak_smjene = _vrijeme(stavka["pocetak"])
        kraj_smjene = _vrijeme(stavka["kraj"])
        stavka["status"] = "otvorena" if kraj_smjene is None else "zavrsena"
        stavka["trajanje_sekundi"] = (
            max(0, int((kraj_smjene - pocetak_smjene).total_seconds()))
            if pocetak_smjene is not None and kraj_smjene is not None
            else None
        )
        stavka["pazar"] = round(float(stavka["pazar"] or 0), 2)
        smjene.append(stavka)

    sesije_red = conn.execute(
        """SELECT
               COUNT(*) AS ukupno,
               COALESCE(SUM(CASE WHEN vreme_kraja IS NULL THEN 1 ELSE 0 END), 0)
                   AS aktivne,
               COALESCE(SUM(CASE WHEN vreme_kraja IS NOT NULL THEN 1 ELSE 0 END), 0)
                   AS zavrsene,
               COALESCE(SUM(CASE WHEN COALESCE(tip, 'neograniceno') = 'neograniceno'
                                 THEN 1 ELSE 0 END), 0) AS regularne,
               COALESCE(SUM(CASE WHEN tip = 'prepaid' THEN 1 ELSE 0 END), 0)
                   AS prepaid,
               COALESCE(SUM(CASE WHEN tip = 'pass1' THEN 1 ELSE 0 END), 0)
                   AS pass1,
               COALESCE(SUM(CASE WHEN tip = 'pass2' THEN 1 ELSE 0 END), 0)
                   AS pass2,
               COALESCE(SUM(CASE WHEN tip = 'minecraft' THEN 1 ELSE 0 END), 0)
                   AS minecraft,
               COALESCE(SUM(CASE WHEN vreme_kraja IS NOT NULL THEN
                   MAX(0, CAST(ROUND(
                       (julianday(vreme_kraja) - julianday(vreme_starta)) * 86400
                   ) AS INTEGER)) ELSE 0 END), 0) AS trajanje_zavrsenih
           FROM sesije_log
           WHERE vreme_starta >= ? AND vreme_starta < ?""",
        granice,
    ).fetchone()

    prosjek_sesije = conn.execute(
        """WITH zavrsene AS (
               SELECT id, smjena_id, vreme_starta, iznos
               FROM sesije_log
               WHERE vreme_starta >= ? AND vreme_starta < ?
                 AND vreme_kraja IS NOT NULL
           ), prihodi AS (
               SELECT z.id,
                      CASE WHEN SUM(CASE
                               WHEN p.id IS NOT NULL AND (
                                    p.tip_prodaje IS NULL
                                    OR p.tip_prodaje NOT IN ('artikal', 'sank'))
                               THEN 1 ELSE 0 END) > 0
                           THEN COALESCE(SUM(CASE
                               WHEN p.id IS NOT NULL AND (
                                    p.tip_prodaje IS NULL
                                    OR p.tip_prodaje NOT IN ('artikal', 'sank'))
                               THEN p.iznos ELSE 0 END), 0)
                           ELSE COALESCE(z.iznos, 0) END
                      + COALESCE(SUM(CASE WHEN p.tip_prodaje = 'artikal'
                                          THEN p.iznos ELSE 0 END), 0) AS ukupno
               FROM zavrsene z
               LEFT JOIN pazar_arhiva p
                 ON p.smjena_id = z.smjena_id
                AND p.vreme_starta = z.vreme_starta
               GROUP BY z.id, z.iznos
           )
           SELECT COALESCE(AVG(ukupno), 0) AS prosjek FROM prihodi""",
        granice,
    ).fetchone()

    top_sesije = conn.execute(
        """SELECT uredjaj, COUNT(*) AS broj_sesija
           FROM sesije_log
           WHERE vreme_starta >= ? AND vreme_starta < ?
           GROUP BY uredjaj
           ORDER BY broj_sesija DESC, uredjaj COLLATE NOCASE ASC
           LIMIT 10""",
        granice,
    ).fetchall()
    top_prihod = conn.execute(
        """SELECT uredjaj, ROUND(SUM(iznos), 2) AS prihod
           FROM pazar_arhiva
           WHERE vreme >= ? AND vreme < ?
             AND (tip_prodaje IS NULL OR tip_prodaje <> 'sank')
           GROUP BY uredjaj
           ORDER BY prihod DESC, uredjaj COLLATE NOCASE ASC
           LIMIT 10""",
        granice,
    ).fetchall()

    artikli_redovi = conn.execute(
        """SELECT naziv_artikla,
                  COALESCE(SUM(kolicina), 0) AS kolicina,
                  ROUND(COALESCE(SUM(ukupna_cijena), 0), 2) AS prihod
           FROM prodaja_artikala
           WHERE vreme >= ? AND vreme < ? AND naplaceno = 1
           GROUP BY naziv_artikla""",
        granice,
    ).fetchall()
    artikli = [
        {
            "naziv": row["naziv_artikla"],
            "kolicina": int(row["kolicina"]),
            "prihod": round(float(row["prihod"]), 2),
        }
        for row in artikli_redovi
    ]
    top_artikli_kolicina = sorted(
        artikli,
        key=lambda red: (-red["kolicina"], -red["prihod"], red["naziv"].lower()),
    )[:10]
    top_artikli_prihod = sorted(
        artikli,
        key=lambda red: (-red["prihod"], -red["kolicina"], red["naziv"].lower()),
    )[:10]

    trend = _dohvati_trend(conn, od, do, granice)

    ukupno = round(float(finansije["ukupno"]), 2)
    broj_zavrsenih_smjena = sum(1 for smjena in smjene if smjena["kraj"])
    broj_zavrsenih_sesija = int(sesije_red["zavrsene"])
    trajanje_zavrsenih = int(sesije_red["trajanje_zavrsenih"])

    return {
        "period": {
            "datum_od": od.isoformat(),
            "datum_do": do.isoformat(),
            "pocetak": granice[0],
            "kraj_iskljucivo": granice[1],
        },
        "sazetak": {
            "ukupno": ukupno,
            "racunari": round(float(finansije["racunari"]), 2),
            "artikli": round(float(finansije["artikli"]), 2),
            "sank": round(float(finansije["sank"]), 2),
            "broj_zavrsenih_smjena": broj_zavrsenih_smjena,
            "broj_sesija": int(sesije_red["ukupno"]),
            "prosjek_po_smjeni": round(
                ukupno / broj_zavrsenih_smjena, 2
            ) if broj_zavrsenih_smjena else 0.0,
            "prosjek_po_zavrsenoj_sesiji": round(
                float(prosjek_sesije["prosjek"]), 2
            ) if broj_zavrsenih_sesija else 0.0,
        },
        "sesije": {
            "ukupno": int(sesije_red["ukupno"]),
            "aktivne": int(sesije_red["aktivne"]),
            "zavrsene": broj_zavrsenih_sesija,
            "tipovi": {
                "neograniceno": int(sesije_red["regularne"]),
                "prepaid": int(sesije_red["prepaid"]),
                "pass1": int(sesije_red["pass1"]),
                "pass2": int(sesije_red["pass2"]),
                "minecraft": int(sesije_red["minecraft"]),
            },
            "ukupno_trajanje_zavrsenih": trajanje_zavrsenih,
            "prosjek_trajanja_zavrsenih": (
                round(trajanje_zavrsenih / broj_zavrsenih_sesija)
                if broj_zavrsenih_sesija else 0
            ),
            "top_uredjaji_po_sesijama": [dict(row) for row in top_sesije],
            "top_uredjaji_po_prihodu": [dict(row) for row in top_prihod],
        },
        "artikli": {
            "ukupna_kolicina": sum(red["kolicina"] for red in artikli),
            "ukupan_prihod_po_evidenciji": round(
                sum(red["prihod"] for red in artikli), 2
            ),
            "top_po_kolicini": top_artikli_kolicina,
            "top_po_prihodu": top_artikli_prihod,
        },
        "smjene": smjene,
        "trend": trend,
        "ogranicenja": [
            "Šank čuva samo zbirni iznos, bez naziva i količine artikala.",
            "Imenovani artikli su filtrirani po vremenu dodavanja na uređaj, ne po vremenu naplate.",
            "Prihod uređaja prati uređaj zapisan na transakciji; transfer može zadržati raniju oznaku.",
        ],
    }


def _dohvati_trend(conn, datum_od: date, datum_do: date, granice: tuple) -> dict:
    jedan_dan = datum_od == datum_do
    format_sql = "%H" if jedan_dan else "%Y-%m-%d"
    redovi = conn.execute(
        """SELECT strftime(?, vreme) AS segment,
                  ROUND(COALESCE(SUM(iznos), 0), 2) AS iznos
           FROM pazar_arhiva
           WHERE vreme >= ? AND vreme < ?
           GROUP BY segment
           ORDER BY segment""",
        (format_sql, *granice),
    ).fetchall()
    vrijednosti = {
        row["segment"]: round(float(row["iznos"]), 2)
        for row in redovi if row["segment"] is not None
    }

    if jedan_dan:
        tacke = [
            {"oznaka": f"{sat:02d}:00", "iznos": vrijednosti.get(f"{sat:02d}", 0.0)}
            for sat in range(24)
        ]
        return {"granularnost": "sat", "tacke": tacke}

    tacke = []
    trenutni = datum_od
    while trenutni <= datum_do:
        kljuc = trenutni.isoformat()
        tacke.append({"oznaka": kljuc, "iznos": vrijednosti.get(kljuc, 0.0)})
        trenutni += timedelta(days=1)
    return {"granularnost": "dan", "tacke": tacke}


def _datum(vrijednost, naziv: str) -> date:
    if isinstance(vrijednost, datetime):
        return vrijednost.date()
    if isinstance(vrijednost, date):
        return vrijednost
    if isinstance(vrijednost, str):
        try:
            return date.fromisoformat(vrijednost)
        except ValueError as e:
            raise ValueError(f"{naziv} mora biti datum u formatu YYYY-MM-DD.") from e
    raise ValueError(f"{naziv} mora biti datum u formatu YYYY-MM-DD.")


def _vrijeme(vrijednost):
    if not vrijednost:
        return None
    try:
        return datetime.fromisoformat(vrijednost)
    except (TypeError, ValueError):
        return None
