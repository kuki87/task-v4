from __future__ import annotations
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QTabWidget, QComboBox, QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from models.artikal import Artikal
from models.app_state import AppState
from services.artikli import ucitaj_artikle


class BocniPanel(QFrame):
    pazar_changed = Signal()

    def __init__(
        self,
        smjena_id_getter: Callable,
        radnik_getter: Callable,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("bocniPanel")
        self.setFixedWidth(210)

        self.smjena_id_getter = smjena_id_getter
        self.radnik_getter = radnik_getter

        self.sank_kosarica: list[Artikal] = []
        self._artikli_db: list = []

        self._build_ui()

    # ── Build ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Naslov
        naslov = QLabel("☕  ŠANK")
        naslov.setObjectName("bocniNaslov")
        naslov.setAlignment(Qt.AlignmentFlag.AlignCenter)
        naslov.setContentsMargins(0, 12, 0, 8)
        root.addWidget(naslov)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setObjectName("bocniTab")

        # Tab 1 — Šank
        sank_tab = self._build_sank_tab()
        self._tabs.addTab(sank_tab, "Šank")

        # Tab 2 — Uređaji (add articles to active device)
        uredjaji_tab = self._build_uredjaji_tab()
        self._tabs.addTab(uredjaji_tab, "Uređaji")

        root.addWidget(self._tabs, 1)

    def _build_sank_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        # Article list
        lbl_art = QLabel("Artikli")
        lbl_art.setStyleSheet("color: #475569; font-size: 10px; font-weight: 600;")
        lay.addWidget(lbl_art)

        self._scroll_artikli = QScrollArea()
        self._scroll_artikli.setWidgetResizable(True)
        self._scroll_artikli.setFixedHeight(150)
        self._art_widget = QWidget()
        self._art_layout = QVBoxLayout(self._art_widget)
        self._art_layout.setContentsMargins(0, 0, 0, 0)
        self._art_layout.setSpacing(2)
        self._art_layout.addStretch()
        self._scroll_artikli.setWidget(self._art_widget)
        lay.addWidget(self._scroll_artikli)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #1e2433;")
        lay.addWidget(div)

        # Cart
        lbl_cart = QLabel("Košarica")
        lbl_cart.setStyleSheet("color: #475569; font-size: 10px; font-weight: 600;")
        lay.addWidget(lbl_cart)

        self._scroll_kosarica = QScrollArea()
        self._scroll_kosarica.setWidgetResizable(True)
        self._scroll_kosarica.setFixedHeight(120)
        self._kos_widget = QWidget()
        self._kos_layout = QVBoxLayout(self._kos_widget)
        self._kos_layout.setContentsMargins(0, 0, 0, 0)
        self._kos_layout.setSpacing(2)
        self._kos_layout.addStretch()
        self._scroll_kosarica.setWidget(self._kos_widget)
        lay.addWidget(self._scroll_kosarica)

        # Total
        self._lbl_ukupno_sank = QLabel("Ukupno: 0.00 KM")
        self._lbl_ukupno_sank.setObjectName("bocniUkupno")
        self._lbl_ukupno_sank.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._lbl_ukupno_sank)

        # NAPLATI ŠANK
        self._btn_naplati_sank = QPushButton("💰 NAPLATI ŠANK")
        self._btn_naplati_sank.setObjectName("btnNaplatiSank")
        self._btn_naplati_sank.clicked.connect(self._naplati_sank)
        lay.addWidget(self._btn_naplati_sank)

        return w

    def _build_uredjaji_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        lbl = QLabel("Dodaj na uređaj:")
        lbl.setStyleSheet("color: #475569; font-size: 10px; font-weight: 600;")
        lay.addWidget(lbl)

        self._combo_uredjaj = QComboBox()
        self._combo_uredjaj.setStyleSheet("font-size: 11px;")
        lay.addWidget(self._combo_uredjaj)

        # Same article list (shared access)
        lbl_art2 = QLabel("Artikli")
        lbl_art2.setStyleSheet("color: #475569; font-size: 10px; font-weight: 600;")
        lay.addWidget(lbl_art2)

        self._scroll_artikli2 = QScrollArea()
        self._scroll_artikli2.setWidgetResizable(True)
        self._scroll_artikli2.setFixedHeight(130)
        self._art_widget2 = QWidget()
        self._art_layout2 = QVBoxLayout(self._art_widget2)
        self._art_layout2.setContentsMargins(0, 0, 0, 0)
        self._art_layout2.setSpacing(2)
        self._art_layout2.addStretch()
        self._scroll_artikli2.setWidget(self._art_widget2)
        lay.addWidget(self._scroll_artikli2)

        # Device cart
        lbl_cart2 = QLabel("Košarica uređaja")
        lbl_cart2.setStyleSheet("color: #475569; font-size: 10px; font-weight: 600;")
        lay.addWidget(lbl_cart2)

        self._scroll_kosarica2 = QScrollArea()
        self._scroll_kosarica2.setWidgetResizable(True)
        self._scroll_kosarica2.setFixedHeight(100)
        self._kos_widget2 = QWidget()
        self._kos_layout2 = QVBoxLayout(self._kos_widget2)
        self._kos_layout2.setContentsMargins(0, 0, 0, 0)
        self._kos_layout2.setSpacing(2)
        self._kos_layout2.addStretch()
        self._scroll_kosarica2.setWidget(self._kos_widget2)
        lay.addWidget(self._scroll_kosarica2)

        lay.addStretch()
        return w

    # ── Load data ──────────────────────────────────────────────

    def ucitaj_artikle(self):
        self._artikli_db = ucitaj_artikle()
        self._render_artikli(self._art_layout, self._art_widget, cilj="sank")
        self._render_artikli(self._art_layout2, self._art_widget2, cilj="uredjaj")

    def _render_artikli(self, layout: QVBoxLayout, parent: QWidget, cilj: str):
        # Remove all except stretch
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for a in self._artikli_db:
            row = QHBoxLayout()
            row.setSpacing(4)

            lbl = QLabel(a["naziv"])
            lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            row.addWidget(lbl)

            lbl_c = QLabel(f"{a['cijena']:.2f}")
            lbl_c.setStyleSheet("color: #475569; font-size: 10px;")
            lbl_c.setFixedWidth(34)
            row.addWidget(lbl_c)

            btn = QPushButton("+")
            btn.setObjectName("btnAddArtikal")
            smjena_ok = self.smjena_id_getter() is not None
            btn.setEnabled(smjena_ok)
            naziv, cijena = a["naziv"], a["cijena"]
            if cilj == "sank":
                btn.clicked.connect(lambda _, n=naziv, c=cijena: self._dodaj_sank(n, c))
            else:
                btn.clicked.connect(lambda _, n=naziv, c=cijena: self._dodaj_uredjaj(n, c))
            row.addWidget(btn)

            container = QWidget()
            container.setLayout(row)
            layout.insertWidget(layout.count() - 1, container)

    # ── Osvježi ────────────────────────────────────────────────

    def osvjezi(self, kartice: list):
        smjena_ok = self.smjena_id_getter() is not None
        self._btn_naplati_sank.setEnabled(smjena_ok)

        # Update device combo
        aktivan = self._combo_uredjaj.currentText()
        self._combo_uredjaj.blockSignals(True)
        self._combo_uredjaj.clear()
        for k in kartice:
            if k.session is not None:
                self._combo_uredjaj.addItem(k.ime)
        self._combo_uredjaj.blockSignals(False)

        # Try to restore selection
        idx = self._combo_uredjaj.findText(aktivan)
        if idx >= 0:
            self._combo_uredjaj.setCurrentIndex(idx)

        # Refresh + buttons enable state
        self._refresh_btn_states(self._art_layout, smjena_ok)
        self._refresh_btn_states(self._art_layout2, smjena_ok)

        self._osvjezi_kosaricu_sank()
        self._osvjezi_kosaricu_uredjaj(kartice)

    def _refresh_btn_states(self, layout: QVBoxLayout, enabled: bool):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                for child in item.widget().findChildren(QPushButton):
                    child.setEnabled(enabled)

    def _osvjezi_kosaricu_sank(self):
        while self._kos_layout.count() > 1:
            item = self._kos_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        ukupno = 0.0
        for artikal in self.sank_kosarica:
            ukupno += artikal.ukupno()
            row = self._cart_row(artikal, lambda a=artikal: self._ukloni_sank_artikal(a))
            self._kos_layout.insertWidget(self._kos_layout.count() - 1, row)

        self._lbl_ukupno_sank.setText(f"Ukupno: {ukupno:.2f} KM")

    def _osvjezi_kosaricu_uredjaj(self, kartice: list):
        while self._kos_layout2.count() > 1:
            item = self._kos_layout2.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        ime = self._combo_uredjaj.currentText()
        kartica = next((k for k in kartice if k.ime == ime), None)
        stavke = kartica.kosarica if kartica else []

        for artikal in stavke:
            row = self._cart_row(artikal, lambda a=artikal, k=kartica: self._ukloni_uredjaj(a, k))
            self._kos_layout2.insertWidget(self._kos_layout2.count() - 1, row)

    def _cart_row(self, artikal: Artikal, remove_fn) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        lbl = QLabel(f"{artikal.naziv} ×{artikal.kolicina}")
        lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(lbl)

        lbl_t = QLabel(f"{artikal.ukupno():.2f}")
        lbl_t.setStyleSheet("color: #f59e0b; font-size: 10px;")
        lbl_t.setFixedWidth(34)
        row.addWidget(lbl_t)

        btn = QPushButton("-")
        btn.setObjectName("btnRemoveArtikal")
        btn.clicked.connect(remove_fn)
        row.addWidget(btn)

        return container

    # ── Actions ────────────────────────────────────────────────

    def _dodaj_sank(self, naziv: str, cijena: float):
        if self.smjena_id_getter() is None:
            QMessageBox.information(self.window(), "Info", "Nema otvorene smjene.")
            return
        for a in self.sank_kosarica:
            if a.naziv == naziv:
                a.kolicina += 1
                self._osvjezi_kosaricu_sank()
                return
        self.sank_kosarica.append(Artikal(naziv=naziv, cijena=cijena, kolicina=1))
        self._osvjezi_kosaricu_sank()

    def _dodaj_uredjaj(self, naziv: str, cijena: float):
        if self.smjena_id_getter() is None:
            QMessageBox.information(self.window(), "Info", "Nema otvorene smjene.")
            return
        ime = self._combo_uredjaj.currentText()
        if not ime:
            QMessageBox.information(self.window(), "Info", "Nema aktivnih uređaja.")
            return
        # Find kartica via get_kartice from main window
        # BocniPanel doesn't store kartice ref, get via combo selection
        # Article is sent via main window's kartice list
        # Use the signal approach: emit a request to add article to device
        # For now, call directly via parent's kartice list
        parent = self.parent()
        while parent and not hasattr(parent, 'kartice'):
            parent = parent.parent()
        if parent is None:
            return
        kartica = next((k for k in parent.kartice if k.ime == ime), None)
        if kartica:
            kartica.dodaj_u_kosaricu(Artikal(naziv=naziv, cijena=cijena, kolicina=1))

    def _ukloni_sank_artikal(self, artikal: Artikal):
        if artikal.kolicina > 1:
            artikal.kolicina -= 1
        else:
            self.sank_kosarica = [a for a in self.sank_kosarica if a.naziv != artikal.naziv]
        self._osvjezi_kosaricu_sank()

    def _ukloni_uredjaj(self, artikal: Artikal, kartica):
        if kartica is None:
            return
        if artikal.kolicina > 1:
            artikal.kolicina -= 1
        else:
            kartica.kosarica = [a for a in kartica.kosarica if a.naziv != artikal.naziv]
        kartica.osvjezi()

    def _naplati_sank(self):
        if self.smjena_id_getter() is None:
            QMessageBox.information(self.window(), "Info", "Nema otvorene smjene.")
            return
        if not self.sank_kosarica:
            QMessageBox.information(self.window(), "Info", "Šank košarica je prazna.")
            return

        smjena_id = self.smjena_id_getter()
        radnik = self.radnik_getter()

        from services.pazar import naplati_sank_kosaricu
        ukupno = naplati_sank_kosaricu(self.sank_kosarica, smjena_id)

        from services.logger import upisi_log
        upisi_log(smjena_id, radnik, "Šank", f"NAPLATA ŠANK — {ukupno:.2f} KM")

        self.sank_kosarica = []
        self._osvjezi_kosaricu_sank()
        self.pazar_changed.emit()
        QMessageBox.information(self.window(), "Naplata", f"Šank naplaćen: {ukupno:.2f} KM")
