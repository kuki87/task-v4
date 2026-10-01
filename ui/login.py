from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from services.users import (
    kreiraj_prvog_admina,
    migriraj_legacy_admin,
    prijavi_korisnika,
)


class LoginDijalog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prijava")
        self.setFixedSize(360, 240)
        self.korisnik = None
        layout = QVBoxLayout(self)
        naslov = QLabel("Caffe & Gaming Zone")
        naslov.setAlignment(Qt.AlignmentFlag.AlignCenter)
        naslov.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(naslov)
        forma = QFormLayout()
        self.inp_username = QLineEdit()
        self.inp_lozinka = QLineEdit()
        self.inp_lozinka.setEchoMode(QLineEdit.EchoMode.Password)
        forma.addRow("Korisničko ime:", self.inp_username)
        forma.addRow("Lozinka:", self.inp_lozinka)
        layout.addLayout(forma)
        self.btn_prijava = QPushButton("Prijava")
        self.btn_prijava.setObjectName("btnSuccess")
        self.btn_prijava.clicked.connect(self._prijavi)
        self.inp_lozinka.returnPressed.connect(self._prijavi)
        layout.addWidget(self.btn_prijava)

    def _prijavi(self):
        try:
            korisnik = prijavi_korisnika(
                self.inp_username.text(), self.inp_lozinka.text()
            )
        except Exception as e:
            QMessageBox.critical(self, "Prijava", f"Prijava nije uspjela:\n{e}")
            return
        if korisnik is None:
            QMessageBox.warning(
                self, "Prijava", "Neispravno korisničko ime ili lozinka."
            )
            self.inp_lozinka.clear()
            return
        self.korisnik = korisnik
        self.accept()


class FirstRunDijalog(QDialog):
    def __init__(self, stanje: str, parent=None):
        super().__init__(parent)
        self.stanje = stanje
        self.korisnik = None
        self.setWindowTitle("Prvo pokretanje")
        self.setFixedSize(430, 360 if stanje == "migracija_legacy" else 320)
        layout = QVBoxLayout(self)
        opis = QLabel(
            "Kreirajte prvi administratorski nalog. Nema zadane lozinke."
            if stanje == "novi_admin"
            else "Potvrdite postojeću admin lozinku i kreirajte novi administratorski nalog."
        )
        opis.setWordWrap(True)
        layout.addWidget(opis)
        forma = QFormLayout()
        self.inp_legacy = None
        if stanje == "migracija_legacy":
            self.inp_legacy = QLineEdit()
            self.inp_legacy.setEchoMode(QLineEdit.EchoMode.Password)
            forma.addRow("Postojeća admin lozinka:", self.inp_legacy)
        self.inp_username = QLineEdit()
        self.inp_ime = QLineEdit()
        self.inp_lozinka = QLineEdit()
        self.inp_potvrda = QLineEdit()
        self.inp_lozinka.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_potvrda.setEchoMode(QLineEdit.EchoMode.Password)
        forma.addRow("Korisničko ime:", self.inp_username)
        forma.addRow("Ime:", self.inp_ime)
        forma.addRow("Nova lozinka:", self.inp_lozinka)
        forma.addRow("Potvrda lozinke:", self.inp_potvrda)
        layout.addLayout(forma)
        dugme = QPushButton("Kreiraj admin nalog")
        dugme.setObjectName("btnSuccess")
        dugme.clicked.connect(self._kreiraj)
        layout.addWidget(dugme)

    def _kreiraj(self):
        if self.inp_lozinka.text() != self.inp_potvrda.text():
            QMessageBox.warning(self, "Prvo pokretanje", "Lozinke se ne podudaraju.")
            return
        try:
            if self.stanje == "migracija_legacy":
                self.korisnik = migriraj_legacy_admin(
                    self.inp_legacy.text(),
                    self.inp_username.text(),
                    self.inp_ime.text(),
                    self.inp_lozinka.text(),
                )
            else:
                self.korisnik = kreiraj_prvog_admina(
                    self.inp_username.text(),
                    self.inp_ime.text(),
                    self.inp_lozinka.text(),
                )
        except Exception as e:
            QMessageBox.warning(self, "Prvo pokretanje", str(e))
            return
        self.accept()
