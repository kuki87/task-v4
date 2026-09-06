from __future__ import annotations
import sys
import os
from datetime import datetime
from typing import Optional

# Ensure project root is on sys.path regardless of how/where the app is launched
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QComboBox,
    QMessageBox, QInputDialog, QLineEdit, QSizePolicy, QDialog,
    QDialogButtonBox, QPlainTextEdit,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor

from database.db import inicijalizuj_bazu
from services.uredjaji import seed_uredjaje_ako_prazno, ucitaj_uredjaje, dohvati_aktivne_sesije
from services.smjena import otvori_smjenu, zatvori_smjenu, dohvati_aktivnu_smjenu
from services.pazar import dohvati_pazar_smjene
from services.logger import upisi_log, log
from models.app_state import AppState
from models.session_state import SessionState
import services.logger  # aktivira global exception handler


class GlavniProzor:
    """Thin wrapper: creates QApplication + MainWindow, exposes run()."""

    def __init__(self):
        existing = QApplication.instance()
        self._qapp: QApplication = existing if isinstance(existing, QApplication) else QApplication(sys.argv)

        # Load QSS
        qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
        try:
            self._qapp.setStyleSheet(open(qss_path, encoding="utf-8").read())
        except FileNotFoundError:
            pass

        self._window = _MainWindow()
        self._window.showMaximized()

    def run(self):
        from database.db import zatvori_bazu
        self._qapp.aboutToQuit.connect(zatvori_bazu)
        sys.exit(self._qapp.exec())


# ─────────────────────────────────────────────────────────────────────────────

