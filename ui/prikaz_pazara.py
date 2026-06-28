from __future__ import annotations
from typing import Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QGridLayout,
)
from PySide6.QtCore import Qt, QTimer


class PrikazPazara(QDialog):
    def __init__(self, parent, smjena_id_getter: Callable):
        super().__init__(parent)
        self.setWindowTitle("Pazar smjene")
        self.resize(540, 560)
        self.smjena_id_getter = smjena_id_getter

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._osvjezi)
        self._timer.start()

        self._osvjezi()
        self.show()

    # ── Build ──────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        naslov = QLabel("💰  PAZAR SMJENE")
        naslov.setStyleSheet("font-size: 18px; font-weight: 700; color: #e2e8f0;")
        naslov.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(naslov)

        # Summary frame
        sumarni = QFrame()
        sumarni.setStyleSheet(
            "QFrame { background: #111827; border: 1px solid #1e2433; border-radius: 8px; }"
        )
        sum_lay = QHBoxLayout(sumarni)
        sum_lay.setContentsMargins(16, 10, 16, 10)

        self._lbl_racunari = QLabel("Računari: 0.00 KM")
        self._lbl_racunari.setStyleSheet("color: #94a3b8; font-size: 13px;")

        self._lbl_sank = QLabel("Šank: 0.00 KM")
        self._lbl_sank.setStyleSheet("color: #94a3b8; font-size: 13px;")

        self._lbl_ukupno = QLabel("UKUPNO: 0.00 KM")
        self._lbl_ukupno.setStyleSheet("color: #f59e0b; font-size: 15px; font-weight: 700;")

        sum_lay.addWidget(self._lbl_racunari)
        sum_lay.addWidget(self._lbl_sank)
        sum_lay.addStretch()
        sum_lay.addWidget(self._lbl_ukupno)
        lay.addWidget(sumarni)

        # Header label
        hdr = QLabel("Transakcije")
        hdr.setStyleSheet("color: #475569; font-size: 12px; font-weight: 600;")
        lay.addWidget(hdr)

        # Table header
        col_hdr = QFrame()
        col_hdr.setStyleSheet("background: #1e2433; border-radius: 4px;")
        col_hdr_lay = QHBoxLayout(col_hdr)
        col_hdr_lay.setContentsMargins(8, 4, 8, 4)
        for txt, w in [("Vrijeme", 130), ("Uređaj", 110), ("Tip", 100), ("Iznos", 80)]:
            lbl = QLabel(txt)
            lbl.setFixedWidth(w)
            lbl.setStyleSheet("color: #475569; font-size: 10px; font-weight: 600;")
            col_hdr_lay.addWidget(lbl)
        col_hdr_lay.addStretch()
        lay.addWidget(col_hdr)

        # Scroll area for transactions
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(0, 0, 0, 0)
        self._content_lay.setSpacing(1)
        self._content_lay.addStretch()
        self._scroll.setWidget(self._content)
        lay.addWidget(self._scroll, 1)

        btn = QPushButton("Zatvori")
        btn.clicked.connect(self.close)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignRight)

    # ── Refresh ────────────────────────────────────────────────

    def _osvjezi(self):
        smjena_id = self.smjena_id_getter()
        if smjena_id is None:
            return

        from services.pazar import dohvati_pazar_smjene
        podaci = dohvati_pazar_smjene(smjena_id)

        self._lbl_racunari.setText(f"Računari: {podaci['racunari']:.2f} KM")
        self._lbl_sank.setText(f"Šank: {podaci['sank']:.2f} KM")
        self._lbl_ukupno.setText(f"UKUPNO: {podaci['ukupno']:.2f} KM")

        # Clear rows
        while self._content_lay.count() > 1:
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        boje = ["#111827", "#0e1117"]
        for i, t in enumerate(podaci["transakcije"]):
            row = QFrame()
            row.setStyleSheet(
                f"QFrame {{ background: {boje[i % 2]}; border-radius: 3px; }}"
            )
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(8, 3, 8, 3)

            vreme = t["vreme"][:16].replace("T", " ") if t.get("vreme") else ""
            for txt, w in [
                (vreme, 130),
                (t.get("uredjaj", ""), 110),
                (t.get("tip_prodaje", ""), 100),
                (f"{t.get('iznos', 0):.2f} KM", 80),
            ]:
                lbl = QLabel(txt)
                lbl.setFixedWidth(w)
                lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
                row_lay.addWidget(lbl)
            row_lay.addStretch()

            self._content_lay.insertWidget(self._content_lay.count() - 1, row)

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
