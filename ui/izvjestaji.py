from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.izvjestaj_perioda import dohvati_izvjestaj_perioda


_CARD_STYLE = (
    "QFrame { background: #111827; border: 1px solid #1e2433; "
    "border-radius: 8px; }"
)


class IzvjestajiDijalog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Poslovni izvještaji")
        self.resize(1120, 760)
        self._podaci: dict | None = None

        self._build_ui()
        self._povezi()
        self._preset_danas()
        self.show()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(8)

        naslov_red = QHBoxLayout()
        naslov = QLabel("POSLOVNI IZVJEŠTAJI")
        naslov.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #e2e8f0;"
        )
        naslov_red.addWidget(naslov)
        naslov_red.addStretch()
        self._btn_txt = QPushButton("Izvezi TXT")
        self._btn_pdf = QPushButton("Izvezi PDF")
        naslov_red.addWidget(self._btn_txt)
        naslov_red.addWidget(self._btn_pdf)
        root.addLayout(naslov_red)

        preset_red = QHBoxLayout()
        self._btn_danas = QPushButton("Danas")
        self._btn_jucer = QPushButton("Jučer")
        self._btn_ova_sedmica = QPushButton("Ova sedmica")
        self._btn_prosla_sedmica = QPushButton("Prošla sedmica")
        self._btn_ovaj_mjesec = QPushButton("Ovaj mjesec")
        self._btn_prosli_mjesec = QPushButton("Prošli mjesec")
        for dugme in (
            self._btn_danas,
            self._btn_jucer,
            self._btn_ova_sedmica,
            self._btn_prosla_sedmica,
            self._btn_ovaj_mjesec,
            self._btn_prosli_mjesec,
        ):
            preset_red.addWidget(dugme)
        preset_red.addStretch()
        root.addLayout(preset_red)

        period_red = QHBoxLayout()
        period_red.addWidget(QLabel("Od:"))
        self._datum_od = QDateEdit(QDate.currentDate())
        self._datum_od.setCalendarPopup(True)
        self._datum_od.setDisplayFormat("dd.MM.yyyy")
        period_red.addWidget(self._datum_od)
        period_red.addWidget(QLabel("Do:"))
        self._datum_do = QDateEdit(QDate.currentDate())
        self._datum_do.setCalendarPopup(True)
        self._datum_do.setDisplayFormat("dd.MM.yyyy")
        period_red.addWidget(self._datum_do)
        self._btn_prikazi = QPushButton("Prikaži")
        self._btn_prikazi.setObjectName("btnSuccess")
        period_red.addWidget(self._btn_prikazi)
        period_red.addStretch()
        self._lbl_period = QLabel("")
        self._lbl_period.setStyleSheet("color: #94a3b8; font-size: 11px;")
        period_red.addWidget(self._lbl_period)
        root.addLayout(period_red)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(9)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        finansije = QGridLayout()
        finansije.setSpacing(8)
        self._lbl_ukupno = self._metric_card(finansije, 0, "UKUPNO", "#f59e0b")
        self._lbl_racunari = self._metric_card(finansije, 1, "RAČUNARI", "#22c55e")
        self._lbl_artikli = self._metric_card(finansije, 2, "ARTIKLI", "#38bdf8")
        self._lbl_sank = self._metric_card(finansije, 3, "ŠANK", "#a78bfa")
        self._content_layout.addLayout(finansije)

        operativa = QGridLayout()
        operativa.setSpacing(8)
        self._lbl_smjene = self._metric_card(
            operativa, 0, "ZAVRŠENE SMJENE", "#94a3b8", "0"
        )
        self._lbl_sesije = self._metric_card(
            operativa, 1, "SESIJE", "#94a3b8", "0"
        )
        self._lbl_prosjek_smjena = self._metric_card(
            operativa, 2, "PROSJEK / SMJENA", "#38bdf8"
        )
        self._lbl_prosjek_sesija = self._metric_card(
            operativa, 3, "PROSJEK / ZAVRŠENA SESIJA", "#38bdf8"
        )
        self._content_layout.addLayout(operativa)

        trend = QFrame()
        trend.setStyleSheet(_CARD_STYLE)
        trend_lay = QHBoxLayout(trend)
        trend_lay.setContentsMargins(12, 8, 12, 8)
        trend_lay.addWidget(self._section_label("Trend prihoda"))
        self._lbl_trend = QLabel("— nema transakcija —")
        self._lbl_trend.setStyleSheet(
            "color: #f59e0b; font-size: 18px; letter-spacing: 2px;"
        )
        trend_lay.addWidget(self._lbl_trend, 1, Qt.AlignmentFlag.AlignCenter)
        self._lbl_granularnost = QLabel("")
        self._lbl_granularnost.setStyleSheet("color: #64748b; font-size: 10px;")
        trend_lay.addWidget(self._lbl_granularnost)
        self._content_layout.addWidget(trend)

        sesije_frame = QFrame()
        sesije_frame.setStyleSheet(_CARD_STYLE)
        sesije_lay = QVBoxLayout(sesije_frame)
        sesije_lay.setContentsMargins(12, 8, 12, 8)
        sesije_lay.addWidget(self._section_label("Sesije"))
        self._lbl_tipovi = QLabel("")
        self._lbl_tipovi.setWordWrap(True)
        self._lbl_tipovi.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        self._lbl_trajanje = QLabel("")
        self._lbl_trajanje.setStyleSheet("color: #94a3b8; font-size: 10px;")
        sesije_lay.addWidget(self._lbl_tipovi)
        sesije_lay.addWidget(self._lbl_trajanje)
        self._content_layout.addWidget(sesije_frame)

        uredjaji_red = QHBoxLayout()
        panel, self._tbl_uredjaji_sesije = self._table_panel(
            "Top uređaji po broju sesija", ["Uređaj", "Sesije"]
        )
        uredjaji_red.addWidget(panel, 1)
        panel, self._tbl_uredjaji_prihod = self._table_panel(
            "Top uređaji po prihodu*", ["Uređaj", "Prihod"]
        )
        uredjaji_red.addWidget(panel, 1)
        self._content_layout.addLayout(uredjaji_red)

        artikli_red = QHBoxLayout()
        panel, self._tbl_artikli_kolicina = self._table_panel(
            "Top artikli po količini**", ["Artikal", "Količina", "Prihod"]
        )
        artikli_red.addWidget(panel, 1)
        panel, self._tbl_artikli_prihod = self._table_panel(
            "Top artikli po prihodu**", ["Artikal", "Količina", "Prihod"]
        )
        artikli_red.addWidget(panel, 1)
        self._content_layout.addLayout(artikli_red)

        panel, self._tbl_smjene = self._table_panel(
            "Smjene u periodu",
            ["ID", "Radnik", "Početak", "Kraj / status", "Trajanje", "Pazar"],
        )
        panel.setMinimumHeight(230)
        self._content_layout.addWidget(panel)

        self._lbl_napomena = QLabel(
            "* Prihod prati uređaj zapisan na transakciji.  "
            "** Imenovani artikli koriste vrijeme dodavanja na uređaj; šank nema detalje artikala."
        )
        self._lbl_napomena.setWordWrap(True)
        self._lbl_napomena.setStyleSheet("color: #64748b; font-size: 9px;")
        self._content_layout.addWidget(self._lbl_napomena)

        btn_zatvori = QPushButton("Zatvori")
        btn_zatvori.clicked.connect(self.close)
        root.addWidget(btn_zatvori, 0, Qt.AlignmentFlag.AlignRight)

    def _povezi(self):
        self._btn_danas.clicked.connect(self._preset_danas)
        self._btn_jucer.clicked.connect(self._preset_jucer)
        self._btn_ova_sedmica.clicked.connect(self._preset_ova_sedmica)
        self._btn_prosla_sedmica.clicked.connect(self._preset_prosla_sedmica)
        self._btn_ovaj_mjesec.clicked.connect(self._preset_ovaj_mjesec)
        self._btn_prosli_mjesec.clicked.connect(self._preset_prosli_mjesec)
        self._btn_prikazi.clicked.connect(self._prikazi)
        self._btn_txt.clicked.connect(self._izvezi_txt)
        self._btn_pdf.clicked.connect(self._izvezi_pdf)

    def _preset_danas(self, *_args):
        danas = QDate.currentDate()
        self._postavi_period(danas, danas)

    def _preset_jucer(self, *_args):
        jucer = QDate.currentDate().addDays(-1)
        self._postavi_period(jucer, jucer)

    def _preset_ova_sedmica(self, *_args):
        danas = QDate.currentDate()
        ponedjeljak = danas.addDays(1 - danas.dayOfWeek())
        self._postavi_period(ponedjeljak, danas)

    def _preset_prosla_sedmica(self, *_args):
        danas = QDate.currentDate()
        ovaj_ponedjeljak = danas.addDays(1 - danas.dayOfWeek())
        self._postavi_period(
            ovaj_ponedjeljak.addDays(-7),
            ovaj_ponedjeljak.addDays(-1),
        )

    def _preset_ovaj_mjesec(self, *_args):
        danas = QDate.currentDate()
        self._postavi_period(QDate(danas.year(), danas.month(), 1), danas)

    def _preset_prosli_mjesec(self, *_args):
        danas = QDate.currentDate()
        prvi_ovog = QDate(danas.year(), danas.month(), 1)
        zadnji_proslog = prvi_ovog.addDays(-1)
        prvi_proslog = QDate(zadnji_proslog.year(), zadnji_proslog.month(), 1)
        self._postavi_period(prvi_proslog, zadnji_proslog)

    def _postavi_period(self, datum_od: QDate, datum_do: QDate):
        self._datum_od.setDate(datum_od)
        self._datum_do.setDate(datum_do)
        self._prikazi()

    def _prikazi(self, *_args) -> bool:
        datum_od = self._datum_od.date()
        datum_do = self._datum_do.date()
        if datum_od > datum_do:
            QMessageBox.warning(
                self,
                "Neispravan period",
                "Datum OD ne može biti poslije datuma DO.",
            )
            return False

        od = datum_od.toString("yyyy-MM-dd")
        do = datum_do.toString("yyyy-MM-dd")
        self._podaci = dohvati_izvjestaj_perioda(od, do)
        self._popuni(self._podaci)
        return True

    def _popuni(self, podaci: dict):
        p = podaci["sazetak"]
        self._lbl_period.setText(
            f"Period: {podaci['period']['datum_od']} — {podaci['period']['datum_do']}"
        )
        self._lbl_ukupno.setText(f"{p['ukupno']:.2f} KM")
        self._lbl_racunari.setText(f"{p['racunari']:.2f} KM")
        self._lbl_artikli.setText(f"{p['artikli']:.2f} KM")
        self._lbl_sank.setText(f"{p['sank']:.2f} KM")
        self._lbl_smjene.setText(str(p["broj_zavrsenih_smjena"]))
        self._lbl_sesije.setText(str(p["broj_sesija"]))
        self._lbl_prosjek_smjena.setText(f"{p['prosjek_po_smjeni']:.2f} KM")
        self._lbl_prosjek_sesija.setText(
            f"{p['prosjek_po_zavrsenoj_sesiji']:.2f} KM"
        )

        sesije = podaci["sesije"]
        tipovi = sesije["tipovi"]
        self._lbl_tipovi.setText(
            "Regular: {neograniceno}   Prepaid: {prepaid}   Pass1: {pass1}   "
            "Pass2: {pass2}   Minecraft: {minecraft}   Aktivne: {aktivne}".format(
                aktivne=sesije["aktivne"], **tipovi
            )
        )
        self._lbl_trajanje.setText(
            "Završene sesije: {broj} · ukupno trajanje: {ukupno} · prosjek: {prosjek}".format(
                broj=sesije["zavrsene"],
                ukupno=self._format_trajanje(sesije["ukupno_trajanje_zavrsenih"]),
                prosjek=self._format_trajanje(sesije["prosjek_trajanja_zavrsenih"]),
            )
        )

        self._lbl_trend.setText(self._sparkline(podaci["trend"]["tacke"]))
        self._lbl_granularnost.setText(
            "po satu" if podaci["trend"]["granularnost"] == "sat" else "po danu"
        )

        self._postavi_redove(
            self._tbl_uredjaji_sesije,
            [(r["uredjaj"] or "—", r["broj_sesija"])
             for r in sesije["top_uredjaji_po_sesijama"]],
        )
        self._postavi_redove(
            self._tbl_uredjaji_prihod,
            [(r["uredjaj"] or "—", f"{r['prihod']:.2f} KM")
             for r in sesije["top_uredjaji_po_prihodu"]],
        )
        self._postavi_artikle(
            self._tbl_artikli_kolicina, podaci["artikli"]["top_po_kolicini"]
        )
        self._postavi_artikle(
            self._tbl_artikli_prihod, podaci["artikli"]["top_po_prihodu"]
        )
        self._postavi_redove(
            self._tbl_smjene,
            [
                (
                    s["id"],
                    s["radnik"] or "—",
                    self._format_datum(s["pocetak"]),
                    self._format_datum(s["kraj"]) if s["kraj"] else "Otvorena",
                    self._format_trajanje(s["trajanje_sekundi"]),
                    f"{s['pazar']:.2f} KM",
                )
                for s in podaci["smjene"]
            ],
        )

    def _izvezi_txt(self):
        if not self._prikazi():
            return
        from services.izvjestaj import generisi_txt_perioda
        putanja = generisi_txt_perioda(
            self._datum_od.date().toString("yyyy-MM-dd"),
            self._datum_do.date().toString("yyyy-MM-dd"),
            self._podaci,
        )
        QMessageBox.information(self, "Izvoz", f"TXT izvještaj je snimljen:\n{putanja}")

    def _izvezi_pdf(self):
        if not self._prikazi():
            return
        from services.izvjestaj import generisi_pdf_perioda
        putanja = generisi_pdf_perioda(
            self._datum_od.date().toString("yyyy-MM-dd"),
            self._datum_do.date().toString("yyyy-MM-dd"),
            self._podaci,
        )
        if putanja:
            QMessageBox.information(self, "Izvoz", f"PDF izvještaj je snimljen:\n{putanja}")
        else:
            QMessageBox.warning(
                self, "Izvoz", "PDF nije generisan. Provjerite log i reportlab instalaciju."
            )

    def _metric_card(
        self, layout: QGridLayout, kolona: int, naslov: str, boja: str,
        pocetna: str = "0.00 KM",
    ) -> QLabel:
        frame = QFrame()
        frame.setStyleSheet(_CARD_STYLE)
        frame_lay = QVBoxLayout(frame)
        frame_lay.setContentsMargins(12, 8, 12, 8)
        lbl_naslov = QLabel(naslov)
        lbl_naslov.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 600;")
        lbl = QLabel(pocetna)
        lbl.setStyleSheet(f"color: {boja}; font-size: 17px; font-weight: 700;")
        frame_lay.addWidget(lbl_naslov)
        frame_lay.addWidget(lbl)
        layout.addWidget(frame, 0, kolona)
        return lbl

    @staticmethod
    def _section_label(tekst: str) -> QLabel:
        lbl = QLabel(tekst)
        lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        return lbl

    def _table_panel(self, naslov: str, kolone: list[str]):
        panel = QFrame()
        panel.setStyleSheet(_CARD_STYLE)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(self._section_label(naslov))
        tabela = QTableWidget(0, len(kolone))
        tabela.setHorizontalHeaderLabels(kolone)
        tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabela.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tabela.verticalHeader().setVisible(False)
        tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tabela.setShowGrid(False)
        layout.addWidget(tabela)
        return panel, tabela

    @staticmethod
    def _postavi_redove(tabela: QTableWidget, redovi: list[tuple]):
        tabela.setRowCount(len(redovi))
        for red, vrijednosti in enumerate(redovi):
            for kolona, vrijednost in enumerate(vrijednosti):
                tabela.setItem(red, kolona, QTableWidgetItem(str(vrijednost)))

    def _postavi_artikle(self, tabela: QTableWidget, artikli: list[dict]):
        self._postavi_redove(
            tabela,
            [(a["naziv"], a["kolicina"], f"{a['prihod']:.2f} KM") for a in artikli],
        )

    @staticmethod
    def _sparkline(tacke: list[dict]) -> str:
        vrijednosti = [float(t["iznos"]) for t in tacke]
        if not vrijednosti or max(vrijednosti) <= 0:
            return "— nema transakcija —"
        znakovi = "▁▂▃▄▅▆▇█"
        maksimum = max(vrijednosti)
        return "".join(
            znakovi[min(7, int(vrijednost / maksimum * 7))]
            for vrijednost in vrijednosti
        )

    @staticmethod
    def _format_datum(vrijednost) -> str:
        if not vrijednost:
            return "—"
        try:
            return datetime.fromisoformat(vrijednost).strftime("%d.%m.%Y %H:%M")
        except (TypeError, ValueError):
            return str(vrijednost)

    @staticmethod
    def _format_trajanje(sekunde) -> str:
        if sekunde is None:
            return "—"
        sekunde = max(0, int(sekunde))
        sati, ostatak = divmod(sekunde, 3600)
        minute, sekunde = divmod(ostatak, 60)
        return f"{sati:02d}:{minute:02d}:{sekunde:02d}"
