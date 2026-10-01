from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from services.permissions import ROLE
from services.users import (
    dohvati_korisnike,
    kreiraj_korisnika,
    postavi_aktivnost,
    promijeni_ime,
    promijeni_lozinku_korisnika,
    promijeni_rolu,
)


class NoviKorisnikDijalog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Novi korisnik")
        self.rezultat = None
        forma = QFormLayout(self)
        self.inp_username = QLineEdit()
        self.inp_ime = QLineEdit()
        self.inp_lozinka = QLineEdit()
        self.inp_lozinka.setEchoMode(QLineEdit.EchoMode.Password)
        self.cmb_rola = QComboBox()
        self.cmb_rola.addItems(ROLE)
        forma.addRow("Username:", self.inp_username)
        forma.addRow("Ime:", self.inp_ime)
        forma.addRow("Lozinka:", self.inp_lozinka)
        forma.addRow("Rola:", self.cmb_rola)
        dugmad = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        dugmad.accepted.connect(self._potvrdi)
        dugmad.rejected.connect(self.reject)
        forma.addRow(dugmad)

    def _potvrdi(self):
        self.rezultat = {
            "korisnicko_ime": self.inp_username.text(),
            "ime": self.inp_ime.text(),
            "lozinka": self.inp_lozinka.text(),
            "rola": self.cmb_rola.currentText(),
        }
        self.accept()


class KorisniciDijalog(QDialog):
    def __init__(self, actor, parent=None):
        super().__init__(parent)
        self.actor = actor
        self._redovi = []
        self.setWindowTitle("Korisnici")
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(
            ["Username", "Ime", "Rola", "Aktivan", "Zadnja prijava"]
        )
        self.tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tabela)
        akcije = QHBoxLayout()
        self.btn_novi = QPushButton("Novi")
        self.btn_ime = QPushButton("Promijeni ime")
        self.btn_rola = QPushButton("Promijeni rolu")
        self.btn_lozinka = QPushButton("Nova lozinka")
        self.btn_aktivnost = QPushButton("Aktiviraj/deaktiviraj")
        self.btn_refresh = QPushButton("Osvježi")
        for btn in (
            self.btn_novi, self.btn_ime, self.btn_rola, self.btn_lozinka,
            self.btn_aktivnost, self.btn_refresh
        ):
            akcije.addWidget(btn)
        layout.addLayout(akcije)
        self.btn_novi.clicked.connect(self._novi)
        self.btn_ime.clicked.connect(self._ime)
        self.btn_rola.clicked.connect(self._rola)
        self.btn_lozinka.clicked.connect(self._lozinka)
        self.btn_aktivnost.clicked.connect(self._aktivnost)
        self.btn_refresh.clicked.connect(self.osvjezi)
        self.osvjezi()

    def osvjezi(self):
        self._redovi = dohvati_korisnike(self.actor)["stavke"]
        self.tabela.setRowCount(0)
        for i, red in enumerate(self._redovi):
            self.tabela.insertRow(i)
            vrijednosti = (
                red["korisnicko_ime"], red["ime"], red["rola"],
                "Da" if red["aktivan"] else "Ne", red["zadnja_prijava"] or "—"
            )
            for j, vrijednost in enumerate(vrijednosti):
                self.tabela.setItem(i, j, QTableWidgetItem(str(vrijednost)))

    def _odabrani(self):
        red = self.tabela.currentRow()
        return self._redovi[red] if 0 <= red < len(self._redovi) else None

    def _izvrsi(self, funkcija):
        try:
            funkcija()
        except Exception as e:
            QMessageBox.warning(self, "Korisnici", str(e))
            return
        self.osvjezi()

    def _novi(self):
        dlg = NoviKorisnikDijalog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.rezultat:
            self._izvrsi(lambda: kreiraj_korisnika(self.actor, **dlg.rezultat))

    def _ime(self):
        red = self._odabrani()
        if not red:
            return
        ime, ok = QInputDialog.getText(self, "Ime", "Novo ime:", text=red["ime"])
        if ok:
            self._izvrsi(lambda: promijeni_ime(self.actor, red["id"], ime))

    def _rola(self):
        red = self._odabrani()
        if not red:
            return
        rola, ok = QInputDialog.getItem(
            self, "Rola", "Nova rola:", list(ROLE), list(ROLE).index(red["rola"]), False
        )
        if ok:
            self._izvrsi(lambda: promijeni_rolu(self.actor, red["id"], rola))

    def _lozinka(self):
        red = self._odabrani()
        if not red:
            return
        lozinka, ok = QInputDialog.getText(
            self, "Nova lozinka", "Lozinka:", QLineEdit.EchoMode.Password
        )
        if ok:
            self._izvrsi(
                lambda: promijeni_lozinku_korisnika(self.actor, red["id"], lozinka)
            )

    def _aktivnost(self):
        red = self._odabrani()
        if red:
            self._izvrsi(
                lambda: postavi_aktivnost(self.actor, red["id"], not red["aktivan"])
            )
