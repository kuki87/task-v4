from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, QTime, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
)

from services.rezervacije import (
    DOZVOLJENE_TRANZICIJE,
    NAZIVI_STATUSA,
    STATUSI_REZERVACIJE,
    STATUS_NO_SHOW,
    STATUS_OTKAZANO,
    STATUS_REZERVISANO,
    STATUS_STIGAO,
    STATUS_ZAVRSENO,
    dohvati_rezervacije,
    izmijeni_rezervaciju,
    kreiraj_rezervaciju,
    promijeni_status_rezervacije,
)
from services.uredjaji import ucitaj_uredjaje


class RezervacijaFormaDijalog(QDialog):
    def __init__(self, parent, uredjaji: list, rezervacija=None):
        super().__init__(parent)
        self.setWindowTitle("Izmijeni rezervaciju" if rezervacija else "Nova rezervacija")
        self.resize(430, 390)
        self.rezultat = None

        layout = QVBoxLayout(self)
        forma = QFormLayout()
        self.cmb_uredjaj = QComboBox()
        for uredjaj in uredjaji:
            self.cmb_uredjaj.addItem(uredjaj["ime"], uredjaj["id"])
        self.inp_gost = QLineEdit()
        self.inp_telefon = QLineEdit()
        sada = (datetime.now() + timedelta(minutes=30)).replace(
            second=0, microsecond=0
        )
        za_pola_sata = sada + timedelta(minutes=30)
        if za_pola_sata.date() != sada.date():
            sutra = datetime.now().date() + timedelta(days=1)
            sada = datetime.combine(sutra, datetime.min.time()).replace(hour=10)
            za_pola_sata = sada + timedelta(minutes=30)
        self.inp_datum = QDateEdit(QDate(sada.year, sada.month, sada.day))
        self.inp_datum.setCalendarPopup(True)
        self.inp_pocetak = QTimeEdit(QTime(sada.hour, sada.minute))
        self.inp_kraj = QTimeEdit(QTime(za_pola_sata.hour, za_pola_sata.minute))
        self.inp_napomena = QTextEdit()
        self.inp_napomena.setFixedHeight(80)
        forma.addRow("Uređaj:", self.cmb_uredjaj)
        forma.addRow("Ime gosta:", self.inp_gost)
        forma.addRow("Telefon:", self.inp_telefon)
        forma.addRow("Datum:", self.inp_datum)
        forma.addRow("Početak:", self.inp_pocetak)
        forma.addRow("Kraj:", self.inp_kraj)
        forma.addRow("Napomena:", self.inp_napomena)
        layout.addLayout(forma)

        if rezervacija is not None:
            self.cmb_uredjaj.setCurrentIndex(
                self.cmb_uredjaj.findData(rezervacija["uredjaj_id"])
            )
            self.inp_gost.setText(rezervacija["ime_gosta"])
            self.inp_telefon.setText(rezervacija["telefon"] or "")
            pocetak = datetime.fromisoformat(rezervacija["pocetak"])
            kraj = datetime.fromisoformat(rezervacija["kraj"])
            self.inp_datum.setDate(QDate(pocetak.year, pocetak.month, pocetak.day))
            self.inp_pocetak.setTime(QTime(pocetak.hour, pocetak.minute))
            self.inp_kraj.setTime(QTime(kraj.hour, kraj.minute))
            self.inp_napomena.setPlainText(rezervacija["napomena"] or "")

        dugmad = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        dugmad.accepted.connect(self._potvrdi)
        dugmad.rejected.connect(self.reject)
        layout.addWidget(dugmad)

    def _potvrdi(self):
        if self.cmb_uredjaj.currentData() is None:
            QMessageBox.warning(self, "Rezervacija", "Odaberite uređaj.")
            return
        if not self.inp_gost.text().strip():
            QMessageBox.warning(self, "Rezervacija", "Ime gosta je obavezno.")
            return
        datum = self.inp_datum.date().toPython()
        pocetak_vrijeme = self.inp_pocetak.time().toPython()
        kraj_vrijeme = self.inp_kraj.time().toPython()
        pocetak = datetime.combine(datum, pocetak_vrijeme)
        kraj = datetime.combine(datum, kraj_vrijeme)
        if pocetak >= kraj:
            QMessageBox.warning(
                self, "Rezervacija", "Početak rezervacije mora biti prije kraja."
            )
            return
        self.rezultat = {
            "uredjaj_id": self.cmb_uredjaj.currentData(),
            "ime_gosta": self.inp_gost.text().strip(),
            "telefon": self.inp_telefon.text().strip() or None,
            "pocetak": pocetak,
            "kraj": kraj,
            "napomena": self.inp_napomena.toPlainText().strip() or None,
        }
        self.accept()


