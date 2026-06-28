from __future__ import annotations
from datetime import datetime
from copy import deepcopy
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
    QPushButton, QProgressBar, QMessageBox, QDialog,
    QListWidget, QListWidgetItem, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from models.session_state import SessionState
from models.app_state import AppState
from models.artikal import Artikal
from constants import CIJENA_MINECRAFT


# status → (bar_color, badge_bg, badge_fg, icon_color, earning_color)
_STATUS_STYLE = {
    "slobodno":  ("#1e2433", "#1e2433", "#334155", "#334155", "#1e2d3d"),
    "u_radu":    ("#3b82f6", "#1e3a5f", "#60a5fa", "#3b82f6", "#e2e8f0"),
    "pass1":     ("#4ade80", "#14291a", "#4ade80", "#4ade80", "#4ade80"),
    "pass2":     ("#fb923c", "#2a1500", "#fb923c", "#fb923c", "#fb923c"),
    "minecraft": ("#22c55e", "#14291a", "#4ade80", "#22c55e", "#4ade80"),
    "ps5":       ("#8b5cf6", "#1a0f2e", "#a78bfa", "#8b5cf6", "#a78bfa"),
}

_BADGE_TEXT = {
    "slobodno":  "SLOBODNO",
    "u_radu":    "U RADU",
    "pass1":     "PASS 1",
    "pass2":     "PASS 2",
    "minecraft": "MINECRAFT",
}


def _tip_to_kljuc(tip_uredjaja: str, session_tip: Optional[str]) -> str:
    if session_tip is None:
        return "slobodno"
    mapa = {
        "neograniceno": "ps5" if tip_uredjaja == "PS5" else "u_radu",
        "prepaid":      "u_radu",
        "pass1":        "pass1",
        "pass2":        "pass2",
        "minecraft":    "minecraft",
    }
    return mapa.get(session_tip, "u_radu")