class _MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Caffe & Gaming Zone")
        self.setMinimumSize(900, 600)

        self.state = AppState()
        self.kartice: list = []
        self._svi_uredjaji: list = []
        self._session_cache: dict = {}
        self._pazar_dlg: Optional[QDialog] = None

        inicijalizuj_bazu()
        self._seed_uredjaje()
        self._build_ui()
        self._ucitaj_uredjaje()
        self._provjeri_smjenu()

        # 1-second refresh timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ── Seed ──────────────────────────────────────────────────

    def _seed_uredjaje(self):
        seed_uredjaje_ako_prazno([
            ("PC1", 2.0, "PC", "Classic"), ("PC2", 2.0, "PC", "Classic"),
            ("PC3", 2.0, "PC", "Classic"), ("PC4", 2.0, "PC", "Classic"),
            ("PC5", 2.0, "PC", "Classic"), ("PC6", 2.0, "PC", "Classic"),
            ("PS5-1", 3.0, "PS5", "PS5"), ("PS5-2", 3.0, "PS5", "PS5"),
        ])

    # ── Build UI ──────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        root_lay.addWidget(self._build_topbar())

        # Content row
        content = QWidget()
        content_lay = QHBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        # Scroll area for cards
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setObjectName("cardsScroll")
        self._cards_content = QWidget()
        self._cards_content.setObjectName("cardsContent")
        self._cards_layout = QVBoxLayout(self._cards_content)
        self._cards_layout.setContentsMargins(12, 12, 12, 12)
        self._cards_layout.setSpacing(4)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._cards_content)
        content_lay.addWidget(self._scroll, 1)

        # Bocni panel
        from ui.bocni_panel import BocniPanel
        self._bocni = BocniPanel(
            smjena_id_getter=lambda: self.state.trenutna_smjena_id,
            radnik_getter=lambda: self.state.ime_radnika,
            parent=self,
        )
        self._bocni.pazar_changed.connect(self._osvjezi_status_bar)
        content_lay.addWidget(self._bocni)

        root_lay.addWidget(content, 1)

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(42)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 16, 0)
        lay.setSpacing(4)

        # Logo
        logo = QLabel("⚡  Caffe & Gaming")
        logo.setStyleSheet("font-size: 13px; font-weight: 700; color: #e2e8f0;")
        lay.addWidget(logo)
        lay.addSpacing(16)

        # Nav buttons
        for txt, slot in [
            ("Smjena",  self._meni_smjena),
            ("Pazar",   self._otvori_pazar),
            ("Admin",   self._otvori_admin),
        ]:
            btn = QPushButton(txt)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        lay.addStretch()

        # Right-side status labels
        self._lbl_pazar = QLabel("")
        self._lbl_pazar.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: 600;")
        lay.addWidget(self._lbl_pazar)

        sep1 = QLabel("│")
        sep1.setStyleSheet("color: #1e2433; font-size: 11px;")
        lay.addWidget(sep1)

        self._lbl_aktivno = QLabel("")
        self._lbl_aktivno.setStyleSheet("color: #94a3b8; font-size: 11px;")
        lay.addWidget(self._lbl_aktivno)

        sep2 = QLabel("│")
        sep2.setStyleSheet("color: #1e2433; font-size: 11px;")
        lay.addWidget(sep2)

        self._lbl_radnik = QLabel("Nema smjene")
        self._lbl_radnik.setStyleSheet("color: #ef4444; font-size: 11px;")
        lay.addWidget(self._lbl_radnik)

        return bar

    # ── Load / Render ──────────────────────────────────────────

    def _ucitaj_uredjaje(self):
        aktivne_prije = {
            k.ime for k in self.kartice
            if k.session is not None or k.kosarica
        }
        self._svi_uredjaji = ucitaj_uredjaje()
        imena_sada = {u["ime"] for u in self._svi_uredjaji}
        nestali = sorted(aktivne_prije - imena_sada)

        self._render_kartice()
        self._bocni.ucitaj_artikle()

        if nestali:
            for ime in nestali:
                log.error(
                    f"Uređaj '{ime}' uklonjen dok je imao aktivnu sesiju ili "
                    "nenaplaćenu košaricu, stanje je odbačeno."
                )
            QMessageBox.warning(
                self, "Izgubljene sesije",
                "Sljedeći uređaji su uklonjeni dok su imali aktivnu sesiju "
                "ili nenaplaćenu košaricu:\n\n  • "
                + "\n  • ".join(nestali)
                + "\n\nTo vrijeme i ti artikli se više ne mogu naplatiti."
            )

    def _render_kartice(self):
        from ui.kartica_uredjaja import UredjajKartica
        from collections import defaultdict

        # Save sessions from currently visible cards
        for k in self.kartice:
            self._session_cache[k.ime] = (k.session, k.kosarica)

        # Drop cache entries for devices that no longer exist
        imena_u_bazi = {u["ime"] for u in self._svi_uredjaji}
        for ime in list(self._session_cache):
            if ime not in imena_u_bazi:
                self._session_cache.pop(ime, None)

        # Clear layout
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
        self.kartice.clear()

        filtrirani = list(self._svi_uredjaji)

        # Calculate cards per row (window width minus bocni panel and padding)
        avail_w = max(200, self.width() - 210 - 32)
        max_per_row = max(1, avail_w // (160 + 14))
        self._max_per_row = max_per_row

        PC_GRUPE = ["Classic", "VIP", "Super VIP"]
        po_grupi: dict = defaultdict(list)
        for u in filtrirani:
            po_grupi[u["grupa"]].append(u)

        def zona_header(tekst: str, color: str = "#6366f1"):
            lbl = QLabel(tekst)
            lbl.setObjectName("zonaHeader")
            lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 700; padding: 6px 0 2px 0;")
            self._cards_layout.addWidget(lbl)

        def grupa_header(tekst: str):
            lbl = QLabel(f"  {tekst}")
            lbl.setObjectName("grupaHeader")
            self._cards_layout.addWidget(lbl)

        def dodaj_kartice(lista: list):
            row_lay: Optional[QHBoxLayout] = None
            for i, u in enumerate(lista):
                if i % max_per_row == 0:
                    row_widget = QWidget()
                    row_lay = QHBoxLayout(row_widget)
                    row_lay.setContentsMargins(0, 0, 0, 0)
                    row_lay.setSpacing(10)
                    row_lay.setAlignment(Qt.AlignmentFlag.AlignLeft)
                    self._cards_layout.addWidget(row_widget)

                kartica = UredjajKartica(
                    ime=u["ime"],
                    tip=u["tip"],
                    cena=u["cena"],
                    state=self.state,
                    get_sve_uredjaje=lambda: self.kartice,
                )
                kartica.pazar_changed.connect(self._osvjezi_status_bar)
                if row_lay is not None:
                    row_lay.addWidget(kartica)
                self.kartice.append(kartica)

        # PC ZONA
        pc_prisutne = [g for g in PC_GRUPE if po_grupi.get(g)]
        if pc_prisutne:
            zona_header("⚡  PC ZONA", "#6366f1")
            for g in PC_GRUPE:
                if po_grupi.get(g):
                    grupa_header(g)
                    dodaj_kartice(po_grupi[g])

        # PS5 ZONA
        if po_grupi.get("PS5"):
            zona_header("🎮  PS5 ZONA", "#8b5cf6")
            dodaj_kartice(po_grupi["PS5"])

        # Fallback
        poznate = set(PC_GRUPE) | {"PS5"}
        for g, uredjaji in po_grupi.items():
            if g not in poznate and uredjaji:
                zona_header(f"📌  {g}", "#475569")
                dodaj_kartice(uredjaji)

        if not filtrirani:
            lbl = QLabel("Nema uređaja u bazi")
            lbl.setStyleSheet("color: #334155; font-size: 13px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._cards_layout.addWidget(lbl)

        # Restore sessions
        for k in self.kartice:
            if k.ime in self._session_cache:
                k.session, k.kosarica = self._session_cache[k.ime]
            k.osvjezi()

    # ── Timer tick ─────────────────────────────────────────────

    def _tick(self):
        for k in self.kartice:
            k.osvjezi()
        self._bocni.osvjezi(self.kartice)
        self._osvjezi_status_bar()

    # ── Status bar ─────────────────────────────────────────────

    def _osvjezi_status_bar(self):
        smjena_id = self.state.trenutna_smjena_id
        if smjena_id is None:
            self._lbl_radnik.setText("Nema smjene")
            self._lbl_radnik.setStyleSheet("color: #ef4444; font-size: 11px;")
            self._lbl_aktivno.setText("")
            self._lbl_pazar.setText("")
            return
        podaci = dohvati_pazar_smjene(smjena_id)
        aktivni = sum(1 for k in self.kartice if k.session is not None)
        ukupno = len(self.kartice)
        self._lbl_radnik.setText(f"● {self.state.ime_radnika}")
        self._lbl_radnik.setStyleSheet("color: #22c55e; font-size: 11px; font-weight: 600;")
        self._lbl_aktivno.setText(f"{aktivni}/{ukupno} aktivno")
        self._lbl_pazar.setText(f"{podaci['ukupno']:.2f} KM")

    # ── Smjena ─────────────────────────────────────────────────

    def _provjeri_smjenu(self):
        aktivna = dohvati_aktivnu_smjenu()
        if not aktivna:
            return
        pocetak = aktivna["pocetak"]
        pocetak_txt = pocetak[:19].replace("T", " ") if pocetak else "—"
        odg = QMessageBox.question(
            self, "Otkrivena smjena",
            f"Pronađena otvorena smjena radnika: {aktivna['radnik'] or '—'}\n"
            f"Početak: {pocetak_txt}\n\n"
            "Nastaviti sa ovom smjenom?"
        )
        if odg == QMessageBox.StandardButton.Yes:
            self.state.postavi_smjenu(aktivna["id"], aktivna["radnik"])
            self._osvjezi_status_bar()
            self._obnovi_aktivne_sesije(aktivna["id"])
            for k in self.kartice:
                k.osvjezi()
            self._bocni.osvjezi(self.kartice)

    def _obnovi_aktivne_sesije(self, smjena_id: int):
        aktivne = dohvati_aktivne_sesije(smjena_id)
        for row in aktivne:
            kartica = next((k for k in self.kartice if k.ime == row["uredjaj"]), None)
            if kartica and kartica.session is None:
                tip = row["tip"] or "neograniceno"
                vreme = datetime.fromisoformat(row["vreme_starta"])
                kartica.session = SessionState(
                    vreme_starta=vreme, tip=tip,
                    is_prepaid=(tip == "prepaid"),
                    is_pass2=(tip == "pass2"),
                    is_minecraft=(tip == "minecraft"),
                )
                self._session_cache[kartica.ime] = (kartica.session, kartica.kosarica)
                kartica.osvjezi()

    def _otvori_smjenu_dijalog(self):
        if self.state.je_smjena_otvorena():
            QMessageBox.warning(
                self, "Upozorenje",
                f"Smjena je već otvorena!\n"
                f"Radnik: {self.state.ime_radnika}\n\n"
                "Zatvori trenutnu smjenu prije otvaranja nove."
            )
            return
        while True:
            ime, ok = QInputDialog.getText(self, "Nova smjena", "Unesite ime radnika:")
            if not ok:
                return
            ime = ime.strip()
            if ime:
                try:
                    smjena_id = otvori_smjenu(ime)
                except ValueError as e:
                    log.error(f"Otvaranje smjene odbijeno: {e}")
                    aktivna = dohvati_aktivnu_smjenu()
                    if aktivna is None:
                        QMessageBox.critical(self, "Greška", str(e))
                        return
                    pocetak = aktivna["pocetak"]
                    pocetak_txt = pocetak[:19].replace("T", " ") if pocetak else "—"
                    odg = QMessageBox.question(
                        self, "Smjena je već otvorena u bazi",
                        f"{e}\n\n"
                        f"Početak: {pocetak_txt}\n\n"
                        "Preuzeti tu smjenu i nastaviti rad?\n\n"
                        "(Ako odbiješ, nećeš moći otvoriti novu smjenu dok ova ne bude "
                        "zatvorena. Da bi je zatvorio, moraš je prvo preuzeti.)"
                    )
                    if odg == QMessageBox.StandardButton.Yes:
                        self.state.postavi_smjenu(aktivna["id"], aktivna["radnik"])
                        self._osvjezi_status_bar()
                        self._obnovi_aktivne_sesije(aktivna["id"])
                        for k in self.kartice:
                            k.osvjezi()
                        self._bocni.osvjezi(self.kartice)
                    return
                except Exception as e:
                    log.error(f"Otvaranje smjene nije uspjelo: {e}")
                    QMessageBox.critical(self, "Greška", f"Smjena nije otvorena:\n{e}")
                    return
                self.state.postavi_smjenu(smjena_id, ime)
                upisi_log(smjena_id, ime, "-", "OTVARANJE SMJENE")
                self._osvjezi_status_bar()
                return
            odg = QMessageBox.question(self, "Info", "Morate otvoriti smjenu. Pokušati ponovo?")
            if odg != QMessageBox.StandardButton.Yes:
                return

    def _meni_smjena(self):
        dlg = _DijalogSmjena(self)
        dlg.exec()
        if dlg.rezultat == "nova":
            self._otvori_smjenu_dijalog()
        elif dlg.rezultat == "zatvori":
            self._zatvori_smjenu()

    def _zatvori_smjenu(self):
        smjena_id = self.state.trenutna_smjena_id
        if smjena_id is None:
            QMessageBox.information(self, "Info", "Nema otvorene smjene.")
            return

        aktivne_sesije = {k.ime: k.session for k in self.kartice if k.session is not None}
        sank_kosarica = self._bocni.sank_kosarica

        upozorenja = []
        if aktivne_sesije:
            upozorenja.append(f"• {len(aktivne_sesije)} aktivnih sesija bit će prekinuto")
        if sank_kosarica:
            upozorenja.append(f"• Šank košarica ({len(sank_kosarica)} stavki) bit će izgubljena!")

        if upozorenja:
            poruka = "Upozorenja:\n" + "\n".join(upozorenja) + "\n\nNastaviti?"
            if QMessageBox.question(self, "Zatvaranje smjene", poruka) != QMessageBox.StandardButton.Yes:
                return

        podaci_pazara = dohvati_pazar_smjene(smjena_id)
        zatvori_smjenu(smjena_id, aktivne_sesije, sank_kosarica, podaci_pazara["ukupno"])
        upisi_log(smjena_id, self.state.ime_radnika, "-", "ZATVARANJE SMJENE")

        # Izvještaj
        podaci_izvj = {"preneseni_racunari": list(aktivne_sesije.keys())}
        try:
            from services.izvjestaj import generiši_tekstualni, generiši_pdf
            tekst = generiši_tekstualni(smjena_id, podaci_izvj)
            pdf_file = generiši_pdf(smjena_id, podaci_izvj)
            _PrikazIzvjestaja(self, tekst, pdf_file).exec()
        except Exception:
            pass

        # Reset
        self.state.zatvori_smjenu()
        self._session_cache.clear()
        for k in self.kartice:
            k.session = None
            k.kosarica = []
            k.osvjezi()
        self._bocni.sank_kosarica = []
        self._osvjezi_status_bar()

    # ── Pazar / Admin ──────────────────────────────────────────

    def _otvori_pazar(self):
        from ui.prikaz_pazara import PrikazPazara
        if self._pazar_dlg and not self._pazar_dlg.isHidden():
            self._pazar_dlg.raise_()
            return
        self._pazar_dlg = PrikazPazara(self, smjena_id_getter=lambda: self.state.trenutna_smjena_id)

    def _otvori_admin(self):
        from ui.admin_panel import AdminPanel
        panel = AdminPanel(self, reload_callback=self._ucitaj_uredjaje)
        if panel.auth_ok:
            panel.exec()

    # ── Resize event ───────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-render on resize only when cards per row actually changes
        if not (self.kartice or self._svi_uredjaji):
            return
        avail_w = max(200, self.width() - 210 - 32)
        novi_max = max(1, avail_w // (160 + 14))
        if novi_max == getattr(self, "_max_per_row", None):
            return
        self._render_kartice()


# ─────────────────────────────────────────────────────────────────────────────
# Helper dialogs
# ─────────────────────────────────────────────────────────────────────────────

class _DijalogSmjena(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Smjena")
        self.setFixedSize(280, 160)
        self.rezultat: Optional[str] = None

        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(24, 20, 24, 16)

        lbl = QLabel("Upravljanje smjenom")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)

        state = AppState()
        if state.je_smjena_otvorena():
            btn_akcija = QPushButton("Zatvori smjenu")
            btn_akcija.setObjectName("btnDanger")
            btn_akcija.clicked.connect(lambda: self._odaberi("zatvori"))
        else:
            btn_akcija = QPushButton("Otvori smjenu")
            btn_akcija.setObjectName("btnSuccess")
            btn_akcija.clicked.connect(lambda: self._odaberi("nova"))

        btn_akcija.setFixedHeight(36)
        lay.addWidget(btn_akcija)

        btn_cancel = QPushButton("Otkaži")
        btn_cancel.setFixedHeight(30)
        btn_cancel.clicked.connect(self.reject)
        lay.addWidget(btn_cancel)

    def _odaberi(self, opcija: str):
        self.rezultat = opcija
        self.accept()


class _PrikazIzvjestaja(QDialog):
    def __init__(self, parent, tekst: str, pdf_file: Optional[str]):
        super().__init__(parent)
        self.setWindowTitle("Izvještaj smjene")
        self.resize(580, 500)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)

        lbl = QLabel("Izvještaj zatvorene smjene")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)

        if pdf_file:
            lbl_pdf = QLabel(f"PDF snimljen: {pdf_file}")
            lbl_pdf.setStyleSheet("color: #22c55e; font-size: 11px;")
            lbl_pdf.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl_pdf)

        textbox = QPlainTextEdit()
        textbox.setReadOnly(True)
        textbox.setPlainText(tekst)
        lay.addWidget(textbox, 1)

        btn = QPushButton("Zatvori")
        btn.clicked.connect(self.accept)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignRight)