class RezervacijeDijalog(QDialog):
    rezervacije_changed = Signal()

    def __init__(self, parent=None, actor_getter=None, smjena_id_getter=None):
        super().__init__(parent)
        self.setWindowTitle("Rezervacije")
        self.resize(920, 620)
        self._actor_getter = actor_getter or (lambda: None)
        self._smjena_id_getter = smjena_id_getter or (lambda: None)
        self._redovi = []
        self._build_ui()
        self._ucitaj_uredjaje()
        self.osvjezi()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        filteri = QHBoxLayout()
        self.inp_datum = QDateEdit(QDate.currentDate())
        self.inp_datum.setCalendarPopup(True)
        self.btn_danas = QPushButton("Danas")
        self.btn_sutra = QPushButton("Sutra")
        self.cmb_uredjaj = QComboBox()
        self.cmb_status = QComboBox()
        self.cmb_status.addItem("Svi statusi", None)
        for status in STATUSI_REZERVACIJE:
            self.cmb_status.addItem(NAZIVI_STATUSA[status], status)
        self.inp_pretraga = QLineEdit()
        self.inp_pretraga.setPlaceholderText("Gost, telefon ili uređaj")
        self.btn_refresh = QPushButton("Osvježi")
        filteri.addWidget(QLabel("Datum:"))
        filteri.addWidget(self.inp_datum)
        filteri.addWidget(self.btn_danas)
        filteri.addWidget(self.btn_sutra)
        filteri.addWidget(self.cmb_uredjaj)
        filteri.addWidget(self.cmb_status)
        filteri.addWidget(self.inp_pretraga, 1)
        filteri.addWidget(self.btn_refresh)
        layout.addLayout(filteri)

        self.tabela = QTableWidget(0, 7)
        self.tabela.setHorizontalHeaderLabels(
            ["Vrijeme", "Uređaj", "Gost", "Telefon", "Status", "Napomena", "Radnik"]
        )
        self.tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tabela, 1)

        akcije = QHBoxLayout()
        self.btn_nova = QPushButton("Nova")
        self.btn_izmijeni = QPushButton("Izmijeni")
        self.btn_stigao = QPushButton("Stigao")
        self.btn_zavrsi = QPushButton("Završi")
        self.btn_otkazi = QPushButton("Otkaži")
        self.btn_no_show = QPushButton("No-show")
        for dugme in (
            self.btn_nova,
            self.btn_izmijeni,
            self.btn_stigao,
            self.btn_zavrsi,
            self.btn_otkazi,
            self.btn_no_show,
        ):
            akcije.addWidget(dugme)
        akcije.addStretch()
        layout.addLayout(akcije)

        self.btn_danas.clicked.connect(lambda: self.inp_datum.setDate(QDate.currentDate()))
        self.btn_sutra.clicked.connect(
            lambda: self.inp_datum.setDate(QDate.currentDate().addDays(1))
        )
        self.btn_refresh.clicked.connect(self.osvjezi)
        self.inp_datum.dateChanged.connect(self.osvjezi)
        self.cmb_uredjaj.currentIndexChanged.connect(self.osvjezi)
        self.cmb_status.currentIndexChanged.connect(self.osvjezi)
        self.inp_pretraga.returnPressed.connect(self.osvjezi)
        self.tabela.itemSelectionChanged.connect(self._osvjezi_akcije)
        self.btn_nova.clicked.connect(self._nova)
        self.btn_izmijeni.clicked.connect(self._izmijeni)
        self.btn_stigao.clicked.connect(lambda: self._promijeni_status(STATUS_STIGAO))
        self.btn_zavrsi.clicked.connect(lambda: self._promijeni_status(STATUS_ZAVRSENO))
        self.btn_otkazi.clicked.connect(lambda: self._promijeni_status(STATUS_OTKAZANO))
        self.btn_no_show.clicked.connect(lambda: self._promijeni_status(STATUS_NO_SHOW))

    def _ucitaj_uredjaje(self):
        trenutno = self.cmb_uredjaj.currentData()
        self.cmb_uredjaj.blockSignals(True)
        self.cmb_uredjaj.clear()
        self.cmb_uredjaj.addItem("Svi uređaji", None)
        for uredjaj in ucitaj_uredjaje():
            self.cmb_uredjaj.addItem(uredjaj["ime"], uredjaj["id"])
        indeks = self.cmb_uredjaj.findData(trenutno)
        self.cmb_uredjaj.setCurrentIndex(max(0, indeks))
        self.cmb_uredjaj.blockSignals(False)

    def osvjezi(self):
        self._redovi = list(
            dohvati_rezervacije(
                datum=self.inp_datum.date().toPython(),
                uredjaj_id=self.cmb_uredjaj.currentData(),
                status=self.cmb_status.currentData(),
                pretraga=self.inp_pretraga.text(),
            )
        )
        self.tabela.setRowCount(0)
        for broj, red in enumerate(self._redovi):
            self.tabela.insertRow(broj)
            pocetak = datetime.fromisoformat(red["pocetak"])
            kraj = datetime.fromisoformat(red["kraj"])
            vrijednosti = (
                f"{pocetak:%H:%M}–{kraj:%H:%M}",
                red["uredjaj"],
                red["ime_gosta"],
                red["telefon"] or "—",
                NAZIVI_STATUSA.get(red["status"], red["status"]),
                red["napomena"] or "—",
                red["kreirao_radnik"],
            )
            for kolona, vrijednost in enumerate(vrijednosti):
                stavka = QTableWidgetItem(str(vrijednost))
                if kolona == 0:
                    stavka.setData(Qt.ItemDataRole.UserRole, red["id"])
                self.tabela.setItem(broj, kolona, stavka)
        self._osvjezi_akcije()

    def _odabrana(self):
        red = self.tabela.currentRow()
        if red < 0 or red >= len(self._redovi):
            return None
        return self._redovi[red]

    def _osvjezi_akcije(self):
        rezervacija = self._odabrana()
        status = rezervacija["status"] if rezervacija else None
        dozvoljeni = DOZVOLJENE_TRANZICIJE.get(status, set())
        self.btn_izmijeni.setEnabled(status == STATUS_REZERVISANO)
        self.btn_stigao.setEnabled(STATUS_STIGAO in dozvoljeni)
        self.btn_zavrsi.setEnabled(STATUS_ZAVRSENO in dozvoljeni)
        self.btn_otkazi.setEnabled(STATUS_OTKAZANO in dozvoljeni)
        self.btn_no_show.setEnabled(STATUS_NO_SHOW in dozvoljeni)

    def _actor(self):
        actor = self._actor_getter()
        if actor is None:
            QMessageBox.warning(
                self, "Rezervacije", "Korisnik nije prijavljen."
            )
            return None
        return actor

    def _nova(self):
        actor = self._actor()
        if actor is None:
            return
        uredjaji = ucitaj_uredjaje()
        forma = RezervacijaFormaDijalog(self, uredjaji)
        if forma.exec() != QDialog.DialogCode.Accepted or forma.rezultat is None:
            return
        try:
            kreiraj_rezervaciju(
                **forma.rezultat,
                actor=actor,
                smjena_id=self._smjena_id_getter(),
            )
        except ValueError as e:
            QMessageBox.warning(self, "Rezervacija", str(e))
            return
        self._nakon_promjene()

    def _izmijeni(self):
        rezervacija = self._odabrana()
        actor = self._actor()
        if rezervacija is None or actor is None:
            return
        forma = RezervacijaFormaDijalog(self, ucitaj_uredjaje(), rezervacija)
        if forma.exec() != QDialog.DialogCode.Accepted or forma.rezultat is None:
            return
        try:
            izmijeni_rezervaciju(
                rezervacija["id"],
                **forma.rezultat,
                actor=actor,
                smjena_id=self._smjena_id_getter(),
            )
        except ValueError as e:
            QMessageBox.warning(self, "Rezervacija", str(e))
            return
        self._nakon_promjene()

    def _promijeni_status(self, status):
        rezervacija = self._odabrana()
        actor = self._actor()
        if rezervacija is None or actor is None:
            return
        try:
            promijeni_status_rezervacije(
                rezervacija["id"], status, actor, self._smjena_id_getter()
            )
        except ValueError as e:
            QMessageBox.warning(self, "Rezervacija", str(e))
            return
        self._nakon_promjene()

    def _nakon_promjene(self):
        self.osvjezi()
        self.rezervacije_changed.emit()
