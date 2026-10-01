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
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
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
    dohvati_rezervacijsku_grupu,
    dohvati_slobodne_uredjaje_za_period,
    izmijeni_rezervacijsku_grupu,
    izmijeni_rezervaciju,
    kreiraj_rezervacijsku_grupu,
    kreiraj_rezervaciju,
    promijeni_status_rezervacijske_grupe,
    promijeni_status_rezervacije,
)
from services.uredjaji import ucitaj_uredjaje
from ui.timeline_rezervacija import RezervacijeTimeline


def _vrijednost(red, kljuc, default=None):
    try:
        return red[kljuc]
    except (KeyError, IndexError, TypeError):
        return default


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


class GrupnaRezervacijaDijalog(QDialog):
    def __init__(self, parent, uredjaji: list, grupa=None):
        super().__init__(parent)
        self.setWindowTitle(
            "Izmijeni grupnu rezervaciju" if grupa else "Nova grupna rezervacija"
        )
        self.resize(560, 620)
        self.rezultat = None
        self._svi_uredjaji = list(uredjaji)
        self._grupa_id = _vrijednost(grupa, "id") if grupa else None

        layout = QVBoxLayout(self)
        forma = QFormLayout()
        self.inp_gost = QLineEdit()
        self.inp_telefon = QLineEdit()
        sada = (datetime.now() + timedelta(minutes=30)).replace(
            second=0, microsecond=0
        )
        kraj = sada + timedelta(hours=1)
        if kraj.date() != sada.date():
            sutra = datetime.now().date() + timedelta(days=1)
            sada = datetime.combine(sutra, datetime.min.time()).replace(hour=10)
            kraj = sada + timedelta(hours=1)
        self.inp_datum = QDateEdit(QDate(sada.year, sada.month, sada.day))
        self.inp_datum.setCalendarPopup(True)
        self.inp_pocetak = QTimeEdit(QTime(sada.hour, sada.minute))
        self.inp_kraj = QTimeEdit(QTime(kraj.hour, kraj.minute))
        self.inp_napomena = QTextEdit()
        self.inp_napomena.setFixedHeight(64)
        self.inp_broj = QSpinBox()
        self.inp_broj.setRange(2, max(2, len(self._svi_uredjaji)))
        self.inp_broj.setValue(2)
        self.cmb_tip = QComboBox()
        self.cmb_tip.addItem("Svi tipovi", None)
        for tip in sorted({u["tip"] for u in self._svi_uredjaji}):
            self.cmb_tip.addItem(tip, tip)
        self.cmb_grupa = QComboBox()
        self.cmb_grupa.addItem("Sve grupe", None)
        for naziv in sorted({u["grupa"] for u in self._svi_uredjaji}):
            self.cmb_grupa.addItem(naziv, naziv)
        forma.addRow("Ime gosta:", self.inp_gost)
        forma.addRow("Telefon:", self.inp_telefon)
        forma.addRow("Datum:", self.inp_datum)
        forma.addRow("Početak:", self.inp_pocetak)
        forma.addRow("Kraj:", self.inp_kraj)
        forma.addRow("Broj uređaja:", self.inp_broj)
        forma.addRow("Tip:", self.cmb_tip)
        forma.addRow("Grupa:", self.cmb_grupa)
        forma.addRow("Napomena:", self.inp_napomena)
        layout.addLayout(forma)

        self.lista_uredjaja = QListWidget()
        self.lista_uredjaja.setSelectionMode(
            QListWidget.SelectionMode.MultiSelection
        )
        layout.addWidget(QLabel("Slobodni/odabrani uređaji:"))
        layout.addWidget(self.lista_uredjaja, 1)
        self.btn_predlozi = QPushButton("Predloži uređaje")
        self.btn_predlozi.clicked.connect(self._predlozi)
        layout.addWidget(self.btn_predlozi)

        if grupa is not None:
            self.inp_gost.setText(grupa["ime_gosta"])
            self.inp_telefon.setText(grupa["telefon"] or "")
            pocetak = datetime.fromisoformat(grupa["pocetak"])
            kraj = datetime.fromisoformat(grupa["kraj"])
            self.inp_datum.setDate(QDate(pocetak.year, pocetak.month, pocetak.day))
            self.inp_pocetak.setTime(QTime(pocetak.hour, pocetak.minute))
            self.inp_kraj.setTime(QTime(kraj.hour, kraj.minute))
            self.inp_napomena.setPlainText(grupa["napomena"] or "")
            self.inp_broj.setValue(len(grupa["uredjaji"]))

        self.cmb_tip.currentIndexChanged.connect(self._popuni_uredjaje)
        self.cmb_grupa.currentIndexChanged.connect(self._popuni_uredjaje)
        self.inp_datum.dateChanged.connect(self._popuni_uredjaje)
        self.inp_pocetak.timeChanged.connect(self._popuni_uredjaje)
        self.inp_kraj.timeChanged.connect(self._popuni_uredjaje)
        self._popuni_uredjaje()
        if grupa is not None:
            self._odaberi_ids({u["id"] for u in grupa["uredjaji"]})

        dugmad = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        dugmad.accepted.connect(self._potvrdi)
        dugmad.rejected.connect(self.reject)
        layout.addWidget(dugmad)

    def _period(self):
        datum = self.inp_datum.date().toPython()
        return (
            datetime.combine(datum, self.inp_pocetak.time().toPython()),
            datetime.combine(datum, self.inp_kraj.time().toPython()),
        )

    def _popuni_uredjaje(self):
        odabrani = {
            stavka.data(Qt.ItemDataRole.UserRole)
            for stavka in self.lista_uredjaja.selectedItems()
        }
        self.lista_uredjaja.clear()
        tip = self.cmb_tip.currentData()
        grupa = self.cmb_grupa.currentData()
        pocetak, kraj = self._period()
        if pocetak >= kraj:
            return
        slobodni = dohvati_slobodne_uredjaje_za_period(
            pocetak,
            kraj,
            tip=tip,
            grupa=grupa,
            izuzmi_grupa_id=self._grupa_id,
        )
        slobodni_ids = {red["id"] for red in slobodni}
        for uredjaj in self._svi_uredjaji:
            if tip is not None and uredjaj["tip"] != tip:
                continue
            if grupa is not None and uredjaj["grupa"] != grupa:
                continue
            if uredjaj["id"] not in slobodni_ids:
                continue
            stavka = QListWidgetItem(
                f"{uredjaj['ime']} · {uredjaj['tip']} · {uredjaj['grupa']}"
            )
            stavka.setData(Qt.ItemDataRole.UserRole, uredjaj["id"])
            self.lista_uredjaja.addItem(stavka)
            stavka.setSelected(uredjaj["id"] in odabrani)

    def _odaberi_ids(self, ids: set[int]):
        self.lista_uredjaja.clearSelection()
        for indeks in range(self.lista_uredjaja.count()):
            stavka = self.lista_uredjaja.item(indeks)
            stavka.setSelected(stavka.data(Qt.ItemDataRole.UserRole) in ids)

    def _predlozi(self):
        pocetak, kraj = self._period()
        try:
            slobodni = dohvati_slobodne_uredjaje_za_period(
                pocetak,
                kraj,
                tip=self.cmb_tip.currentData(),
                grupa=self.cmb_grupa.currentData(),
                broj=self.inp_broj.value(),
                izuzmi_grupa_id=self._grupa_id,
            )
        except ValueError as e:
            QMessageBox.warning(self, "Grupna rezervacija", str(e))
            return
        if len(slobodni) < self.inp_broj.value():
            QMessageBox.warning(
                self,
                "Grupna rezervacija",
                f"Dostupno je samo {len(slobodni)} traženih uređaja.",
            )
            return
        self._odaberi_ids({red["id"] for red in slobodni})

    def _potvrdi(self):
        if not self.inp_gost.text().strip():
            QMessageBox.warning(
                self, "Grupna rezervacija", "Ime gosta je obavezno."
            )
            return
        pocetak, kraj = self._period()
        if pocetak >= kraj:
            QMessageBox.warning(
                self,
                "Grupna rezervacija",
                "Početak rezervacije mora biti prije kraja.",
            )
            return
        ids = [
            stavka.data(Qt.ItemDataRole.UserRole)
            for stavka in self.lista_uredjaja.selectedItems()
        ]
        if len(ids) < 2:
            QMessageBox.warning(
                self,
                "Grupna rezervacija",
                "Odaberite najmanje 2 uređaja.",
            )
            return
        self.rezultat = {
            "uredjaj_ids": ids,
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
        self._uredjaji = []
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

        self.timeline = RezervacijeTimeline()
        self.tabela = QTableWidget(0, 7)
        self.tabela.setHorizontalHeaderLabels(
            ["Vrijeme", "Uređaj", "Gost", "Telefon", "Status", "Napomena", "Radnik"]
        )
        self.tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.pogledi = QTabWidget()
        self.pogledi.addTab(self.timeline, "Timeline")
        self.pogledi.addTab(self.tabela, "Tabela")
        layout.addWidget(self.pogledi, 1)

        akcije = QHBoxLayout()
        self.btn_nova = QPushButton("Nova")
        self.btn_nova_grupa = QPushButton("Nova grupa")
        self.btn_izmijeni = QPushButton("Izmijeni")
        self.btn_stigao = QPushButton("Stigao")
        self.btn_zavrsi = QPushButton("Završi")
        self.btn_otkazi = QPushButton("Otkaži")
        self.btn_no_show = QPushButton("No-show")
        for dugme in (
            self.btn_nova,
            self.btn_nova_grupa,
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
        self.timeline.blok_clicked.connect(self._timeline_klik)
        self.btn_nova.clicked.connect(self._nova)
        self.btn_nova_grupa.clicked.connect(self._nova_grupa)
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
        self._uredjaji = list(ucitaj_uredjaje())
        for uredjaj in self._uredjaji:
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
            gost = red["ime_gosta"]
            if _vrijednost(red, "grupa_id") is not None:
                velicina = _vrijednost(red, "grupa_velicina", "?")
                gost = f"Grupa {gost} ({velicina})"
            vrijednosti = (
                f"{pocetak:%H:%M}–{kraj:%H:%M}",
                red["uredjaj"],
                gost,
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
        odabrani_id = self.cmb_uredjaj.currentData()
        uredjaji = [
            uredjaj
            for uredjaj in self._uredjaji
            if odabrani_id is None or uredjaj["id"] == odabrani_id
        ]
        self.timeline.set_podaci(
            uredjaji, self._redovi, self.inp_datum.date().toPython()
        )
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

    def _nova_grupa(self):
        actor = self._actor()
        if actor is None:
            return
        forma = GrupnaRezervacijaDijalog(self, self._uredjaji)
        if forma.exec() != QDialog.DialogCode.Accepted or forma.rezultat is None:
            return
        try:
            kreiraj_rezervacijsku_grupu(
                **forma.rezultat,
                actor=actor,
                smjena_id=self._smjena_id_getter(),
            )
        except (ValueError, PermissionError) as e:
            QMessageBox.warning(self, "Grupna rezervacija", str(e))
            return
        self._nakon_promjene()

    def _izmijeni(self):
        rezervacija = self._odabrana()
        actor = self._actor()
        if rezervacija is None or actor is None:
            return
        grupa_id = _vrijednost(rezervacija, "grupa_id")
        if grupa_id is not None:
            grupa = dohvati_rezervacijsku_grupu(grupa_id)
            if grupa is None:
                QMessageBox.warning(
                    self, "Grupna rezervacija", "Grupna rezervacija ne postoji."
                )
                return
            forma = GrupnaRezervacijaDijalog(self, self._uredjaji, grupa)
        else:
            forma = RezervacijaFormaDijalog(
                self, self._uredjaji, rezervacija
            )
        if forma.exec() != QDialog.DialogCode.Accepted or forma.rezultat is None:
            return
        try:
            if grupa_id is not None:
                izmijeni_rezervacijsku_grupu(
                    grupa_id,
                    **forma.rezultat,
                    actor=actor,
                    smjena_id=self._smjena_id_getter(),
                )
            else:
                izmijeni_rezervaciju(
                    rezervacija["id"],
                    **forma.rezultat,
                    actor=actor,
                    smjena_id=self._smjena_id_getter(),
                )
        except (ValueError, PermissionError) as e:
            QMessageBox.warning(self, "Rezervacija", str(e))
            return
        self._nakon_promjene()

    def _promijeni_status(self, status):
        rezervacija = self._odabrana()
        actor = self._actor()
        if rezervacija is None or actor is None:
            return
        try:
            grupa_id = _vrijednost(rezervacija, "grupa_id")
            if grupa_id is not None:
                promijeni_status_rezervacijske_grupe(
                    grupa_id, status, actor, self._smjena_id_getter()
                )
            else:
                promijeni_status_rezervacije(
                    rezervacija["id"], status, actor, self._smjena_id_getter()
                )
        except (ValueError, PermissionError) as e:
            QMessageBox.warning(self, "Rezervacija", str(e))
            return
        self._nakon_promjene()

    def _timeline_klik(self, rezervacija):
        rezervacija_id = rezervacija["id"]
        for indeks, red in enumerate(self._redovi):
            if red["id"] == rezervacija_id:
                self.tabela.selectRow(indeks)
                break
        if rezervacija["status"] == STATUS_REZERVISANO:
            self._izmijeni()
            return
        pocetak = datetime.fromisoformat(rezervacija["pocetak"])
        kraj = datetime.fromisoformat(rezervacija["kraj"])
        gost = rezervacija["ime_gosta"]
        if _vrijednost(rezervacija, "grupa_id") is not None:
            velicina = _vrijednost(rezervacija, "grupa_velicina", "?")
            gost = f"Grupa {gost} ({velicina})"
        QMessageBox.information(
            self,
            "Detalji rezervacije",
            "\n".join(
                (
                    f"{gost} • {rezervacija['uredjaj']}",
                    f"{pocetak:%d.%m.%Y. %H:%M}–{kraj:%H:%M}",
                    "Status: "
                    + NAZIVI_STATUSA.get(
                        rezervacija["status"], rezervacija["status"]
                    ),
                )
            ),
        )

    def _nakon_promjene(self):
        self.osvjezi()
        self.rezervacije_changed.emit()
