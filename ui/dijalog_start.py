from __future__ import annotations
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QLineEdit, QMessageBox,
)
from PySide6.QtCore import Qt

from constants import (
    CIJENA_MINECRAFT,
    PASS1_PLACENIH_SATI, PASS1_DOBIJENIH_SATI,
    PASS2_PLACENIH_SATI, PASS2_ULAZ_OD, PASS2_ULAZ_DO,
)


class IzborStartaDijalog(QDialog):
    def __init__(self, parent, tip_uredjaja: str = "PC", cena_po_satu: float = 2.0):
        super().__init__(parent)
        self.setWindowTitle("Odaberi tip starta")
        self.setFixedSize(420, 340)
        self.setModal(True)

        self.tip_uredjaja = tip_uredjaja.upper()
        self.cena_po_satu = cena_po_satu
        self.rezultat: Optional[dict] = None

        self._build_ui()

    # ── Build ──────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        naslov = QLabel("Odaberi tip starta")
        naslov.setStyleSheet("font-size: 15px; font-weight: 700; color: #e2e8f0;")
        naslov.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(naslov)

        self._tabs = QTabWidget()
        lay.addWidget(self._tabs, 1)

        # Always present
        self._tabs.addTab(self._tab_neograniceno(), "Neograničeno")
        self._tabs.addTab(self._tab_unaprijed(),    "Unaprijed")

        # PC only
        if self.tip_uredjaja == "PC":
            self._tabs.addTab(self._tab_pass1(),    "Pass 1")
            self._tabs.addTab(self._tab_pass2(),    "Pass 2")
            self._tabs.addTab(self._tab_minecraft(), "Minecraft")

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_ok = QPushButton("✓ Pokreni")
        btn_ok.setObjectName("btnPrimary")
        btn_ok.clicked.connect(self._potvrdi)

        btn_cancel = QPushButton("✕ Otkaži")
        btn_cancel.setObjectName("btnDanger")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

    def _tab_neograniceno(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lbl = QLabel(
            f"Neograničeno trajanje\n"
            f"Cijena: {self.cena_po_satu:.2f} KM/h\n"
            f"Naplata pri kraju sesije."
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #94a3b8; font-size: 13px; line-height: 1.6;")
        lay.addWidget(lbl, 1, Qt.AlignmentFlag.AlignCenter)
        return w

    def _tab_unaprijed(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)

        lbl = QLabel("Uplati iznos → dobije odgovarajuće vrijeme")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        lay.addWidget(lbl)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(QLabel("Iznos (KM):"))
        self._entry_prepaid = QLineEdit()
        self._entry_prepaid.setPlaceholderText("npr. 5.00")
        self._entry_prepaid.setFixedWidth(100)
        row.addWidget(self._entry_prepaid)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        return w

    def _tab_pass1(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        cijena = PASS1_PLACENIH_SATI * self.cena_po_satu
        tekst = (
            f"Plati {PASS1_PLACENIH_SATI}h → dobije {PASS1_DOBIJENIH_SATI}h\n"
            f"Cijena: {cijena:.2f} KM\n"
            f"Progress bar prikazuje preostalo."
        )
        lbl = QLabel(tekst)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #4ade80; font-size: 13px; line-height: 1.6;")
        lay.addWidget(lbl, 1, Qt.AlignmentFlag.AlignCenter)
        return w

    def _tab_pass2(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        cijena = PASS2_PLACENIH_SATI * self.cena_po_satu
        tekst = (
            f"Plati {PASS2_PLACENIH_SATI}h → igra do kraja smjene\n"
            f"Ulaz: {PASS2_ULAZ_OD}:00 – {PASS2_ULAZ_DO}:00\n"
            f"Cijena: {cijena:.2f} KM"
        )
        lbl = QLabel(tekst)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #fb923c; font-size: 13px; line-height: 1.6;")
        lay.addWidget(lbl, 1, Qt.AlignmentFlag.AlignCenter)
        return w

    def _tab_minecraft(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        tekst = (
            f"Pass Minecraft\n"
            f"Fiksna cijena: {CIJENA_MINECRAFT:.2f} KM/h\n"
            f"Naplata po provedenom vremenu."
        )
        lbl = QLabel(tekst)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #22c55e; font-size: 13px; line-height: 1.6;")
        lay.addWidget(lbl, 1, Qt.AlignmentFlag.AlignCenter)
        return w

    # ── Confirm ────────────────────────────────────────────────

    def _potvrdi(self):
        tab_name = self._tabs.tabText(self._tabs.currentIndex())

        if tab_name == "Neograničeno":
            self.rezultat = {"tip": "neograniceno", "iznos": 0.0, "limit_sekundi": None}

        elif tab_name == "Unaprijed":
            try:
                iznos = float(self._entry_prepaid.text().replace(",", "."))
                if iznos <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "Greška", "Unesite validan iznos (npr. 5.00)")
                return
            limit_sek = int((iznos / self.cena_po_satu) * 3600)
            self.rezultat = {"tip": "prepaid", "iznos": iznos, "limit_sekundi": limit_sek}

        elif tab_name == "Pass 1":
            iznos = PASS1_PLACENIH_SATI * self.cena_po_satu
            limit_sek = PASS1_DOBIJENIH_SATI * 3600
            self.rezultat = {"tip": "pass1", "iznos": iznos, "limit_sekundi": limit_sek}

        elif tab_name == "Pass 2":
            sad = datetime.now().hour
            if not (PASS2_ULAZ_OD <= sad < PASS2_ULAZ_DO):
                QMessageBox.warning(
                    self, "Greška",
                    f"Pass 2 dostupan samo između {PASS2_ULAZ_OD}:00 i {PASS2_ULAZ_DO}:00!"
                )
                return
            iznos = PASS2_PLACENIH_SATI * self.cena_po_satu
            self.rezultat = {"tip": "pass2", "iznos": iznos, "limit_sekundi": None}

        elif tab_name == "Minecraft":
            self.rezultat = {"tip": "minecraft", "iznos": 0.0, "limit_sekundi": None}

        self.accept()
