from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from services.pazar import (
    dohvati_historiju_sesija,
    dohvati_opcije_historije_sesija,
)


class HistorijaSesijaDijalog(QDialog):
    LIMIT = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Historija sesija")
        self.resize(1180, 720)
        self._offset = 0
        self._stavke: list[dict] = []

        self._build_ui()
        self._ucitaj_opcije()
        self._povezi_filtere()
        self.osvjezi()
        self.show()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(9)

        naslov = QLabel("HISTORIJA SESIJA")
        naslov.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #e2e8f0;"
        )
        root.addWidget(naslov)

        filter_frame = QFrame()
        filter_frame.setStyleSheet(
            "QFrame { background: #111827; border: 1px solid #1e2433; "
            "border-radius: 8px; }"
        )
        filter_lay = QGridLayout(filter_frame)
        filter_lay.setContentsMargins(10, 8, 10, 8)
        filter_lay.setHorizontalSpacing(8)
        filter_lay.setVerticalSpacing(6)

        self._pretraga = QLineEdit()
        self._pretraga.setPlaceholderText("ID, uređaj, tip ili radnik…")
        self._pretraga.setClearButtonEnabled(True)
        filter_lay.addWidget(QLabel("Pretraga"), 0, 0)
        filter_lay.addWidget(self._pretraga, 1, 0)

        self._combo_uredjaj = QComboBox()
        filter_lay.addWidget(QLabel("Uređaj"), 0, 1)
        filter_lay.addWidget(self._combo_uredjaj, 1, 1)

        self._combo_tip = QComboBox()
        filter_lay.addWidget(QLabel("Tip sesije"), 0, 2)
        filter_lay.addWidget(self._combo_tip, 1, 2)

        self._combo_status = QComboBox()
        self._combo_status.addItem("Sve", "sve")
        self._combo_status.addItem("Aktivne", "aktivna")
        self._combo_status.addItem("Završene", "zavrsena")
        filter_lay.addWidget(QLabel("Status"), 0, 3)
        filter_lay.addWidget(self._combo_status, 1, 3)

        self._check_od = QCheckBox("Datum od")
        self._datum_od = QDateEdit(QDate.currentDate().addMonths(-1))
        self._datum_od.setCalendarPopup(True)
        self._datum_od.setDisplayFormat("dd.MM.yyyy")
        self._datum_od.setEnabled(False)
        od_lay = QHBoxLayout()
        od_lay.setContentsMargins(0, 0, 0, 0)
        od_lay.addWidget(self._check_od)
        od_lay.addWidget(self._datum_od)
        filter_lay.addLayout(od_lay, 2, 0)

        self._check_do = QCheckBox("Datum do")
        self._datum_do = QDateEdit(QDate.currentDate())
        self._datum_do.setCalendarPopup(True)
        self._datum_do.setDisplayFormat("dd.MM.yyyy")
        self._datum_do.setEnabled(False)
        do_lay = QHBoxLayout()
        do_lay.setContentsMargins(0, 0, 0, 0)
        do_lay.addWidget(self._check_do)
        do_lay.addWidget(self._datum_do)
        filter_lay.addLayout(do_lay, 2, 1)

        btn_red = QHBoxLayout()
        btn_red.setContentsMargins(0, 0, 0, 0)
        self._btn_reset = QPushButton("Poništi filtere")
        self._btn_osvjezi = QPushButton("Osvježi")
        self._btn_osvjezi.setObjectName("btnSuccess")
        btn_red.addWidget(self._btn_reset)
        btn_red.addWidget(self._btn_osvjezi)
        filter_lay.addLayout(btn_red, 2, 3)
        root.addWidget(filter_frame)

        self._tbl = QTableWidget(0, 10)
        self._tbl.setHorizontalHeaderLabels([
            "ID",
            "Početak",
            "Uređaj",
            "Tip",
            "Status",
            "Trajanje",
            "Računar",
            "Artikli",
            "Ukupno",
            "Smjena",
        ])
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._tbl.setSortingEnabled(False)
        root.addWidget(self._tbl, 1)

        detalji = QFrame()
        detalji.setStyleSheet(
            "QFrame { background: #111827; border: 1px solid #1e2433; "
            "border-radius: 8px; }"
        )
        detalji_lay = QVBoxLayout(detalji)
        detalji_lay.setContentsMargins(12, 8, 12, 8)
        detalji_naslov = QLabel("Detalji odabrane sesije")
        detalji_naslov.setStyleSheet(
            "color: #94a3b8; font-size: 11px; font-weight: 600;"
        )
        self._lbl_detalji = QLabel("Odaberite sesiju iz tabele.")
        self._lbl_detalji.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._lbl_detalji.setWordWrap(True)
        self._lbl_detalji.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        detalji_lay.addWidget(detalji_naslov)
        detalji_lay.addWidget(self._lbl_detalji)
        root.addWidget(detalji)

        dno = QHBoxLayout()
        self._lbl_rezultati = QLabel("0 sesija")
        self._lbl_rezultati.setStyleSheet("color: #64748b; font-size: 10px;")
        dno.addWidget(self._lbl_rezultati)
        dno.addStretch()
        self._btn_prethodna = QPushButton("← Prethodna")
        self._btn_sljedeca = QPushButton("Sljedeća →")
        dno.addWidget(self._btn_prethodna)
        dno.addWidget(self._btn_sljedeca)
        btn_zatvori = QPushButton("Zatvori")
        btn_zatvori.clicked.connect(self.close)
        dno.addWidget(btn_zatvori)
        root.addLayout(dno)

    def _ucitaj_opcije(self):
        opcije = dohvati_opcije_historije_sesija()
        self._combo_uredjaj.addItem("Svi uređaji", None)
        for uredjaj in opcije["uredjaji"]:
            self._combo_uredjaj.addItem(uredjaj, uredjaj)
        self._combo_tip.addItem("Svi tipovi", None)
        for tip in opcije["tipovi"]:
            self._combo_tip.addItem(tip, tip)

    def _povezi_filtere(self):
        self._combo_uredjaj.currentIndexChanged.connect(
            self._resetuj_stranicu_i_osvjezi
        )
        self._combo_tip.currentIndexChanged.connect(
            self._resetuj_stranicu_i_osvjezi
        )
        self._combo_status.currentIndexChanged.connect(
            self._resetuj_stranicu_i_osvjezi
        )
        self._check_od.toggled.connect(self._datum_od.setEnabled)
        self._check_od.toggled.connect(self._resetuj_stranicu_i_osvjezi)
        self._check_do.toggled.connect(self._datum_do.setEnabled)
        self._check_do.toggled.connect(self._resetuj_stranicu_i_osvjezi)
        self._datum_od.dateChanged.connect(self._datum_filter_promijenjen)
        self._datum_do.dateChanged.connect(self._datum_filter_promijenjen)
        self._pretraga.returnPressed.connect(self._resetuj_stranicu_i_osvjezi)
        self._btn_osvjezi.clicked.connect(self._resetuj_stranicu_i_osvjezi)
        self._btn_reset.clicked.connect(self._ponisti_filtere)
        self._btn_prethodna.clicked.connect(self._prethodna_stranica)
        self._btn_sljedeca.clicked.connect(self._sljedeca_stranica)
        self._tbl.itemSelectionChanged.connect(self._prikazi_detalje)

    def _datum_filter_promijenjen(self):
        if self.sender() is self._datum_od and not self._check_od.isChecked():
            return
        if self.sender() is self._datum_do and not self._check_do.isChecked():
            return
        self._resetuj_stranicu_i_osvjezi()

    def _filteri(self) -> dict:
        return {
            "datum_od": (
                self._datum_od.date().toString("yyyy-MM-dd")
                if self._check_od.isChecked() else None
            ),
            "datum_do": (
                self._datum_do.date().toString("yyyy-MM-dd")
                if self._check_do.isChecked() else None
            ),
            "uredjaj": self._combo_uredjaj.currentData(),
            "tip": self._combo_tip.currentData(),
            "status": self._combo_status.currentData(),
            "pretraga": self._pretraga.text().strip() or None,
            "limit": self.LIMIT,
            "offset": self._offset,
        }

    def osvjezi(self):
        rezultat = dohvati_historiju_sesija(**self._filteri())
        self._stavke = rezultat["stavke"]
        ukupno = rezultat["ukupno"]
        self._popuni_tabelu()

        prikaz_od = self._offset + 1 if ukupno else 0
        prikaz_do = min(self._offset + len(self._stavke), ukupno)
        self._lbl_rezultati.setText(
            f"{ukupno} sesija · prikaz {prikaz_od}–{prikaz_do}"
        )
        self._btn_prethodna.setEnabled(self._offset > 0)
        self._btn_sljedeca.setEnabled(self._offset + len(self._stavke) < ukupno)

        if self._stavke:
            self._tbl.selectRow(0)
        else:
            self._lbl_detalji.setText("Nema sesija za odabrane filtere.")

    def _popuni_tabelu(self):
        self._tbl.setRowCount(len(self._stavke))
        for red, sesija in enumerate(self._stavke):
            vrijednosti = [
                sesija["id"],
                self._format_datum(sesija["vreme_starta"]),
                sesija["uredjaj"] or "—",
                sesija["tip"] or "—",
                "Aktivna" if sesija["status"] == "aktivna" else "Završena",
                self._format_trajanje(sesija["trajanje_sekundi"]),
                f"{sesija['iznos_racunara']:.2f} KM",
                f"{sesija['iznos_artikala']:.2f} KM",
                f"{sesija['ukupno']:.2f} KM",
                f"#{sesija['smjena_id']}",
            ]
            for kolona, vrijednost in enumerate(vrijednosti):
                self._tbl.setItem(red, kolona, QTableWidgetItem(str(vrijednost)))

    def _prikazi_detalje(self):
        red = self._tbl.currentRow()
        if red < 0 or red >= len(self._stavke):
            self._lbl_detalji.setText("Odaberite sesiju iz tabele.")
            return
        s = self._stavke[red]
        kraj = self._format_datum(s["vreme_kraja"]) if s["vreme_kraja"] else "— aktivna"
        status = "Aktivna" if s["status"] == "aktivna" else "Završena"
        self._lbl_detalji.setText(
            f"Sesija #{s['id']} · {s['uredjaj'] or '—'} · {s['tip'] or '—'} · {status}\n"
            f"Početak: {self._format_datum(s['vreme_starta'])}   "
            f"Kraj: {kraj}   Trajanje: {self._format_trajanje(s['trajanje_sekundi'])}\n"
            f"Smjena: #{s['smjena_id']} · Radnik: {s['radnik'] or '—'}\n"
            f"Računar: {s['iznos_racunara']:.2f} KM   "
            f"Artikli: {s['iznos_artikala']:.2f} KM   "
            f"Ukupno evidentirano: {s['ukupno']:.2f} KM\n"
            "Nazivi i količine artikala nisu dostupni po sesiji u trenutnoj šemi."
        )

    def _resetuj_stranicu_i_osvjezi(self, *_args):
        self._offset = 0
        self.osvjezi()

    def _ponisti_filtere(self):
        kontrole = (
            self._pretraga,
            self._combo_uredjaj,
            self._combo_tip,
            self._combo_status,
            self._check_od,
            self._check_do,
        )
        blokatori = [QSignalBlocker(kontrola) for kontrola in kontrole]
        self._pretraga.clear()
        self._combo_uredjaj.setCurrentIndex(0)
        self._combo_tip.setCurrentIndex(0)
        self._combo_status.setCurrentIndex(0)
        self._check_od.setChecked(False)
        self._check_do.setChecked(False)
        self._datum_od.setEnabled(False)
        self._datum_do.setEnabled(False)
        del blokatori
        self._resetuj_stranicu_i_osvjezi()

    def _prethodna_stranica(self):
        self._offset = max(0, self._offset - self.LIMIT)
        self.osvjezi()

    def _sljedeca_stranica(self):
        self._offset += self.LIMIT
        self.osvjezi()

    @staticmethod
    def _format_datum(vrijednost) -> str:
        if not vrijednost:
            return "—"
        try:
            return datetime.fromisoformat(vrijednost).strftime("%d.%m.%Y %H:%M:%S")
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
