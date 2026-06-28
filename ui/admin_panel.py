from __future__ import annotations
import re
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QInputDialog, QSizePolicy, QScrollArea,
    QFrame,
)
from PySide6.QtCore import Qt

from services.auth import provjeri_admin_lozinku, promijeni_lozinku
from services.artikli import ucitaj_artikle, dodaj_artikal, uredi_artikal, brisi_artikal
from services.uredjaji import (
    ucitaj_uredjaje, dodaj_uredjaj, brisi_uredjaj,
    ucitaj_logove, postavi_cijenu_grupe,
)


class AdminPanel(QDialog):
    def __init__(self, parent, reload_callback: Optional[Callable] = None):
        super().__init__(parent)
        self.setWindowTitle("Admin Panel")
        self.resize(680, 660)
        self.reload_callback = reload_callback
        self.auth_ok = False

        # Password check BEFORE showing window
        lozinka, ok = QInputDialog.getText(
            parent, "Admin", "Unesite admin lozinku:",
            QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        if not provjeri_admin_lozinku(lozinka):
            QMessageBox.critical(parent, "Greška", "Pogrešna lozinka!")
            return

        self.auth_ok = True
        self._build_ui()

    def exec(self):
        if not self.auth_ok:
            return QDialog.DialogCode.Rejected
        return super().exec()

    # ── Build ──────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)

        self._tabs = QTabWidget()
        lay.addWidget(self._tabs)

        self._tabs.addTab(self._tab_artikli(),   "Artikli")
        self._tabs.addTab(self._tab_uredjaji(),  "Uređaji")
        self._tabs.addTab(self._tab_logovi(),    "Logovi")
        self._tabs.addTab(self._tab_lozinka(),   "Lozinka")

    # ── TAB ARTIKLI ────────────────────────────────────────────

    def _tab_artikli(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)

        # Input row
        inp = QHBoxLayout()
        inp.addWidget(QLabel("Naziv:"))
        self._entry_art_naziv = QLineEdit()
        self._entry_art_naziv.setPlaceholderText("Naziv artikla")
        self._entry_art_naziv.setFixedWidth(160)
        inp.addWidget(self._entry_art_naziv)

        inp.addWidget(QLabel("Cijena (KM):"))
        self._entry_art_cijena = QLineEdit()
        self._entry_art_cijena.setPlaceholderText("0.00")
        self._entry_art_cijena.setFixedWidth(80)
        inp.addWidget(self._entry_art_cijena)

        btn_add = QPushButton("Dodaj")
        btn_add.setObjectName("btnSuccess")
        btn_add.setFixedWidth(80)
        btn_add.clicked.connect(self._dodaj_artikal)
        inp.addWidget(btn_add)
        inp.addStretch()
        lay.addLayout(inp)

        # Table
        self._tbl_artikli = QTableWidget(0, 3)
        self._tbl_artikli.setHorizontalHeaderLabels(["Naziv", "Cijena", "Akcija"])
        self._tbl_artikli.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tbl_artikli.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._tbl_artikli.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._tbl_artikli.setColumnWidth(1, 90)
        self._tbl_artikli.setColumnWidth(2, 130)
        self._tbl_artikli.verticalHeader().setVisible(False)
        self._tbl_artikli.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl_artikli.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self._tbl_artikli)

        self._ucitaj_artikle()
        return w

    def _ucitaj_artikle(self):
        self._tbl_artikli.setRowCount(0)
        self._artikli_ids = []
        for a in ucitaj_artikle():
            row = self._tbl_artikli.rowCount()
            self._tbl_artikli.insertRow(row)
            self._tbl_artikli.setItem(row, 0, QTableWidgetItem(a["naziv"]))
            self._tbl_artikli.setItem(row, 1, QTableWidgetItem(f"{a['cijena']:.2f} KM"))
            self._artikli_ids.append(a["id"])

            cell = QWidget()
            cell_lay = QHBoxLayout(cell)
            cell_lay.setContentsMargins(4, 2, 4, 2)
            cell_lay.setSpacing(4)

            btn_e = QPushButton("Uredi")
            btn_e.setObjectName("btnWarning")
            btn_e.setFixedHeight(24)
            btn_e.clicked.connect(
                lambda _, aid=a["id"], an=a["naziv"], ac=a["cijena"]: self._uredi_artikal(aid, an, ac)
            )
            btn_d = QPushButton("Briši")
            btn_d.setObjectName("btnDanger")
            btn_d.setFixedHeight(24)
            btn_d.clicked.connect(lambda _, aid=a["id"]: self._brisi_artikal(aid))

            cell_lay.addWidget(btn_e)
            cell_lay.addWidget(btn_d)
            self._tbl_artikli.setCellWidget(row, 2, cell)

    def _dodaj_artikal(self):
        naziv = self._entry_art_naziv.text().strip()
        try:
            cijena = float(self._entry_art_cijena.text().replace(",", "."))
        except ValueError:
            QMessageBox.warning(self, "Greška", "Nevalidna cijena!")
            return
        if not naziv:
            QMessageBox.warning(self, "Greška", "Unesite naziv!")
            return
        try:
            dodaj_artikal(naziv, cijena)
            self._entry_art_naziv.clear()
            self._entry_art_cijena.clear()
            self._ucitaj_artikle()
            if self.reload_callback:
                self.reload_callback()
        except Exception as e:
            QMessageBox.warning(self, "Greška", f"Artikal već postoji: {e}")

    def _uredi_artikal(self, aid: int, naziv: str, cijena: float):
        novi_naziv, ok = QInputDialog.getText(self, "Uredi", "Novi naziv:", text=naziv)
        if not ok:
            return
        nova_c_str, ok2 = QInputDialog.getText(self, "Uredi", "Nova cijena:", text=str(cijena))
        if not ok2:
            return
        try:
            nova_c = float(nova_c_str.replace(",", "."))
        except ValueError:
            QMessageBox.warning(self, "Greška", "Nevalidna cijena!")
            return
        uredi_artikal(aid, novi_naziv, nova_c)
        self._ucitaj_artikle()
        if self.reload_callback:
            self.reload_callback()

    def _brisi_artikal(self, aid: int):
        if QMessageBox.question(self, "Potvrda", "Obrisati artikal?") != QMessageBox.StandardButton.Yes:
            return
        brisi_artikal(aid)
        self._ucitaj_artikle()
        if self.reload_callback:
            self.reload_callback()

    # ── TAB UREĐAJI ────────────────────────────────────────────

    def _tab_uredjaji(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)

        # Input row
        inp = QHBoxLayout()
        inp.setSpacing(6)

        inp.addWidget(QLabel("Ime:"))
        self._entry_urd_ime = QLineEdit()
        self._entry_urd_ime.setPlaceholderText("PC")
        self._entry_urd_ime.setFixedWidth(70)
        inp.addWidget(self._entry_urd_ime)

        inp.addWidget(QLabel("KM/h:"))
        self._entry_urd_cena = QLineEdit()
        self._entry_urd_cena.setPlaceholderText("2.0")
        self._entry_urd_cena.setFixedWidth(50)
        inp.addWidget(self._entry_urd_cena)

        inp.addWidget(QLabel("Tip:"))
        self._combo_tip = QComboBox()
        self._combo_tip.addItems(["PC", "PS5"])
        self._combo_tip.setFixedWidth(60)
        self._combo_tip.currentTextChanged.connect(self._on_tip_changed)
        inp.addWidget(self._combo_tip)

        inp.addWidget(QLabel("Grupa:"))
        self._combo_grupa = QComboBox()
        self._combo_grupa.addItems(["Classic", "VIP", "Super VIP"])
        self._combo_grupa.setFixedWidth(90)
        inp.addWidget(self._combo_grupa)

        inp.addWidget(QLabel("Kol:"))
        self._entry_kolicina = QLineEdit("1")
        self._entry_kolicina.setFixedWidth(35)
        inp.addWidget(self._entry_kolicina)

        btn_add = QPushButton("Dodaj")
        btn_add.setObjectName("btnSuccess")
        btn_add.setFixedWidth(70)
        btn_add.clicked.connect(self._dodaj_uredjaj)
        inp.addWidget(btn_add)
        inp.addStretch()
        lay.addLayout(inp)

        # Device list
        self._tbl_uredjaji = QTableWidget(0, 5)
        self._tbl_uredjaji.setHorizontalHeaderLabels(["Ime", "Cijena", "Tip", "Grupa", ""])
        self._tbl_uredjaji.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, w_px in [(1, 80), (2, 50), (3, 90), (4, 70)]:
            self._tbl_uredjaji.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self._tbl_uredjaji.setColumnWidth(col, w_px)
        self._tbl_uredjaji.verticalHeader().setVisible(False)
        self._tbl_uredjaji.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl_uredjaji.setFixedHeight(200)
        lay.addWidget(self._tbl_uredjaji)

        btn_osvjezi = QPushButton("Osvježi listu")
        btn_osvjezi.setFixedWidth(130)
        btn_osvjezi.clicked.connect(self._ucitaj_uredjaje)
        lay.addWidget(btn_osvjezi)

        # ── Price per group ────
        hdr = QLabel("Postavi cijenu po grupi (KM/h)")
        hdr.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 700; margin-top: 8px;")
        lay.addWidget(hdr)

        cijena_frame = QFrame()
        cijena_frame.setStyleSheet(
            "QFrame { background: #111827; border: 1px solid #1e2433; border-radius: 8px; }"
        )
        cijena_lay = QVBoxLayout(cijena_frame)
        cijena_lay.setContentsMargins(10, 8, 10, 8)
        cijena_lay.setSpacing(6)

        self._entry_cijene: dict = {}
        for grupa in ["Classic", "VIP", "Super VIP", "PS5"]:
            row = QHBoxLayout()
            lbl = QLabel(grupa)
            lbl.setFixedWidth(90)
            lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
            row.addWidget(lbl)

            entry = QLineEdit()
            entry.setFixedWidth(80)
            entry.setPlaceholderText("—")
            self._entry_cijene[grupa] = entry
            row.addWidget(entry)

            btn_s = QPushButton("Sačuvaj")
            btn_s.setObjectName("btnSuccess")
            btn_s.setFixedWidth(80)
            btn_s.clicked.connect(lambda _, g=grupa: self._postavi_cijenu_grupe(g))
            row.addWidget(btn_s)
            row.addStretch()
            cijena_lay.addLayout(row)

        lay.addWidget(cijena_frame)
        lay.addStretch()

        self._ucitaj_uredjaje()
        return w

    def _on_tip_changed(self, vrijednost: str):
        if vrijednost == "PS5":
            self._combo_grupa.setCurrentText("Classic")
            self._combo_grupa.setEnabled(False)
        else:
            self._combo_grupa.setEnabled(True)

    def _ucitaj_uredjaje(self):
        self._tbl_uredjaji.setRowCount(0)
        self._uredjaj_ids = []

        cijene_po_grupi: dict = {}
        for u in ucitaj_uredjaje():
            row = self._tbl_uredjaji.rowCount()
            self._tbl_uredjaji.insertRow(row)
            self._tbl_uredjaji.setItem(row, 0, QTableWidgetItem(u["ime"]))
            self._tbl_uredjaji.setItem(row, 1, QTableWidgetItem(f"{u['cena']:.2f} KM/h"))
            self._tbl_uredjaji.setItem(row, 2, QTableWidgetItem(u["tip"]))
            self._tbl_uredjaji.setItem(row, 3, QTableWidgetItem(u["grupa"]))
            self._uredjaj_ids.append(u["id"])

            btn_d = QPushButton("Briši")
            btn_d.setObjectName("btnDanger")
            btn_d.setFixedHeight(24)
            btn_d.clicked.connect(lambda _, uid=u["id"]: self._brisi_uredjaj(uid))
            self._tbl_uredjaji.setCellWidget(row, 4, btn_d)

            g = u["grupa"]
            if g not in cijene_po_grupi:
                cijene_po_grupi[g] = u["cena"]

        # Fill group price entries with current values
        for g, entry in self._entry_cijene.items():
            if g in cijene_po_grupi:
                entry.setText(f"{cijene_po_grupi[g]:.2f}")

    def _dodaj_uredjaj(self):
        base_ime = self._entry_urd_ime.text().strip()
        try:
            cena = float(self._entry_urd_cena.text().replace(",", "."))
        except ValueError:
            QMessageBox.warning(self, "Greška", "Nevalidna cijena!")
            return
        try:
            kolicina = max(1, int(self._entry_kolicina.text().strip() or "1"))
        except ValueError:
            QMessageBox.warning(self, "Greška", "Nevalidna količina!")
            return

        tip = self._combo_tip.currentText()
        grupa = "PS5" if tip == "PS5" else self._combo_grupa.currentText()
        if not base_ime:
            QMessageBox.warning(self, "Greška", "Unesite ime uređaja!")
            return

        try:
            if kolicina == 1:
                dodaj_uredjaj(base_ime, cena, tip, grupa)
            else:
                svi = ucitaj_uredjaje()
                postojeci_imena = {u["ime"] for u in svi}
                svi_brojevi = [
                    int(m.group(1))
                    for u in svi
                    if (m := re.search(r'(\d+)$', u["ime"]))
                ]
                sljedeci = (max(svi_brojevi) + 1) if svi_brojevi else 1
                created = 0
                while created < kolicina:
                    kandidat = f"{base_ime}{sljedeci}"
                    if kandidat not in postojeci_imena:
                        dodaj_uredjaj(kandidat, cena, tip, grupa)
                        postojeci_imena.add(kandidat)
                        created += 1
                    sljedeci += 1

            self._entry_urd_ime.clear()
            self._entry_urd_cena.clear()
            self._entry_kolicina.setText("1")
            self._ucitaj_uredjaje()
            if self.reload_callback:
                self.reload_callback()
        except Exception as e:
            QMessageBox.warning(self, "Greška", f"Greška: {e}")

    def _postavi_cijenu_grupe(self, grupa: str):
        raw = self._entry_cijene[grupa].text().strip().replace(",", ".")
        try:
            cena = float(raw)
        except ValueError:
            QMessageBox.warning(self, "Greška", f"Nevalidna cijena za grupu {grupa}!")
            return
        azurirano = postavi_cijenu_grupe(grupa, cena)
        QMessageBox.information(
            self, "OK",
            f"Ažurirano {azurirano} uređaja u grupi '{grupa}' → {cena:.2f} KM/h"
        )
        self._ucitaj_uredjaje()
        if self.reload_callback:
            self.reload_callback()

    def _brisi_uredjaj(self, uid: int):
        if QMessageBox.question(self, "Potvrda", "Obrisati uređaj?") != QMessageBox.StandardButton.Yes:
            return
        brisi_uredjaj(uid)
        self._ucitaj_uredjaje()
        if self.reload_callback:
            self.reload_callback()

    # ── TAB LOGOVI ─────────────────────────────────────────────

    def _tab_logovi(self) -> QWidget:
        from PySide6.QtWidgets import QPlainTextEdit
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(6)

        # Filter row
        f_row = QHBoxLayout()
        f_row.addWidget(QLabel("Filter (datum):"))
        self._entry_filter = QLineEdit()
        self._entry_filter.setPlaceholderText("2024-01-01")
        self._entry_filter.setFixedWidth(120)
        f_row.addWidget(self._entry_filter)

        btn_fil = QPushButton("Filtriraj")
        btn_fil.setFixedWidth(80)
        btn_fil.clicked.connect(self._ucitaj_logove)
        f_row.addWidget(btn_fil)

        btn_sve = QPushButton("Sve")
        btn_sve.setFixedWidth(60)
        btn_sve.clicked.connect(lambda: (self._entry_filter.clear(), self._ucitaj_logove()))
        f_row.addWidget(btn_sve)
        f_row.addStretch()
        lay.addLayout(f_row)

        self._textbox_logovi = QPlainTextEdit()
        self._textbox_logovi.setReadOnly(True)
        lay.addWidget(self._textbox_logovi)

        self._ucitaj_logove()
        return w

    def _ucitaj_logove(self):
        filter_dat = self._entry_filter.text().strip() or None
        rows = ucitaj_logove(filter_dat)
        self._textbox_logovi.clear()
        for r in rows:
            vreme = r["vreme"][:19].replace("T", " ") if r["vreme"] else ""
            linija = f"{vreme}  [{r['radnik']}]  {r['uredjaj']}  →  {r['akcija']}\n"
            self._textbox_logovi.insertPlainText(linija)

    # ── TAB LOZINKA ────────────────────────────────────────────

    def _tab_lozinka(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)

        hdr = QLabel("Promjena admin lozinke")
        hdr.setStyleSheet("font-size: 14px; font-weight: 700; color: #e2e8f0;")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hdr)

        def row_input(label_text: str, echo=QLineEdit.EchoMode.Password) -> QLineEdit:
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl)
            entry = QLineEdit()
            entry.setEchoMode(echo)
            entry.setFixedWidth(220)
            lay.addWidget(entry, 0, Qt.AlignmentFlag.AlignCenter)
            return entry

        self._entry_nova_loz = row_input("Nova lozinka:")
        self._entry_ponovi_loz = row_input("Ponovi lozinku:")

        btn = QPushButton("Spremi lozinku")
        btn.setObjectName("btnSuccess")
        btn.setFixedWidth(180)
        btn.clicked.connect(self._promijeni_lozinku)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        return w

    def _promijeni_lozinku(self):
        nova = self._entry_nova_loz.text()
        ponovi = self._entry_ponovi_loz.text()
        if nova != ponovi:
            QMessageBox.warning(self, "Greška", "Lozinke se ne podudaraju!")
            return
        if len(nova) < 4:
            QMessageBox.warning(self, "Greška", "Lozinka mora imati najmanje 4 znaka!")
            return
        promijeni_lozinku(nova)
        QMessageBox.information(self, "Uspjeh", "Lozinka uspješno promijenjena!")
        self._entry_nova_loz.clear()
        self._entry_ponovi_loz.clear()
