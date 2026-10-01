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
from PySide6.QtGui import QFont, QColor, QKeySequence, QShortcut

from database.db import inicijalizuj_bazu
from services.uredjaji import seed_uredjaje_ako_prazno, ucitaj_uredjaje, dohvati_aktivne_sesije
from services.smjena import (
    otvori_smjenu, zatvori_smjenu, dohvati_aktivnu_smjenu, preuzmi_smjenu,
)
from services.pazar import dohvati_nenaplacene_artikle, dohvati_pazar_smjene
from services.logger import log
from models.app_state import AppState
from models.session_state import SessionState
from services.permissions import (
    ARTICLE_MANAGE, AUDIT_VIEW, DASHBOARD_VIEW, DEVICE_MANAGE, REPORT_VIEW,
    POS_USE, RESERVATION_MANAGE, SESSION_HISTORY_VIEW, SHIFT_CLOSE, SHIFT_OPEN,
    USER_MANAGE,
)
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
        inicijalizuj_bazu()
        self.state = AppState()
        self._window = None
        if self._prijavi_korisnika():
            self._otvori_glavni_prozor()
        else:
            QTimer.singleShot(0, self._qapp.quit)

    def _prijavi_korisnika(self) -> bool:
        from services.users import stanje_prvog_pokretanja
        from ui.login import FirstRunDijalog, LoginDijalog

        stanje = stanje_prvog_pokretanja()
        if stanje == "legacy_ostecen":
            QMessageBox.critical(
                None,
                "Oštećena autentikacija",
                "Legacy admin podaci su oštećeni. Automatski reset nije izvršen.",
            )
            return False
        if stanje in ("novi_admin", "migracija_legacy"):
            dlg = FirstRunDijalog(stanje)
        else:
            dlg = LoginDijalog()
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.korisnik is None:
            return False
        self.state.prijavi_korisnika(dlg.korisnik)
        return True

    def _otvori_glavni_prozor(self):
        self._window = _MainWindow()
        self._window.logout_requested.connect(self._odjava)
        self._window.showMaximized()

    def _odjava(self):
        from services.users import odjavi_korisnika

        stari = self._window
        if stari is not None:
            for naziv in ("_korisnici_dlg", "_audit_dlg"):
                dijalog = getattr(stari, naziv, None)
                if dijalog is not None:
                    dijalog.actor = None
                    dijalog.close()
            stari.hide()
        actor = self.state.trenutni_korisnik()
        if actor is not None:
            try:
                odjavi_korisnika(actor)
            except Exception as e:
                log.error(f"Audit odjave nije uspio: {e}")
        self.state.odjavi_korisnika()
        if stari is not None:
            stari.deleteLater()
        if self._prijavi_korisnika():
            self._otvori_glavni_prozor()
        else:
            self._qapp.quit()

    def run(self):
        from database.db import zatvori_bazu
        self._qapp.aboutToQuit.connect(zatvori_bazu)
        sys.exit(self._qapp.exec())


# ─────────────────────────────────────────────────────────────────────────────

