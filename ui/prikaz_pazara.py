from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.pazar import dohvati_dashboard_smjene


_CARD_STYLE = (
    "QFrame { background: #111827; border: 1px solid #1e2433; "
    "border-radius: 8px; }"
)


class PrikazPazara(QDialog):
    def __init__(self, parent, smjena_id_getter: Callable):
        super().__init__(parent)
        self.setWindowTitle("Operativni dashboard smjene")
        self.resize(900, 680)
        self.smjena_id_getter = smjena_id_getter
        self._podaci: dict | None = None

        self._build_ui()

        # Timer mijenja samo prikaz trajanja i countdown iz keširanih podataka.
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._osvjezi_vremenske_podatke)
        self._timer.start()

        self.osvjezi_podatke()
        self.show()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(10)

        naslov_red = QHBoxLayout()
        naslov = QLabel("OPERATIVNI DASHBOARD")
        naslov.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #e2e8f0;"
        )
        naslov_red.addWidget(naslov)
        naslov_red.addStretch()
        self._lbl_smjena = QLabel("Nema otvorene smjene")
        self._lbl_smjena.setObjectName("dashboardShift")
        self._lbl_smjena.setStyleSheet("color: #94a3b8; font-size: 11px;")
        naslov_red.addWidget(self._lbl_smjena)
        lay.addLayout(naslov_red)

        finansije = QGridLayout()
        finansije.setSpacing(8)
        self._lbl_ukupno = self._metric_card(
            finansije, 0, "UKUPNO", "#f59e0b"
        )
        self._lbl_racunari = self._metric_card(
            finansije, 1, "RAČUNARI", "#22c55e"
        )
        self._lbl_artikli = self._metric_card(
            finansije, 2, "ARTIKLI UZ UREĐAJE", "#38bdf8"
        )
        self._lbl_sank = self._metric_card(
            finansije, 3, "ŠANK", "#a78bfa"
        )
        lay.addLayout(finansije)

        operativa = QGridLayout()
        operativa.setSpacing(8)
        self._lbl_aktivni = self._metric_card(
            operativa, 0, "AKTIVNI UREĐAJI", "#22c55e", "0"
        )
        self._lbl_slobodni = self._metric_card(
            operativa, 1, "SLOBODNI UREĐAJI", "#94a3b8", "0"
        )
        self._lbl_prepaid = self._metric_card(
            operativa, 2, "PREPAID / PASS", "#38bdf8", "0"
        )
        self._lbl_artikli_broj = self._metric_card(
            operativa, 3, "PRODANI ARTIKLI*", "#a78bfa", "0"
        )
        lay.addLayout(operativa)

        trend = QFrame()
        trend.setStyleSheet(_CARD_STYLE)
        trend_lay = QHBoxLayout(trend)
        trend_lay.setContentsMargins(12, 7, 12, 7)
        trend_lay.addWidget(self._section_label("Kretanje pazara"))
        self._lbl_trend = QLabel("— nema naplata —")
        self._lbl_trend.setObjectName("dashboardTrend")
        self._lbl_trend.setStyleSheet(
            "color: #f59e0b; font-size: 17px; letter-spacing: 2px;"
        )
        trend_lay.addWidget(self._lbl_trend, 1, Qt.AlignmentFlag.AlignCenter)
        self._lbl_transakcije = QLabel("0 transakcija")
        self._lbl_transakcije.setStyleSheet("color: #64748b; font-size: 10px;")
        trend_lay.addWidget(self._lbl_transakcije)
        lay.addWidget(trend)

        detalji = QHBoxLayout()
        detalji.setSpacing(10)

        isticu_panel = self._table_panel("Uskoro ističu", ["Uređaj", "Tip", "Preostalo"])
        self._tbl_isticu = isticu_panel.layout().itemAt(1).widget()
        detalji.addWidget(isticu_panel, 1)

        top_panel = self._table_panel(
            "Top 5 artikala uz uređaje", ["Artikal", "Količina", "Iznos"]
        )
        self._tbl_top = top_panel.layout().itemAt(1).widget()
        detalji.addWidget(top_panel, 1)
        lay.addLayout(detalji, 1)

        trans_panel = self._table_panel(
            "Posljednjih 5 naplata", ["Vrijeme", "Uređaj", "Tip", "Iznos"]
        )
        self._tbl_posljednje = trans_panel.layout().itemAt(1).widget()
        trans_panel.setMinimumHeight(185)
        lay.addWidget(trans_panel, 1)

        dno = QHBoxLayout()
        napomena = QLabel("* Količina je dostupna za naplaćene artikle uz uređaje; šank čuva zbirni iznos.")
        napomena.setStyleSheet("color: #475569; font-size: 9px;")
        dno.addWidget(napomena)
        dno.addStretch()
        btn = QPushButton("Zatvori")
        btn.clicked.connect(self.close)
        dno.addWidget(btn)
        lay.addLayout(dno)

    def _metric_card(
        self,
        layout: QGridLayout,
        kolona: int,
        naslov: str,
        boja: str,
        pocetna_vrijednost: str = "0.00 KM",
    ) -> QLabel:
        frame = QFrame()
        frame.setStyleSheet(_CARD_STYLE)
        frame_lay = QVBoxLayout(frame)
        frame_lay.setContentsMargins(12, 8, 12, 8)
        frame_lay.setSpacing(2)
        lbl_naslov = QLabel(naslov)
        lbl_naslov.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 600;")
        lbl_vrijednost = QLabel(pocetna_vrijednost)
        lbl_vrijednost.setObjectName(f"dashboardMetric{kolona}")
        lbl_vrijednost.setStyleSheet(
            f"color: {boja}; font-size: 17px; font-weight: 700;"
        )
        frame_lay.addWidget(lbl_naslov)
        frame_lay.addWidget(lbl_vrijednost)
        layout.addWidget(frame, 0, kolona)
        return lbl_vrijednost

    @staticmethod
    def _section_label(tekst: str) -> QLabel:
        lbl = QLabel(tekst)
        lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        return lbl

    def _table_panel(self, naslov: str, kolone: list[str]) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(_CARD_STYLE)
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(10, 8, 10, 8)
        panel_lay.setSpacing(5)
        panel_lay.addWidget(self._section_label(naslov))

        tabela = QTableWidget(0, len(kolone))
        tabela.setHorizontalHeaderLabels(kolone)
        tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabela.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tabela.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tabela.verticalHeader().setVisible(False)
        tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tabela.setShowGrid(False)
        panel_lay.addWidget(tabela)
        return panel

    def osvjezi_podatke(self):
        """Učitaj agregate iz servisa; poziva se na događaj, ne na timer."""
        smjena_id = self.smjena_id_getter()
        if smjena_id is None:
            self._postavi_prazno_stanje()
            return

        self._podaci = dohvati_dashboard_smjene(smjena_id)
        p = self._podaci
        self._lbl_ukupno.setText(f"{p['ukupno']:.2f} KM")
        self._lbl_racunari.setText(f"{p['racunari']:.2f} KM")
        self._lbl_artikli.setText(f"{p['artikli']:.2f} KM")
        self._lbl_sank.setText(f"{p['sank']:.2f} KM")
        self._lbl_aktivni.setText(str(p["aktivni_uredjaji"]))
        self._lbl_slobodni.setText(str(p["slobodni_uredjaji"]))
        self._lbl_prepaid.setText(str(p["aktivne_prepaid_pass"]))
        self._lbl_artikli_broj.setText(str(p["broj_prodanih_artikala"]))
        self._lbl_transakcije.setText(
            f"{p['broj_transakcija']} transakcija"
        )
        self._lbl_trend.setText(self._sparkline(p["kretanje_pazara"]))

        self._popuni_tabelu(
            self._tbl_top,
            [
                (
                    red["naziv_artikla"],
                    str(red["kolicina"]),
                    f"{red['ukupno']:.2f} KM",
                )
                for red in p["top_artikli"]
            ],
        )
        self._popuni_tabelu(
            self._tbl_isticu,
            [
                (
                    red["uredjaj"],
                    red["tip"],
                    self._format_sekundi(red["preostalo_sekundi"]),
                )
                for red in p["uskoro_isticu"]
            ],
        )
        self._popuni_tabelu(
            self._tbl_posljednje,
            [
                (
                    self._format_vrijeme(red.get("vreme")),
                    red.get("uredjaj", ""),
                    red.get("tip_prodaje", ""),
                    f"{red.get('iznos', 0):.2f} KM",
                )
                for red in p["posljednje_transakcije"]
            ],
        )
        self._osvjezi_vremenske_podatke()

    # Kompatibilnost sa starim internim nazivom metode.
    _osvjezi = osvjezi_podatke

    def _postavi_prazno_stanje(self):
        self._podaci = None
        self._lbl_smjena.setText("Nema otvorene smjene")
        for lbl in (
            self._lbl_ukupno,
            self._lbl_racunari,
            self._lbl_artikli,
            self._lbl_sank,
        ):
            lbl.setText("0.00 KM")
        for lbl in (
            self._lbl_aktivni,
            self._lbl_slobodni,
            self._lbl_prepaid,
            self._lbl_artikli_broj,
        ):
            lbl.setText("0")
        self._lbl_transakcije.setText("0 transakcija")
        self._lbl_trend.setText("— nema naplata —")
        for tabela in (self._tbl_top, self._tbl_isticu, self._tbl_posljednje):
            tabela.setRowCount(0)

    def _osvjezi_vremenske_podatke(self):
        if not self._podaci:
            return
        sada = datetime.now()
        pocetak = self._parse_datetime(self._podaci.get("pocetak_smjene"))
        if pocetak is None:
            self._lbl_smjena.setText("Početak: — · Trajanje: —")
        else:
            trajanje = max(0, int((sada - pocetak).total_seconds()))
            self._lbl_smjena.setText(
                f"Početak: {pocetak:%d.%m. %H:%M} · "
                f"Trajanje: {self._format_sekundi(trajanje)}"
            )

        for red, podaci in enumerate(self._podaci.get("uskoro_isticu", [])):
            if red >= self._tbl_isticu.rowCount():
                break
            istek = self._parse_datetime(podaci.get("vreme_isteka"))
            if istek is None:
                continue
            preostalo = max(0, int((istek - sada).total_seconds()))
            self._tbl_isticu.item(red, 2).setText(
                self._format_sekundi(preostalo)
            )

    @staticmethod
    def _popuni_tabelu(tabela: QTableWidget, redovi: list[tuple]):
        tabela.setRowCount(len(redovi))
        for red, vrijednosti in enumerate(redovi):
            for kolona, vrijednost in enumerate(vrijednosti):
                tabela.setItem(red, kolona, QTableWidgetItem(str(vrijednost)))

    @staticmethod
    def _sparkline(kretanje: list[dict]) -> str:
        if not kretanje:
            return "— nema naplata —"
        znakovi = "▁▂▃▄▅▆▇█"
        maksimum = max(float(red["ukupno"]) for red in kretanje)
        if maksimum <= 0:
            return znakovi[0] * len(kretanje)
        return "".join(
            znakovi[min(len(znakovi) - 1, int(float(red["ukupno"]) / maksimum * (len(znakovi) - 1)))]
            for red in kretanje
        )

    @staticmethod
    def _format_vrijeme(vrijednost) -> str:
        datum = PrikazPazara._parse_datetime(vrijednost)
        return datum.strftime("%H:%M:%S") if datum else "—"

    @staticmethod
    def _format_sekundi(sekunde: int) -> str:
        sekunde = max(0, int(sekunde))
        sati, ostatak = divmod(sekunde, 3600)
        minute, sekunde = divmod(ostatak, 60)
        return f"{sati:02d}:{minute:02d}:{sekunde:02d}"

    @staticmethod
    def _parse_datetime(vrijednost):
        if not vrijednost:
            return None
        try:
            return datetime.fromisoformat(vrijednost)
        except (TypeError, ValueError):
            return None

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
