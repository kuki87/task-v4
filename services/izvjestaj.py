import os
from datetime import datetime
from typing import List
from database.db import get_db

IZVJESTAJI_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Izvještaji")


def _osiguraj_folder():
    os.makedirs(IZVJESTAJI_DIR, exist_ok=True)


def generiši_tekstualni(smjena_id: int, podaci: dict) -> str:
    """Kreira tekstualni izvještaj, sprema ga u Izvještaji/ i vraća sadržaj."""
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
        tekst.append(f"Radnik    : {smjena['radnik']}")
        tekst.append(f"Početak   : {smjena['pocetak'][:19].replace('T', ' ')}")
        kraj = smjena['kraj']
        if kraj:
            tekst.append(f"Kraj      : {kraj[:19].replace('T', ' ')}")
        tekst.append(f"Pazar     : {smjena['pazar']:.2f} KM")

    tekst.append("")
    tekst.append("--- TRANSAKCIJE ---")

    ukupno_racunari = 0.0
    ukupno_sank = 0.0
    ukupno_artikli = 0.0

    for t in transakcije:
        vreme = t["vreme"][:19].replace("T", " ") if t["vreme"] else ""
        tekst.append(f"{vreme}  {t['uredjaj']:<12}  {t['tip_prodaje']:<12}  {t['iznos']:.2f} KM")
        if t["tip_prodaje"] == "sank":
            ukupno_sank += t["iznos"]
        elif t["tip_prodaje"] == "artikal":
            ukupno_artikli += t["iznos"]
        else:
            ukupno_racunari += t["iznos"]

    tekst.append("")
    tekst.append(linija)
    tekst.append(f"Računari  : {ukupno_racunari:.2f} KM")
    tekst.append(f"Artikli   : {ukupno_artikli:.2f} KM")
    tekst.append(f"Šank      : {ukupno_sank:.2f} KM")
    tekst.append(f"UKUPNO    : {(ukupno_racunari + ukupno_sank + ukupno_artikli):.2f} KM")
    tekst.append(linija)

    if podaci.get("preneseni_racunari"):
        tekst.append("")
        tekst.append("--- PRENESENI U NOVU SMJENU ---")
        for r in podaci["preneseni_racunari"]:
            tekst.append(f"  • {r}")

    tekst.append("")
    tekst.append(f"Generisano: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

    sadrzaj = "\n".join(tekst)

    _osiguraj_folder()
    txt_file = os.path.join(
        IZVJESTAJI_DIR,
        f"izvjestaj_smjena_{smjena_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(sadrzaj)

    return sadrzaj


def generiši_pdf(smjena_id: int, podaci: dict) -> str:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.units import cm
    except ImportError:
        return ""

    conn = get_db()
    smjena = conn.execute("SELECT * FROM smjene WHERE id = ?", (smjena_id,)).fetchone()
    transakcije = conn.execute(
        "SELECT vreme, uredjaj, iznos, tip_prodaje FROM pazar_arhiva WHERE smjena_id = ? ORDER BY vreme",
        (smjena_id,)
    ).fetchall()

    _osiguraj_folder()
    filename = os.path.join(
        IZVJESTAJI_DIR,
        f"izvjestaj_smjena_{smjena_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )
    doc = SimpleDocTemplate(filename, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
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
            ["Radnik:", smjena["radnik"]],
            ["Početak:", smjena["pocetak"][:19].replace("T", " ")],
            ["Pazar:", f"{smjena['pazar']:.2f} KM"],
        ]
        if smjena["kraj"]:
            info_data.insert(3, ["Kraj:", smjena["kraj"][:19].replace("T", " ")])

        t = Table(info_data, colWidths=[4*cm, 10*cm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.5*cm))

    # Tabela transakcija
    story.append(Paragraph("Transakcije", styles["Heading3"]))
    if transakcije:
        zaglavlje = [["Vrijeme", "Uređaj", "Tip", "Iznos (KM)"]]
        redovi = []
        for t in transakcije:
            vreme = t["vreme"][:16].replace("T", " ") if t["vreme"] else ""
            redovi.append([vreme, t["uredjaj"], t["tip_prodaje"], f"{t['iznos']:.2f}"])

        tabela_data = zaglavlje + redovi
        tabela = Table(tabela_data, colWidths=[4.5*cm, 4*cm, 4*cm, 3*cm])
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tabela)

    story.append(Spacer(1, 0.3*cm))

    if podaci.get("preneseni_racunari"):
        story.append(Paragraph("Preneseni u novu smjenu:", styles["Heading3"]))
        for r in podaci["preneseni_racunari"]:
            story.append(Paragraph(f"• {r}", styles["Normal"]))

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        f"Generisano: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
        styles["Normal"]
    ))

    doc.build(story)
    return filename
