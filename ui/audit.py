from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from services.audit import dohvati_audit, dohvati_audit_opcije


class AuditDijalog(QDialog):
    def __init__(self, actor, parent=None, limit=100):
        super().__init__(parent)
        self.actor = actor
        self.limit = limit
        self.offset = 0
        self.setWindowTitle("Audit")
        self.resize(1000, 580)
        layout = QVBoxLayout(self)
        filteri = QHBoxLayout()
        danas = QDate.currentDate()
        self.datum_od = QDateEdit(danas.addDays(-7))
        self.datum_do = QDateEdit(danas)
        self.datum_od.setCalendarPopup(True)
        self.datum_do.setCalendarPopup(True)
        self.cmb_korisnik = QComboBox()
        self.cmb_akcija = QComboBox()
        self.cmb_entitet = QComboBox()
        self.cmb_uredjaj = QComboBox()
        self.inp_pretraga = QLineEdit()
        self.inp_pretraga.setPlaceholderText("Pretraga")
        self.btn_refresh = QPushButton("Osvježi")
        for labela, widget in (
            ("OD", self.datum_od), ("DO", self.datum_do),
            ("Korisnik", self.cmb_korisnik), ("Akcija", self.cmb_akcija),
            ("Entitet", self.cmb_entitet), ("Uređaj", self.cmb_uredjaj),
        ):
            filteri.addWidget(QLabel(labela))
            filteri.addWidget(widget)
        filteri.addWidget(self.inp_pretraga, 1)
        filteri.addWidget(self.btn_refresh)
        layout.addLayout(filteri)
        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(
            ["Vrijeme", "Korisnik", "Akcija", "Entitet", "Objekt", "Detalj"]
        )
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tabela)
        navigacija = QHBoxLayout()
        self.btn_prethodna = QPushButton("Prethodna")
        self.btn_sljedeca = QPushButton("Sljedeća")
        self.lbl_stranica = QLabel()
        navigacija.addWidget(self.btn_prethodna)
        navigacija.addWidget(self.btn_sljedeca)
        navigacija.addWidget(self.lbl_stranica)
        navigacija.addStretch()
        layout.addLayout(navigacija)
        self.btn_refresh.clicked.connect(self._reset_i_osvjezi)
        self.btn_prethodna.clicked.connect(self._prethodna)
        self.btn_sljedeca.clicked.connect(self._sljedeca)
        self._ucitaj_opcije()
        self.osvjezi()

    def _ucitaj_opcije(self):
        opcije = dohvati_audit_opcije(self.actor)
        self.cmb_korisnik.addItem("Svi", None)
        for red in opcije["korisnici"]:
            self.cmb_korisnik.addItem(red["naziv"], red["user_id"])
        for combo, naziv, vrijednosti in (
            (self.cmb_akcija, "Sve", opcije["akcije"]),
            (self.cmb_entitet, "Svi", opcije["entiteti"]),
            (self.cmb_uredjaj, "Svi", opcije["uredjaji"]),
        ):
            combo.addItem(naziv, None)
            for vrijednost in vrijednosti:
                combo.addItem(vrijednost, vrijednost)

    def osvjezi(self):
        rezultat = dohvati_audit(
            self.actor,
            datum_od=self.datum_od.date().toPython(),
            datum_do=self.datum_do.date().toPython(),
            user_id=self.cmb_korisnik.currentData(),
            akcija=self.cmb_akcija.currentData(),
            entitet=self.cmb_entitet.currentData(),
            uredjaj=self.cmb_uredjaj.currentData(),
            pretraga=self.inp_pretraga.text(),
            limit=self.limit,
            offset=self.offset,
        )
        self.tabela.setRowCount(0)
        for i, red in enumerate(rezultat["stavke"]):
            self.tabela.insertRow(i)
            vrijednosti = (
                (red["vreme"] or "").replace("T", " ")[:19],
                red["username"] or red["radnik"] or "—",
                red["akcija"] or "—",
                red["entitet"] or "—",
                red["entitet_id"] or "—",
                red["detalj"] or "—",
            )
            for j, vrijednost in enumerate(vrijednosti):
                self.tabela.setItem(i, j, QTableWidgetItem(str(vrijednost)))
        ukupno = rezultat["ukupno"]
        self.btn_prethodna.setEnabled(self.offset > 0)
        self.btn_sljedeca.setEnabled(self.offset + self.limit < ukupno)
        self.lbl_stranica.setText(
            f"{self.offset + 1 if ukupno else 0}–{min(self.offset + self.limit, ukupno)} / {ukupno}"
        )

    def _reset_i_osvjezi(self):
        self.offset = 0
        self.osvjezi()

    def _prethodna(self):
        self.offset = max(0, self.offset - self.limit)
        self.osvjezi()

    def _sljedeca(self):
        self.offset += self.limit
        self.osvjezi()