class UredjajKartica(QWidget):
    """
    Transparent wrapper:
        QVBoxLayout (0 margin, 0 spacing)
        ├── QFrame#deviceCard  — card with rounded corners
        └── QFrame#statusBar   — 3px colored bar, outside the rounded rect
    """
    pazar_changed = Signal()

    def __init__(
        self,
        ime: str,
        tip: str,
        cena: float,
        state: AppState,
        get_sve_uredjaje: Callable,
        parent=None,
    ):
        super().__init__(parent)
        self.setFixedWidth(160)

        self.ime = ime
        self.tip = tip.upper()
        self.cena = cena
        self.state = state
        self.get_sve_uredjaje = get_sve_uredjaje

        self.session: Optional[SessionState] = None
        self.kosarica: list = []

        # ── Outer layout ──────────────────────────────────────
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("deviceCard")
        outer.addWidget(self._card)

        self._status_bar = QFrame()
        self._status_bar.setObjectName("statusBar")
        self._status_bar.setFixedHeight(3)
        self._status_bar.setStyleSheet("background: #1e2433;")
        outer.addWidget(self._status_bar)

        self._build_ui()

    # ── Build card content ─────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self._card)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(3)

        self._lbl_icon = QLabel("🖥" if self.tip != "PS5" else "🎮")
        self._lbl_icon.setObjectName("cardIcon")
        self._lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._lbl_icon)

        lbl_name = QLabel(self.ime)
        lbl_name.setObjectName("cardName")
        lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(lbl_name)

        self._lbl_badge = QLabel("SLOBODNO")
        self._lbl_badge.setObjectName("badge")
        self._lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._lbl_badge, 0, Qt.AlignmentFlag.AlignCenter)

        self._lbl_earning = QLabel("--")
        self._lbl_earning.setObjectName("cardEarning")
        self._lbl_earning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._lbl_earning)

        self._lbl_timer = QLabel("--:--")
        self._lbl_timer.setObjectName("cardTimer")
        self._lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._lbl_timer)

        self._progress = QProgressBar()
        self._progress.setObjectName("cardProgress")
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.hide()
        root.addWidget(self._progress)

        self._lbl_kosarica = QLabel("")
        self._lbl_kosarica.setObjectName("cardKosarica")
        self._lbl_kosarica.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._lbl_kosarica)

        root.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._btn_start = QPushButton("START")
        self._btn_start.setObjectName("btnStart")
        self._btn_start.clicked.connect(self.start_sesiju)

        self._btn_naplati = QPushButton("NAPLATI")
        self._btn_naplati.setObjectName("btnNaplati")
        self._btn_naplati.setEnabled(False)
        self._btn_naplati.clicked.connect(self.naplati)

        btn_row.addWidget(self._btn_start)
        btn_row.addWidget(self._btn_naplati)
        root.addLayout(btn_row)

        self._btn_prebaci = QPushButton("↔ PREBACI")
        self._btn_prebaci.setObjectName("btnPrebaci")
        self._btn_prebaci.clicked.connect(self.prebaci)
        self._btn_prebaci.hide()
        root.addWidget(self._btn_prebaci)

    # ── Refresh ────────────────────────────────────────────────

    def osvjezi(self):
        smjena_ok = self.state.trenutna_smjena_id is not None

        if self.session is None:
            self._apply_style("slobodno", _STATUS_STYLE["slobodno"])
            self._lbl_earning.setText("--")
            self._lbl_timer.setText("--:--")
            self._lbl_timer.setObjectName("cardTimer")
            self._lbl_timer.style().unpolish(self._lbl_timer)
            self._lbl_timer.style().polish(self._lbl_timer)
            self._lbl_kosarica.setText("")
            self._progress.hide()
            self._btn_start.setEnabled(smjena_ok)
            self._btn_naplati.setEnabled(False)
            self._btn_prebaci.hide()
            return

        tip = self.session.tip
        kljuc = _tip_to_kljuc(self.tip, tip)
        self._apply_style(kljuc, _STATUS_STYLE.get(kljuc, _STATUS_STYLE["u_radu"]))

        timer_txt = self.session.formatiraj_timer()
        self._lbl_timer.setText(timer_txt)
        self._lbl_timer.setObjectName("cardTimerActive")
        self._lbl_timer.style().unpolish(self._lbl_timer)
        self._lbl_timer.style().polish(self._lbl_timer)

        if tip in ("neograniceno", "minecraft"):
            rate = CIJENA_MINECRAFT if tip == "minecraft" else self.cena
            iznos = self.session.elapsed_sekundi() / 3600 * rate
            self._lbl_earning.setText(f"{iznos:.2f} KM")
        elif tip in ("prepaid", "pass1"):
            preostalo = self.session.formatiraj_preostalo()
            self._lbl_earning.setText(f"⏳ {preostalo}" if preostalo else "--")
        else:
            self._lbl_earning.setText("")

        if tip in ("prepaid", "pass1"):
            self._progress.show()
            self._progress.setValue(int(self.session.progres_prepaid() * 1000))
        else:
            self._progress.hide()

        if self.kosarica:
            total = sum(a.ukupno() for a in self.kosarica)
            self._lbl_kosarica.setText(f"🛒 {len(self.kosarica)} × {total:.2f} KM")
        else:
            self._lbl_kosarica.setText("")

        self._btn_start.setEnabled(False)
        self._btn_naplati.setEnabled(smjena_ok)
        self._btn_prebaci.setVisible(True)
        self._btn_prebaci.setEnabled(smjena_ok)

        if self.session.je_istekao():
            self._lbl_badge.setText("⚠ ISTEKLO!")
            self._lbl_badge.setStyleSheet(
                "background: #7f1d1d; color: #f87171; border-radius: 8px; padding: 2px 8px;"
            )

    def _apply_style(self, kljuc: str, style: tuple):
        bar_c, badge_bg, badge_fg, icon_c, earn_c = style
        self._status_bar.setStyleSheet(
            f"background: {bar_c}; min-height: 3px; max-height: 3px;"
        )
        self._lbl_badge.setText(_BADGE_TEXT.get(kljuc, kljuc.upper()))
        self._lbl_badge.setStyleSheet(
            f"background: {badge_bg}; color: {badge_fg}; border-radius: 8px; padding: 2px 8px;"
        )
        self._lbl_icon.setStyleSheet(f"color: {icon_c}; font-size: 22px;")
        self._lbl_earning.setStyleSheet(f"color: {earn_c};")

    # ── Actions ────────────────────────────────────────────────

    def start_sesiju(self):
        if self.state.trenutna_smjena_id is None:
            QMessageBox.information(self.window(), "Info", "Nema otvorene smjene.")
            return
        if self.session is not None:
            return

        from ui.dijalog_start import IzborStartaDijalog
        dlg = IzborStartaDijalog(self.window(), self.tip, self.cena)
        dlg.exec()
        if dlg.rezultat is None:
            return

        rezultat = dlg.rezultat
        tip = rezultat["tip"]
        self.session = SessionState(
            vreme_starta=datetime.now(),
            limit_sekundi=rezultat.get("limit_sekundi"),
            is_prepaid=(tip == "prepaid"),
            is_pass2=(tip == "pass2"),
            is_minecraft=(tip == "minecraft"),
            tip=tip,
        )
        self.kosarica = []

        smjena_id = self.state.trenutna_smjena_id
        radnik = self.state.ime_radnika

        if tip in ("prepaid", "pass1", "pass2") and rezultat["iznos"] > 0:
            from services.pazar import start_sesija_prepaid
            start_sesija_prepaid(self.ime, rezultat["iznos"], smjena_id, tip)
            self.pazar_changed.emit()

        from services.logger import upisi_log
        upisi_log(smjena_id, radnik, self.ime, f"START — {tip.upper()}")
        self.osvjezi()

    def naplati(self):
        if self.state.trenutna_smjena_id is None:
            QMessageBox.information(self.window(), "Info", "Nema otvorene smjene.")
            return
        if self.session is None:
            return

        smjena_id = self.state.trenutna_smjena_id
        radnik = self.state.ime_radnika

        from services.pazar import naplati_uredjaj
        iznos = naplati_uredjaj(self.ime, self.session, self.kosarica, self.cena, smjena_id)

        from services.logger import upisi_log
        upisi_log(smjena_id, radnik, self.ime,
                  f"NAPLATA — {self.session.tip.upper()} — {iznos:.2f} KM")

        self.session = None
        self.kosarica = []
        self.pazar_changed.emit()
        self.osvjezi()

    def prebaci(self):
        if self.session is None:
            return

        svi = self.get_sve_uredjaje()
        slobodni = [u for u in svi if u.ime != self.ime and u.session is None]
        if not slobodni:
            QMessageBox.information(self.window(), "Info", "Nema slobodnih uređaja.")
            return

        dlg = _IzborUredjajaDlg(self.window(), [u.ime for u in slobodni])
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.odabrano is None:
            return

        cilj = next((u for u in slobodni if u.ime == dlg.odabrano), None)
        if cilj is None:
            return

        cilj.session = deepcopy(self.session)
        cilj.kosarica = deepcopy(self.kosarica)

        smjena_id = self.state.trenutna_smjena_id
        radnik = self.state.ime_radnika
        from services.logger import upisi_log
        upisi_log(smjena_id, radnik, self.ime, f"PRIJENOS → {cilj.ime}")

        self.session = None
        self.kosarica = []
        self.osvjezi()
        cilj.osvjezi()

    def dodaj_u_kosaricu(self, artikal: Artikal):
        for a in self.kosarica:
            if a.naziv == artikal.naziv:
                a.kolicina += artikal.kolicina
                self.osvjezi()
                return
        self.kosarica.append(deepcopy(artikal))
        self.osvjezi()

        smjena_id = self.state.trenutna_smjena_id
        from services.pazar import dodaj_artikal_na_uredjaj
        dodaj_artikal_na_uredjaj(smjena_id, self.ime, artikal.naziv,
                                  artikal.kolicina, artikal.cijena)


class _IzborUredjajaDlg(QDialog):
    def __init__(self, parent, opcije: list):
        super().__init__(parent)
        self.setWindowTitle("Prebaci sesiju")
        self.setFixedSize(260, 300)
        self.odabrano = None

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Odaberi slobodan uređaj:"))

        self._lista = QListWidget()
        for o in opcije:
            self._lista.addItem(QListWidgetItem(o))
        self._lista.itemDoubleClicked.connect(self._potvrdi)
        lay.addWidget(self._lista)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._potvrdi)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _potvrdi(self):
        item = self._lista.currentItem()
        if item:
            self.odabrano = item.text()
            self.accept()