class _MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Caffe & Gaming Zone")
        self.setMinimumSize(900, 600)

        self.state = AppState()
        self.kartice: list = []
        self._svi_uredjaji: list = []
        self._session_cache: dict = {}
        self._pazar_dlg: Optional[QDialog] = None
        self._historija_dlg: Optional[QDialog] = None
        self._izvjestaji_dlg: Optional[QDialog] = None
        self._rezervacije_dlg: Optional[QDialog] = None
        self._korisnici_dlg: Optional[QDialog] = None
        self._audit_dlg: Optional[QDialog] = None
        self._smjena_pocetak: Optional[datetime] = None
        self._operativna_upozorenja: list[tuple[str, Optional[str]]] = []
        self._aktivni_alert_uredjaj: Optional[str] = None

        inicijalizuj_bazu()
        self._seed_uredjaje()
        self._build_ui()
        self._ucitaj_uredjaje()
        self._provjeri_smjenu()
        self._osvjezi_status_bar()

        # 1-second refresh timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # Rezervacije se osvježavaju po događaju i laganim minutnim timerom.
        self._rezervacije_timer = QTimer(self)
        self._rezervacije_timer.setInterval(60_000)
        self._rezervacije_timer.timeout.connect(self._osvjezi_rezervacije_kartica)
        self._rezervacije_timer.start()

    # ── Seed ──────────────────────────────────────────────────

    def _seed_uredjaje(self):
        if not self.state.ima_dozvolu(DEVICE_MANAGE):
            return
        seed_uredjaje_ako_prazno([
            ("PC1", 2.0, "PC", "Classic"), ("PC2", 2.0, "PC", "Classic"),
            ("PC3", 2.0, "PC", "Classic"), ("PC4", 2.0, "PC", "Classic"),
            ("PC5", 2.0, "PC", "Classic"), ("PC6", 2.0, "PC", "Classic"),
            ("PS5-1", 3.0, "PS5", "PS5"), ("PS5-2", 3.0, "PS5", "PS5"),
        ], actor=self.state.trenutni_korisnik())

    # ── Build UI ──────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        root_lay.addWidget(self._build_topbar())

        # Role-aware navigacija, operativne kartice i postojeći quick POS.
        content = QWidget()
        content_lay = QHBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        content_lay.addWidget(self._build_navigation())

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
            actor_getter=self.state.trenutni_korisnik,
            parent=self,
        )
        self._bocni.pazar_changed.connect(self._pazar_promijenjen)
        content_lay.addWidget(self._bocni)

        root_lay.addWidget(content, 1)
        root_lay.addWidget(self._build_alert_bar())

        self._shortcut_refresh = QShortcut(QKeySequence("F5"), self)
        self._shortcut_refresh.activated.connect(self._refresh_trenutnog_prikaza)
        if self.state.ima_dozvolu(RESERVATION_MANAGE):
            self._shortcut_rezervacije = QShortcut(QKeySequence("Ctrl+R"), self)
            self._shortcut_rezervacije.activated.connect(self._otvori_rezervacije)

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(56)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 12, 0)
        lay.setSpacing(10)

        logo = QLabel("Caffe & Gaming Zone")
        logo.setObjectName("appTitle")
        lay.addWidget(logo)

        lay.addStretch()

        self._lbl_radnik = QLabel("")
        self._lbl_radnik.setObjectName("topStatus")
        lay.addWidget(self._lbl_radnik)

        self._lbl_smjena = QLabel("NEMA OTVORENE SMJENE")
        self._lbl_smjena.setObjectName("topShift")
        lay.addWidget(self._lbl_smjena)

        self._lbl_aktivno = QLabel("")
        self._lbl_aktivno.setObjectName("topStatus")
        lay.addWidget(self._lbl_aktivno)

        self._lbl_pazar = QLabel("Pazar: 0.00 KM")
        self._lbl_pazar.setObjectName("topRevenue")
        lay.addWidget(self._lbl_pazar)

        btn_odjava = QPushButton("Odjava")
        btn_odjava.setObjectName("btnLogout")
        btn_odjava.clicked.connect(self._potvrdi_odjavu)
        lay.addWidget(btn_odjava)
        self._nav_buttons = {"Odjava": btn_odjava}

        return bar

    def _build_navigation(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("navigationSidebar")
        panel.setFixedWidth(154)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 14, 10, 12)
        lay.setSpacing(4)

        def sekcija(naziv: str):
            lbl = QLabel(naziv)
            lbl.setObjectName("navSection")
            lay.addWidget(lbl)

        def stavka(naziv: str, slot, dozvola: Optional[str] = None):
            if dozvola is not None and not self.state.ima_dozvolu(dozvola):
                return
            btn = QPushButton(naziv)
            btn.setObjectName("navButton")
            btn.clicked.connect(slot)
            lay.addWidget(btn)
            self._nav_buttons[naziv] = btn

        sekcija("OPERATIVNO")
        stavka("Gaming", self._prikazi_gaming, POS_USE)
        if self.state.ima_dozvolu(SHIFT_OPEN) or self.state.ima_dozvolu(SHIFT_CLOSE):
            stavka("Smjena", self._meni_smjena)
        stavka("Rezervacije", self._otvori_rezervacije, RESERVATION_MANAGE)
        stavka("Dashboard", self._otvori_pazar, DASHBOARD_VIEW)

        if self.state.ima_dozvolu(SESSION_HISTORY_VIEW) or self.state.ima_dozvolu(REPORT_VIEW):
            lay.addSpacing(10)
            sekcija("ANALITIKA")
            stavka("Historija", self._otvori_historiju_sesija, SESSION_HISTORY_VIEW)
            stavka("Izvještaji", self._otvori_izvjestaje, REPORT_VIEW)

        if any(self.state.ima_dozvolu(p) for p in (
            DEVICE_MANAGE, ARTICLE_MANAGE, USER_MANAGE, AUDIT_VIEW
        )):
            lay.addSpacing(10)
            sekcija("ADMINISTRACIJA")
            if self.state.ima_dozvolu(DEVICE_MANAGE) or self.state.ima_dozvolu(ARTICLE_MANAGE):
                stavka("Admin", self._otvori_admin)
            stavka("Korisnici", self._otvori_korisnike, USER_MANAGE)
            stavka("Audit", self._otvori_audit, AUDIT_VIEW)

        lay.addStretch()
        return panel

    def _build_alert_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("alertBar")
        bar.setFixedHeight(34)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 3, 12, 3)
        self._btn_alert = QPushButton("")
        self._btn_alert.setObjectName("alertButton")
        self._btn_alert.clicked.connect(self._fokusiraj_alert)
        lay.addWidget(self._btn_alert)
        bar.hide()
        self._alert_bar = bar
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
                upozorenje = (f"⚠ {ime}: izgubljeno aktivno stanje uređaja", ime)
                if upozorenje not in self._operativna_upozorenja:
                    self._operativna_upozorenja.append(upozorenje)
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

        max_per_row = self._izracunaj_broj_kolona()
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
                    uredjaj_id=u["id"],
                    grupa=u["grupa"],
                )
                kartica.pazar_changed.connect(self._pazar_promijenjen)
                kartica.session_changed.connect(self._session_event)
                kartica.dodaj_artikal_requested.connect(
                    self._fokusiraj_artikle_uredjaja
                )
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
        self._osvjezi_rezervacije_kartica()

    def _izracunaj_broj_kolona(self) -> int:
        sirina = self._scroll.viewport().width() if hasattr(self, "_scroll") else 0
        if sirina < 200:
            sirina = self.width() - 154 - 210 - 32
        return max(1, max(200, sirina) // (184 + 12))

    # ── Timer tick ─────────────────────────────────────────────

    def _tick(self):
        for k in self.kartice:
            k.osvjezi()
        self._bocni.osvjezi_ako_promijenjeno(self.kartice)
        self._osvjezi_trajanje_smjene()
        self._osvjezi_alert_bar()

    def _osvjezi_rezervacije_kartica(self):
        from services.rezervacije import dohvati_naredne_rezervacije_uredjaja

        kartice_po_id = {
            k.uredjaj_id: k for k in self.kartice if k.uredjaj_id is not None
        }
        rezervacije = dohvati_naredne_rezervacije_uredjaja(kartice_po_id)
        for uredjaj_id, kartica in kartice_po_id.items():
            kartica.postavi_narednu_rezervaciju(rezervacije.get(uredjaj_id))
        self._osvjezi_alert_bar()

    # ── Status bar ─────────────────────────────────────────────

    def _osvjezi_status_bar(self):
        self._lbl_radnik.setText(
            f"Korisnik: {self.state.ime or self.state.username} ({self.state.rola})"
        )
        smjena_id = self.state.trenutna_smjena_id
        if smjena_id is None:
            self._smjena_pocetak = None
            self._lbl_smjena.setText("NEMA OTVORENE SMJENE")
            self._lbl_aktivno.setText(f"0/{len(self.kartice)} aktivno")
            self._lbl_pazar.setText("Pazar: 0.00 KM")
            return
        podaci = dohvati_pazar_smjene(smjena_id)
        aktivni = sum(1 for k in self.kartice if k.session is not None)
        ukupno = len(self.kartice)
        self._lbl_aktivno.setText(f"{aktivni}/{ukupno} aktivno")
        self._lbl_pazar.setText(f"Pazar: {podaci['ukupno']:.2f} KM")
        self._osvjezi_trajanje_smjene()

    def _osvjezi_trajanje_smjene(self):
        smjena_id = self.state.trenutna_smjena_id
        if smjena_id is None:
            return
        if self._smjena_pocetak is None:
            self._lbl_smjena.setText(f"Smjena #{smjena_id}")
            return
        trajanje = max(0, int((datetime.now() - self._smjena_pocetak).total_seconds()))
        sati, ostatak = divmod(trajanje, 3600)
        minute = ostatak // 60
        self._lbl_smjena.setText(
            f"Smjena #{smjena_id} · {self._smjena_pocetak:%H:%M} · {sati:02d}:{minute:02d}"
        )

    def _osvjezi_alert_bar(self):
        sada = datetime.now()
        alerti: list[tuple[int, str, Optional[str]]] = [
            (0, tekst, uredjaj) for tekst, uredjaj in self._operativna_upozorenja
        ]
        for kartica in self.kartice:
            rezervacija = kartica.naredna_rezervacija
            if rezervacija is not None:
                pocetak = datetime.fromisoformat(rezervacija["pocetak"])
                minuta = int((pocetak - sada).total_seconds() // 60)
                if -60 <= minuta <= 30:
                    kada = "u toku" if minuta < 0 else f"za {minuta} min"
                    alerti.append((
                        1 if minuta >= 10 else 0,
                        f"⚠ {kartica.ime}: rezervacija {kada} · {rezervacija['ime_gosta']}",
                        kartica.ime,
                    ))
            if kartica.session is not None and kartica.session.limit_sekundi is not None:
                preostalo = kartica.session.preostalo_sekundi()
                if preostalo is not None and preostalo <= 10 * 60:
                    minuta = max(0, (preostalo + 59) // 60)
                    tekst = (
                        f"⚠ {kartica.ime}: sesija je istekla"
                        if preostalo == 0
                        else f"⚠ {kartica.ime}: {kartica.session.tip} ističe za {minuta} min"
                    )
                    alerti.append((0, tekst, kartica.ime))

        if not alerti:
            self._aktivni_alert_uredjaj = None
            self._btn_alert.clearFocus()
            self._alert_bar.hide()
            return
        alerti.sort(key=lambda stavka: (stavka[0], stavka[1]))
        _, tekst, uredjaj = alerti[0]
        self._aktivni_alert_uredjaj = uredjaj
        dodatno = len(alerti) - 1
        self._btn_alert.setText(
            tekst if dodatno == 0 else f"{tekst}   (+{dodatno} upozorenja)"
        )
        self._alert_bar.show()

    def _fokusiraj_alert(self):
        kartica = next(
            (k for k in self.kartice if k.ime == self._aktivni_alert_uredjaj),
            None,
        )
        if kartica is not None:
            self._scroll.ensureWidgetVisible(kartica, 24, 24)
            kartica.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _session_event(self, uredjaj: str):
        kartica = next((k for k in self.kartice if k.ime == uredjaj), None)
        if kartica is not None:
            kartica.osvjezi()
        self._bocni.osvjezi_ako_promijenjeno(self.kartice)
        self._osvjezi_status_bar()
        self._osvjezi_alert_bar()

    def _fokusiraj_artikle_uredjaja(self, uredjaj: str):
        self._bocni.fokusiraj_uredjaj(uredjaj)

    def _refresh_trenutnog_prikaza(self):
        for kartica in self.kartice:
            kartica.osvjezi()
        self._osvjezi_rezervacije_kartica()
        self._bocni.osvjezi(self.kartice)
        self._pazar_promijenjen()

    def _prikazi_gaming(self):
        self._scroll.verticalScrollBar().setValue(0)
        self._scroll.setFocus()

    def _pazar_promijenjen(self):
        """Osvježi finansije i dashboard samo nakon poslovnog događaja."""
        self._osvjezi_status_bar()
        self._osvjezi_alert_bar()
        if self._pazar_dlg and not self._pazar_dlg.isHidden():
            osvjezi = getattr(self._pazar_dlg, "osvjezi_podatke", None)
            if osvjezi is not None:
                osvjezi()

    # ── Smjena ─────────────────────────────────────────────────

    def _provjeri_smjenu(self):
        aktivna = dohvati_aktivnu_smjenu()
        if not aktivna:
            self._smjena_pocetak = None
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
            actor = self.state.trenutni_korisnik()
            if aktivna.get("user_id") != self.state.user_id:
                try:
                    preuzmi_smjenu(aktivna["id"], actor)
                except Exception as e:
                    QMessageBox.critical(self, "Preuzimanje smjene", str(e))
                    return
            self.state.postavi_smjenu(aktivna["id"], self.state.ime)
            self._smjena_pocetak = datetime.fromisoformat(aktivna["pocetak"])
            self._pazar_promijenjen()
            self._obnovi_aktivne_sesije(aktivna["id"])
            for k in self.kartice:
                k.osvjezi()
            self._bocni.osvjezi(self.kartice)

    def _obnovi_aktivne_sesije(self, smjena_id: int):
        aktivne = dohvati_aktivne_sesije(smjena_id)
        nepostojeci_uredjaji = []
        for row in aktivne:
            kartica = next((k for k in self.kartice if k.ime == row["uredjaj"]), None)
            if kartica is None:
                nepostojeci_uredjaji.append(row["uredjaj"])
                upozorenje = (
                    f"⚠ {row['uredjaj']}: aktivna sesija nije obnovljena",
                    row["uredjaj"],
                )
                if upozorenje not in self._operativna_upozorenja:
                    self._operativna_upozorenja.append(upozorenje)
                log.error(
                    f"Aktivna sesija za uređaj '{row['uredjaj']}' nije obnovljena "
                    "jer uređaj više ne postoji."
                )
                continue
            if kartica.session is not None:
                continue

            tip = row["tip"] or "neograniceno"
            vreme = datetime.fromisoformat(row["vreme_starta"])
            kartica.session = SessionState(
                vreme_starta=vreme,
                limit_sekundi=row["limit_sekundi"],
                tip=tip,
                is_prepaid=(tip == "prepaid"),
                is_pass2=(tip == "pass2"),
                is_minecraft=(tip == "minecraft"),
            )
            kartica.kosarica = dohvati_nenaplacene_artikle(
                smjena_id, kartica.ime
            )
            self._session_cache[kartica.ime] = (kartica.session, kartica.kosarica)
            kartica.osvjezi()

        if nepostojeci_uredjaji:
            QMessageBox.warning(
                self,
                "Neobnovljene sesije",
                "U bazi postoje aktivne sesije za uređaje koji više ne postoje:\n\n"
                "  • " + "\n  • ".join(nepostojeci_uredjaji)
                + "\n\nZapisi su ostali u bazi i zahtijevaju ručnu provjeru.",
            )

    def _otvori_smjenu_dijalog(self):
        if self.state.je_smjena_otvorena():
            QMessageBox.warning(
                self, "Upozorenje",
                f"Smjena je već otvorena!\n"
                f"Radnik: {self.state.ime_radnika}\n\n"
                "Zatvori trenutnu smjenu prije otvaranja nove."
            )
            return
        actor = self.state.trenutni_korisnik()
        try:
            smjena_id = otvori_smjenu(actor)
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
                f"{e}\n\nPočetak: {pocetak_txt}\n\nPreuzeti smjenu?"
            )
            if odg == QMessageBox.StandardButton.Yes:
                preuzmi_smjenu(aktivna["id"], actor)
                self.state.postavi_smjenu(aktivna["id"], self.state.ime)
                self._smjena_pocetak = datetime.fromisoformat(aktivna["pocetak"])
                self._pazar_promijenjen()
                self._obnovi_aktivne_sesije(aktivna["id"])
                self._bocni.osvjezi(self.kartice)
            return
        except Exception as e:
            log.error(f"Otvaranje smjene nije uspjelo: {e}")
            QMessageBox.critical(self, "Greška", f"Smjena nije otvorena:\n{e}")
            return
        self.state.postavi_smjenu(smjena_id, self.state.ime)
        self._smjena_pocetak = datetime.now()
        self._pazar_promijenjen()

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

        aktivne_sesije = {
            k.ime: (k.session, k.kosarica, k.cena)
            for k in self.kartice
            if k.session is not None
        }
        sank_kosarica = self._bocni.sank_kosarica

        upozorenja = []
        if aktivne_sesije:
            upozorenja.append(
                f"• {len(aktivne_sesije)} aktivnih sesija bit će naplaćeno i prekinuto"
            )
        if sank_kosarica:
            upozorenja.append(f"• Šank košarica ({len(sank_kosarica)} stavki) bit će izgubljena!")

        if upozorenja:
            poruka = "Upozorenja:\n" + "\n".join(upozorenja) + "\n\nNastaviti?"
            if QMessageBox.question(self, "Zatvaranje smjene", poruka) != QMessageBox.StandardButton.Yes:
                return

        zatvori_smjenu(
            smjena_id, aktivne_sesije, sank_kosarica,
            actor=self.state.trenutni_korisnik(),
        )

        # Izvještaj
        podaci_izvj = {}
        try:
            from services.izvjestaj import generiši_tekstualni, generiši_pdf
            tekst = generiši_tekstualni(smjena_id, podaci_izvj)
            pdf_file = generiši_pdf(smjena_id, podaci_izvj)
            _PrikazIzvjestaja(self, tekst, pdf_file).exec()
        except Exception as e:
            log.error(f"Izvještaj smjene {smjena_id} nije generisan ili prikazan: {e}")
            QMessageBox.warning(
                self, "Greška izvještaja",
                "Smjena je uspješno zatvorena, ali izvještaj nije moguće "
                f"generisati ili prikazati.\n\nGreška: {e}"
            )

        # Reset
        self.state.zatvori_smjenu()
        self._smjena_pocetak = None
        self._session_cache.clear()
        for k in self.kartice:
            k.session = None
            k.kosarica = []
            k.osvjezi()
        self._bocni.sank_kosarica = []
        self._pazar_promijenjen()

    # ── Pazar / Admin ──────────────────────────────────────────

    def _otvori_pazar(self):
        from ui.prikaz_pazara import PrikazPazara
        if self._pazar_dlg and not self._pazar_dlg.isHidden():
            self._pazar_dlg.raise_()
            return
        self._pazar_dlg = PrikazPazara(self, smjena_id_getter=lambda: self.state.trenutna_smjena_id)

    def _otvori_historiju_sesija(self):
        from ui.historija_sesija import HistorijaSesijaDijalog
        if self._historija_dlg and not self._historija_dlg.isHidden():
            self._historija_dlg.raise_()
            return
        self._historija_dlg = HistorijaSesijaDijalog(self)

    def _otvori_rezervacije(self):
        from ui.rezervacije import RezervacijeDijalog
        if self._rezervacije_dlg and not self._rezervacije_dlg.isHidden():
            self._rezervacije_dlg.raise_()
            return
        self._rezervacije_dlg = RezervacijeDijalog(
            self,
            actor_getter=self.state.trenutni_korisnik,
            smjena_id_getter=lambda: self.state.trenutna_smjena_id,
        )
        self._rezervacije_dlg.rezervacije_changed.connect(
            self._osvjezi_rezervacije_kartica
        )
        self._rezervacije_dlg.show()

    def _otvori_izvjestaje(self):
        from ui.izvjestaji import IzvjestajiDijalog
        if self._izvjestaji_dlg and not self._izvjestaji_dlg.isHidden():
            self._izvjestaji_dlg.raise_()
            return
        self._izvjestaji_dlg = IzvjestajiDijalog(self)

    def _otvori_admin(self):
        from ui.admin_panel import AdminPanel
        panel = AdminPanel(
            self,
            self.state.trenutni_korisnik(),
            reload_callback=self._ucitaj_uredjaje,
        )
        if panel.auth_ok:
            panel.exec()

    def _otvori_korisnike(self):
        from ui.korisnici import KorisniciDijalog
        if self._korisnici_dlg and not self._korisnici_dlg.isHidden():
            self._korisnici_dlg.raise_()
            return
        self._korisnici_dlg = KorisniciDijalog(
            self.state.trenutni_korisnik(), self
        )
        self._korisnici_dlg.show()

    def _otvori_audit(self):
        from ui.audit import AuditDijalog
        if self._audit_dlg and not self._audit_dlg.isHidden():
            self._audit_dlg.raise_()
            return
        self._audit_dlg = AuditDijalog(self.state.trenutni_korisnik(), self)
        self._audit_dlg.show()

    def _potvrdi_odjavu(self):
        if QMessageBox.question(
            self, "Odjava", "Odjaviti trenutnog korisnika? Aktivna smjena ostaje otvorena."
        ) == QMessageBox.StandardButton.Yes:
            self.logout_requested.emit()

    # ── Resize event ───────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-render on resize only when cards per row actually changes
        if not (self.kartice or self._svi_uredjaji):
            return
        novi_max = self._izracunaj_broj_kolona()
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
