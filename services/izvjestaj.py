import os
from datetime import datetime
from typing import List
from database.db import get_db
from services.logger import log
from constants import BASE_DIR

IZVJESTAJI_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Izvještaji")


def _iznos(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _vrijeme(v, duzina: int = 19) -> str:
    if not isinstance(v, str) or not v:
        return "—"
    return v[:duzina].replace("T", " ")


def _jedinstvena_putanja(putanja: str) -> str:
    if not os.path.exists(putanja):
        return putanja
    koren, ext = os.path.splitext(putanja)
    n = 1
    while os.path.exists(f"{koren}_{n}{ext}"):
        n += 1
    return f"{koren}_{n}{ext}"


def _registruj_font() -> tuple:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    win_fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    kandidati = [
        (os.path.join(BASE_DIR, "fonts"), "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
        (win_fonts, "arial.ttf", "arialbd.ttf"),
        (win_fonts, "segoeui.ttf", "segoeuib.ttf"),
    ]
    for folder, fajl, fajl_bold in kandidati:
        putanja = os.path.join(folder, fajl)
        if not os.path.exists(putanja):
            continue
        try:
            pdfmetrics.registerFont(TTFont("Izv", putanja))
        except Exception as e:
            log.error(f"Font {fajl} nije registrovan: {e}")
            continue
        putanja_bold = os.path.join(folder, fajl_bold)
        if os.path.exists(putanja_bold):
            try:
                pdfmetrics.registerFont(TTFont("Izv-Bold", putanja_bold))
                return "Izv", "Izv-Bold"
            except Exception as e:
                log.error(f"Font {fajl_bold} nije registrovan: {e}")
        return "Izv", "Izv"

    log.error(
        "Nijedan Unicode font nije pronađen, PDF će izgubiti slova Č, ć, Đ, đ."
    )
    return "Helvetica", "Helvetica-Bold"


def _osiguraj_folder():
    os.makedirs(IZVJESTAJI_DIR, exist_ok=True)


def generiši_tekstualni(smjena_id: int, podaci: dict) -> str:
    """Kreira tekstualni izvještaj, sprema ga u Izvještaji/ i vraća sadržaj."""
    podaci = podaci or {}
    conn = get_db()
    smjena = conn.execute(
        "SELECT * FROM smjene WHERE id = ?", (smjena_id,)
    ).fetchone()

    transakcije = conn.execute(
        """SELECT vreme, uredjaj, iznos, tip_prodaje
           FROM pazar_arhiva WHERE smjena_id = ? ORDER BY vreme""",
        (smjena_id,)
    ).fetchall()

    linija = "=" * 50
    tekst = []
    tekst.append(linija)
    tekst.append("     CAFFE & GAMING ZONE — IZVJEŠTAJ SMJENE")
    tekst.append(linija)

    if smjena:
        tekst.append(f"Smjena ID : {smjena_id}")
        tekst.append(f"Radnik    : {smjena['radnik'] or '—'}")
        tekst.append(f"Početak   : {_vrijeme(smjena['pocetak'])}")
        kraj = smjena['kraj']
        if kraj:
            tekst.append(f"Kraj      : {_vrijeme(kraj)}")
        else:
            tekst.append("Kraj      : — (smjena nije zatvorena)")
        tekst.append(f"Pazar     : {_iznos(smjena['pazar']):.2f} KM")
    else:
        log.error(f"Izvještaj tražen za nepostojeću smjenu id={smjena_id}.")
        tekst.append(f"Smjena ID : {smjena_id}")
        tekst.append("UPOZORENJE: smjena sa ovim ID-om ne postoji u bazi!")

    tekst.append("")
    tekst.append("--- TRANSAKCIJE ---")

    ukupno_racunari = 0.0
    ukupno_sank = 0.0
    ukupno_artikli = 0.0

    for t in transakcije:
        iznos = _iznos(t["iznos"])
        vreme = _vrijeme(t["vreme"])
        uredjaj = t["uredjaj"] or "—"
        tip = t["tip_prodaje"] or "—"
        tekst.append(f"{vreme}  {uredjaj:<12}  {tip:<12}  {iznos:.2f} KM")
        if tip == "sank":
            ukupno_sank += iznos
        elif tip == "artikal":
            ukupno_artikli += iznos
        else:
            ukupno_racunari += iznos

    tekst.append("")
    tekst.append(linija)
    tekst.append(f"Računari  : {ukupno_racunari:.2f} KM")
    tekst.append(f"Artikli   : {ukupno_artikli:.2f} KM")
    tekst.append(f"Šank      : {ukupno_sank:.2f} KM")
    tekst.append(f"UKUPNO    : {(ukupno_racunari + ukupno_sank + ukupno_artikli):.2f} KM")
    tekst.append(linija)

    if podaci.get("preneseni_racunari"):
        tekst.append("")
        tekst.append("--- PREKINUTE AKTIVNE SESIJE (NENAPLAĆENO) ---")
        for r in podaci["preneseni_racunari"]:
            tekst.append(f"  • {r}")
        tekst.append("  Vrijeme ovih sesija NIJE uključeno u iznose iznad.")

    tekst.append("")
    tekst.append(f"Generisano: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

    sadrzaj = "\n".join(tekst)

    try:
        _osiguraj_folder()
        txt_file = _jedinstvena_putanja(os.path.join(
            IZVJESTAJI_DIR,
            f"izvjestaj_smjena_{smjena_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        ))
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(sadrzaj)
    except OSError as e:
        log.error(f"Izvještaj smjene {smjena_id} nije snimljen na disk: {e}")

    return sadrzaj


def generiši_pdf(smjena_id: int, podaci: dict) -> str:
    podaci = podaci or {}
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.units import cm
    except ImportError as e:
        log.error(f"reportlab nije dostupan, PDF izvještaj preskočen: {e}")
        return ""

    font, font_bold = _registruj_font()

    conn = get_db()
    smjena = conn.execute("SELECT * FROM smjene WHERE id = ?", (smjena_id,)).fetchone()
    transakcije = conn.execute(
        "SELECT vreme, uredjaj, iznos, tip_prodaje FROM pazar_arhiva WHERE smjena_id = ? ORDER BY vreme",
        (smjena_id,)
    ).fetchall()

    try:
        _osiguraj_folder()
        filename = _jedinstvena_putanja(os.path.join(
            IZVJESTAJI_DIR,
            f"izvjestaj_smjena_{smjena_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        ))
        doc = SimpleDocTemplate(filename, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)

        styles = getSampleStyleSheet()
        styles["Normal"].fontName = font
        styles["Title"].fontName = font_bold
        styles["Heading2"].fontName = font_bold
        styles["Heading3"].fontName = font_bold
        story = []

        # Naslov
        naslov_style = ParagraphStyle("Naslov", parent=styles["Title"], fontSize=16, spaceAfter=6)
        story.append(Paragraph("CAFFE & GAMING ZONE", naslov_style))
        story.append(Paragraph("Izvještaj smjene", styles["Heading2"]))
        story.append(Spacer(1, 0.5*cm))

        # Info smjene
        if smjena:
            info_data = [
                ["Smjena ID:", str(smjena_id)],
                ["Radnik:", smjena["radnik"] or "—"],
                ["Početak:", _vrijeme(smjena["pocetak"])],
                ["Pazar:", f"{_iznos(smjena['pazar']):.2f} KM"],
            ]
            if smjena["kraj"]:
                info_data.insert(3, ["Kraj:", _vrijeme(smjena["kraj"])])

            t = Table(info_data, colWidths=[4*cm, 10*cm])
            t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTNAME", (0, 0), (0, -1), font_bold),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.5*cm))
        else:
            log.error(f"PDF izvještaj tražen za nepostojeću smjenu id={smjena_id}.")
            story.append(Paragraph(
                "UPOZORENJE: smjena sa ovim ID-om ne postoji u bazi!", styles["Normal"]
            ))
            story.append(Spacer(1, 0.5*cm))

        # Tabela transakcija
        story.append(Paragraph("Transakcije", styles["Heading3"]))
        ukupno_racunari = 0.0
        ukupno_sank = 0.0
        ukupno_artikli = 0.0
        if transakcije:
            zaglavlje = [["Vrijeme", "Uređaj", "Tip", "Iznos (KM)"]]
            redovi = []
            for t in transakcije:
                iznos = _iznos(t["iznos"])
                tip = t["tip_prodaje"] or "—"
                if tip == "sank":
                    ukupno_sank += iznos
                elif tip == "artikal":
                    ukupno_artikli += iznos
                else:
                    ukupno_racunari += iznos
                redovi.append([_vrijeme(t["vreme"], 16), t["uredjaj"] or "—", tip, f"{iznos:.2f}"])

            tabela_data = zaglavlje + redovi
            tabela = Table(tabela_data, colWidths=[4.5*cm, 4*cm, 4*cm, 3*cm])
            tabela.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTNAME", (0, 0), (-1, 0), font_bold),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(tabela)

        story.append(Spacer(1, 0.4*cm))

        # Rekapitulacija, ista podjela kao u tekstualnom izvještaju
        rekap = Table([
            ["Računari:", f"{ukupno_racunari:.2f} KM"],
            ["Artikli:", f"{ukupno_artikli:.2f} KM"],
            ["Šank:", f"{ukupno_sank:.2f} KM"],
            ["UKUPNO:", f"{(ukupno_racunari + ukupno_artikli + ukupno_sank):.2f} KM"],
        ], colWidths=[4*cm, 4*cm])
        rekap.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTNAME", (0, -1), (-1, -1), font_bold),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(rekap)
        story.append(Spacer(1, 0.3*cm))

        if podaci.get("preneseni_racunari"):
            story.append(Paragraph("Prekinute aktivne sesije (nenaplaćeno):", styles["Heading3"]))
            for r in podaci["preneseni_racunari"]:
                story.append(Paragraph(f"• {r}", styles["Normal"]))
            story.append(Paragraph(
                "Vrijeme ovih sesija NIJE uključeno u iznose iznad.", styles["Normal"]
            ))

        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(
            f"Generisano: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
            styles["Normal"]
        ))

        doc.build(story)
    except Exception as e:
        log.error(f"PDF izvještaj smjene {smjena_id} nije generisan: {e}")
        return ""
    return filename


def generisi_txt_perioda(datum_od: str, datum_do: str, podaci: dict = None) -> str:
    """Snimi novi tekstualni izvještaj perioda i vrati putanju fajla."""
    if podaci is None:
        from services.izvjestaj_perioda import dohvati_izvjestaj_perioda
        podaci = dohvati_izvjestaj_perioda(datum_od, datum_do)

    sadrzaj = _sadrzaj_perioda(podaci)
    _osiguraj_folder()
    putanja = _jedinstvena_putanja(os.path.join(
        IZVJESTAJI_DIR,
        f"izvjestaj_{datum_od}_{datum_do}.txt",
    ))
    with open(putanja, "w", encoding="utf-8") as fajl:
        fajl.write(sadrzaj)
    return putanja


def generisi_pdf_perioda(datum_od: str, datum_do: str, podaci: dict = None) -> str:
    """Snimi novi PDF izvještaj perioda; stari izvještaj smjene ostaje odvojen."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as e:
        log.error(f"reportlab nije dostupan, PDF izvještaj perioda preskočen: {e}")
        return ""

    if podaci is None:
        from services.izvjestaj_perioda import dohvati_izvjestaj_perioda
        podaci = dohvati_izvjestaj_perioda(datum_od, datum_do)

    font, font_bold = _registruj_font()
    _osiguraj_folder()
    putanja = _jedinstvena_putanja(os.path.join(
        IZVJESTAJI_DIR,
        f"izvjestaj_{datum_od}_{datum_do}.pdf",
    ))

    try:
        doc = SimpleDocTemplate(
            putanja,
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )
        styles = getSampleStyleSheet()
        for ime in ("Normal", "Title", "Heading2", "Heading3"):
            styles[ime].fontName = font_bold if ime != "Normal" else font

        period = podaci["period"]
        sazetak = podaci["sazetak"]
        sesije = podaci["sesije"]
        story = [
            Paragraph("CAFFE & GAMING ZONE", styles["Title"]),
            Paragraph("Poslovni izvještaj perioda", styles["Heading2"]),
            Paragraph(
                f"Period: {period['datum_od']} — {period['datum_do']}",
                styles["Normal"],
            ),
            Spacer(1, 0.35 * cm),
        ]

        summary_data = [
            ["Ukupno", "Računari", "Artikli", "Šank"],
            [
                f"{sazetak['ukupno']:.2f} KM",
                f"{sazetak['racunari']:.2f} KM",
                f"{sazetak['artikli']:.2f} KM",
                f"{sazetak['sank']:.2f} KM",
            ],
            ["Završene smjene", "Sesije", "Prosjek / smjena", "Prosjek / sesija"],
            [
                str(sazetak["broj_zavrsenih_smjena"]),
                str(sazetak["broj_sesija"]),
                f"{sazetak['prosjek_po_smjeni']:.2f} KM",
                f"{sazetak['prosjek_po_zavrsenoj_sesiji']:.2f} KM",
            ],
        ]
        summary = Table(summary_data, colWidths=[4.2 * cm] * 4)
        summary.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
            ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#e5e7eb")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTNAME", (0, 0), (-1, 0), font_bold),
            ("FONTNAME", (0, 2), (-1, 2), font_bold),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([summary, Spacer(1, 0.35 * cm)])

        tipovi = sesije["tipovi"]
        story.append(Paragraph("Sesije", styles["Heading3"]))
        story.append(Paragraph(
            "Regular: {neograniceno} · Prepaid: {prepaid} · Pass1: {pass1} · "
            "Pass2: {pass2} · Minecraft: {minecraft} · Aktivne: {aktivne}".format(
                aktivne=sesije["aktivne"], **tipovi
            ),
            styles["Normal"],
        ))
        story.append(Spacer(1, 0.3 * cm))

        if podaci["artikli"]["top_po_kolicini"]:
            story.append(Paragraph("Top artikli po količini", styles["Heading3"]))
            redovi = [["Artikal", "Količina", "Prihod"]] + [
                [a["naziv"], str(a["kolicina"]), f"{a['prihod']:.2f} KM"]
                for a in podaci["artikli"]["top_po_kolicini"][:10]
            ]
            story.append(_pdf_tabela(redovi, [8 * cm, 3 * cm, 4 * cm], font, font_bold))
            story.append(Spacer(1, 0.3 * cm))

        story.append(Paragraph("Smjene", styles["Heading3"]))
        smjene = [["ID", "Radnik", "Početak", "Kraj / status", "Pazar"]]
        for s in podaci["smjene"]:
            smjene.append([
                str(s["id"]),
                s["radnik"] or "—",
                _vrijeme(s["pocetak"], 16),
                _vrijeme(s["kraj"], 16) if s["kraj"] else "Otvorena",
                f"{s['pazar']:.2f} KM",
            ])
        story.append(_pdf_tabela(
            smjene, [1.2 * cm, 3.5 * cm, 4.5 * cm, 4.5 * cm, 2.7 * cm], font, font_bold
        ))
        story.extend([
            Spacer(1, 0.3 * cm),
            Paragraph(
                "Napomena: šank čuva zbirni iznos bez naziva i količine artikala.",
                styles["Normal"],
            ),
        ])
        doc.build(story)
    except Exception as e:
        log.error(f"PDF izvještaj perioda {datum_od}—{datum_do} nije generisan: {e}")
        return ""
    return putanja


def _sadrzaj_perioda(podaci: dict) -> str:
    period = podaci["period"]
    sazetak = podaci["sazetak"]
    sesije = podaci["sesije"]
    tipovi = sesije["tipovi"]
    linija = "=" * 64
    tekst = [
        linija,
        "CAFFE & GAMING ZONE — POSLOVNI IZVJEŠTAJ",
        f"Period: {period['datum_od']} — {period['datum_do']}",
        linija,
        f"Ukupno             : {sazetak['ukupno']:.2f} KM",
        f"Računari           : {sazetak['racunari']:.2f} KM",
        f"Artikli uz uređaje : {sazetak['artikli']:.2f} KM",
        f"Šank               : {sazetak['sank']:.2f} KM",
        f"Završene smjene    : {sazetak['broj_zavrsenih_smjena']}",
        f"Broj sesija        : {sazetak['broj_sesija']}",
        f"Prosjek / smjena   : {sazetak['prosjek_po_smjeni']:.2f} KM",
        f"Prosjek / sesija   : {sazetak['prosjek_po_zavrsenoj_sesiji']:.2f} KM",
        "",
        "SESIJE",
        f"Regular: {tipovi['neograniceno']}  Prepaid: {tipovi['prepaid']}  "
        f"Pass1: {tipovi['pass1']}  Pass2: {tipovi['pass2']}  "
        f"Minecraft: {tipovi['minecraft']}  Aktivne: {sesije['aktivne']}",
        "",
        "TOP ARTIKLI PO KOLIČINI",
    ]
    for artikal in podaci["artikli"]["top_po_kolicini"][:10]:
        tekst.append(
            f"{artikal['naziv']:<24} {artikal['kolicina']:>6}  "
            f"{artikal['prihod']:>10.2f} KM"
        )
    tekst.extend(["", "SMJENE"])
    for smjena in podaci["smjene"]:
        kraj = _vrijeme(smjena["kraj"], 16) if smjena["kraj"] else "Otvorena"
        tekst.append(
            f"#{smjena['id']:<5} {(smjena['radnik'] or '—'):<18} "
            f"{_vrijeme(smjena['pocetak'], 16):<16}  {kraj:<16}  "
            f"{smjena['pazar']:.2f} KM"
        )
    tekst.extend([
        "",
        "Napomena: šank čuva zbirni iznos bez naziva i količine artikala.",
        "Imenovani artikli koriste vrijeme dodavanja na uređaj, ne vrijeme naplate.",
        f"Generisano: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
    ])
    return "\n".join(tekst)


def _pdf_tabela(redovi, sirine, font, font_bold):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    tabela = Table(redovi, colWidths=sirine, repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabela
