from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget


SAT_SIRINA = 90
NAZIV_SIRINA = 110
ZAGLAVLJE_VISINA = 38
RED_VISINA = 46

_STATUS_STIL = {
    "rezervisano": "background:#1e3a5f;color:#93c5fd;border:1px solid #2563eb;",
    "stigao": "background:#14532d;color:#86efac;border:1px solid #16a34a;",
    "zavrseno": "background:#1e293b;color:#94a3b8;border:1px solid #334155;",
    "otkazano": "background:#292524;color:#a8a29e;border:1px solid #44403c;",
    "no_show": "background:#451a03;color:#fdba74;border:1px solid #9a3412;",
}


def _vrijednost(red, kljuc, default=None):
    try:
        return red[kljuc]
    except (KeyError, IndexError, TypeError):
        return default


class RezervacijeTimeline(QWidget):
    blok_clicked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.blokovi: list[QPushButton] = []
        self._datum = date.today()
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)
        self.set_podaci([], [], self._datum)

    def set_podaci(self, uredjaji: list, rezervacije: list, datum: date):
        self._datum = datum
        prethodni = self._scroll.takeWidget()
        if prethodni is not None:
            prethodni.deleteLater()
        self.blokovi = []

        pocetak_sata = 10
        if rezervacije:
            najranije = min(
                datetime.fromisoformat(red["pocetak"]) for red in rezervacije
            )
            pocetak_sata = min(pocetak_sata, najranije.hour)
        kraj_sata = 24
        trajanje_sati = kraj_sata - pocetak_sata

        platno = QWidget()
        platno.setObjectName("timelineCanvas")
        platno.setMinimumSize(
            NAZIV_SIRINA + trajanje_sati * SAT_SIRINA + 20,
            ZAGLAVLJE_VISINA + max(1, len(uredjaji)) * RED_VISINA + 10,
        )
        self._scroll.setWidget(platno)

        if not uredjaji:
            prazno = QLabel("Nema uređaja za prikaz", platno)
            prazno.setStyleSheet("color:#64748b;padding:12px;")
            prazno.move(12, ZAGLAVLJE_VISINA + 8)
            prazno.adjustSize()
            return

        rezervacije_po_uredjaju: dict[int, list] = {}
        for red in rezervacije:
            rezervacije_po_uredjaju.setdefault(red["uredjaj_id"], []).append(red)

        for sat in range(pocetak_sata, kraj_sata + 1):
            x = NAZIV_SIRINA + (sat - pocetak_sata) * SAT_SIRINA
            oznaka = QLabel(f"{sat:02d}:00" if sat < 24 else "24:00", platno)
            oznaka.setStyleSheet("color:#64748b;font-size:9px;")
            oznaka.setGeometry(x - 18, 6, 44, 20)
            linija = QLabel(platno)
            linija.setStyleSheet("background:#1e2433;")
            linija.setGeometry(
                x, ZAGLAVLJE_VISINA - 5, 1,
                max(1, len(uredjaji)) * RED_VISINA,
            )

        for indeks, uredjaj in enumerate(uredjaji):
            y = ZAGLAVLJE_VISINA + indeks * RED_VISINA
            naziv = QLabel(uredjaj["ime"], platno)
            naziv.setStyleSheet("color:#94a3b8;font-weight:600;padding-left:8px;")
            naziv.setGeometry(0, y, NAZIV_SIRINA - 6, RED_VISINA - 1)
            linija = QLabel(platno)
            linija.setStyleSheet("background:#171d29;")
            linija.setGeometry(0, y + RED_VISINA - 1, platno.minimumWidth(), 1)

            for red in rezervacije_po_uredjaju.get(uredjaj["id"], []):
                pocetak = datetime.fromisoformat(red["pocetak"])
                kraj = datetime.fromisoformat(red["kraj"])
                start_min = max(0, (pocetak.hour - pocetak_sata) * 60 + pocetak.minute)
                end_min = min(
                    trajanje_sati * 60,
                    (kraj.hour - pocetak_sata) * 60 + kraj.minute,
                )
                x = NAZIV_SIRINA + round(start_min / 60 * SAT_SIRINA)
                sirina = max(36, round((end_min - start_min) / 60 * SAT_SIRINA))
                grupa_id = _vrijednost(red, "grupa_id")
                velicina = _vrijednost(red, "grupa_velicina")
                tekst = red["ime_gosta"]
                if grupa_id is not None:
                    tekst = f"Grupa {tekst} ({velicina})"
                blok = QPushButton(tekst, platno)
                blok.setToolTip(
                    f"{pocetak:%H:%M}–{kraj:%H:%M} · {red['status']}"
                )
                blok.setProperty("rezervacija_id", red["id"])
                blok.setProperty("grupa_id", grupa_id)
                blok.setGeometry(x + 2, y + 7, sirina - 4, RED_VISINA - 14)
                blok.setStyleSheet(
                    _STATUS_STIL.get(red["status"], _STATUS_STIL["rezervisano"])
                    + "border-radius:4px;padding:2px;font-size:9px;text-align:left;"
                )
                blok.clicked.connect(
                    lambda _checked=False, rezervacija=red:
                    self.blok_clicked.emit(rezervacija)
                )
                self.blokovi.append(blok)
