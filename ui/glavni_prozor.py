import customtkinter as ctk
from tkinter import messagebox, simpledialog
from typing import Dict, List, Optional

import services.logger  # Aktivira global exception handler

from database.db import inicijalizuj_bazu
from services.uredjaji import (
    seed_uredjaje_ako_prazno, ucitaj_uredjaje, dohvati_aktivne_sesije
)
from models.app_state import AppState
from models.session_state import SessionState
from models.artikal import Artikal
from services.smjena import (
    otvori_smjenu, zatvori_smjenu, dohvati_aktivnu_smjenu
)
from services.pazar import dohvati_pazar_smjene
from services.logger import upisi_log

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class GlavniProzor:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Caffe & Gaming Zone")
        self.root.geometry("1080x680")
        self.root.minsize(900, 600)

        self.state = AppState()
        self.kartice: List = []
        self.bocni_panel = None
        self._pazar_prozor = None

        inicijalizuj_bazu()
        self._seed_uredjaje_ako_prazno()
        self._izgraduj_ui()
        self._provjeri_smjenu()
        self._ucitaj_uredjaje()

    def _seed_uredjaje_ako_prazno(self):
        default_uredjaji = [
            ("PC1", 2.0, "PC"), ("PC2", 2.0, "PC"), ("PC3", 2.0, "PC"),
            ("PC4", 2.0, "PC"), ("PC5", 2.0, "PC"), ("PC6", 2.0, "PC"),
            ("PS5-1", 3.0, "PS5"), ("PS5-2", 3.0, "PS5"),
        ]
        seed_uredjaje_ako_prazno(default_uredjaji)

    def _izgraduj_ui(self):
        # Menubar
        menu_frame = ctk.CTkFrame(self.root, height=40, fg_color="#111827", corner_radius=0)
        menu_frame.pack(fill="x", side="top")

        ctk.CTkButton(
            menu_frame, text="⚡ Smjena", width=110, height=32,
            fg_color="transparent", hover_color="#374151",
            command=self._meni_smjena
        ).pack(side="left", padx=4, pady=4)

        ctk.CTkButton(
            menu_frame, text="💰 Pazar", width=110, height=32,
            fg_color="transparent", hover_color="#374151",
            command=self._otvori_pazar
        ).pack(side="left", padx=4, pady=4)

        ctk.CTkButton(
            menu_frame, text="🔒 Admin", width=110, height=32,
            fg_color="transparent", hover_color="#374151",
            command=self._otvori_admin
        ).pack(side="left", padx=4, pady=4)

        # Status bar
        self.lbl_status_bar = ctk.CTkLabel(
            menu_frame, text="Nema otvorene smjene",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af"
        )
        self.lbl_status_bar.pack(side="right", padx=16)

        # Glavni sadržaj
        self.main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Lijevo: kartice uređaja
        self.kartice_frame = ctk.CTkScrollableFrame(
            self.main_frame, fg_color="#0f0f1a", corner_radius=0
        )
        self.kartice_frame.pack(side="left", fill="both", expand=True)

        # Desno: bočni panel
        from ui.bocni_panel import BocniPanel
        self.bocni_panel = BocniPanel(
            self.main_frame,
            smjena_id_getter=lambda: self.state.trenutna_smjena_id,
            radnik_getter=lambda: self.state.ime_radnika,
            log_callback=upisi_log,
            pazar_callback=self._osvjezi_status_bar,
            get_kartice=lambda: self.kartice,
        )
        self.bocni_panel.pack(side="right", fill="y")

    def _provjeri_smjenu(self):
        aktivna = dohvati_aktivnu_smjenu()
        if aktivna:
            odgovor = messagebox.askyesno(
                "Otkrivena smjena",
                f"Pronađena otvorena smjena radnika: {aktivna['radnik']}\n"
                f"Početak: {aktivna['pocetak'][:19].replace('T', ' ')}\n\n"
                "Nastaviti sa ovom smjenom?"
            )
            if odgovor:
                self.state.postavi_smjenu(aktivna["id"], aktivna["radnik"])
                self._osvjezi_status_bar()
                self._obnovi_aktivne_sesije(aktivna["id"])

    def _obnovi_aktivne_sesije(self, smjena_id: int):
        aktivne = dohvati_aktivne_sesije(smjena_id)

        from datetime import datetime
        for row in aktivne:
            kartica = next((k for k in self.kartice if k.ime == row["uredjaj"]), None)
            if kartica and kartica.session is None:
                tip = row["tip"] or "neograniceno"
                vreme = datetime.fromisoformat(row["vreme_starta"])
                kartica.session = SessionState(
                    vreme_starta=vreme,
                    tip=tip,
                    is_prepaid=(tip == "prepaid"),
                    is_pass2=(tip == "pass2"),
                    is_minecraft=(tip == "minecraft"),
                )
                kartica.osvjezi_prikaz()

    def _otvori_smjenu_dijalog(self):
        while True:
            ime = simpledialog.askstring("Nova smjena", "Unesite ime radnika:", parent=self.root)
            if ime and ime.strip():
                smjena_id = otvori_smjenu(ime.strip())
                self.state.postavi_smjenu(smjena_id, ime.strip())
                upisi_log(smjena_id, ime.strip(), "-", "OTVARANJE SMJENE")
                self._osvjezi_status_bar()
                return
            else:
                odgovor = messagebox.askyesno("Info", "Morate otvoriti smjenu. Pokušati ponovo?")
                if not odgovor:
                    return

    def _ucitaj_uredjaje(self):
        for w in self.kartice_frame.winfo_children():
            w.destroy()
        self.kartice.clear()

        from ui.kartica_uredjaja import UredjajKontroler

        red_frame = None
        for i, u in enumerate(ucitaj_uredjaje()):
            if i % 6 == 0:
                red_frame = ctk.CTkFrame(self.kartice_frame, fg_color="transparent")
                red_frame.pack(anchor="w", pady=6, padx=10)

            kartica = UredjajKontroler(
                red_frame,
                ime=u["ime"],
                tip=u["tip"],
                cena=u["cena"],
                smjena_id_getter=lambda: self.state.trenutna_smjena_id,
                radnik_getter=lambda: self.state.ime_radnika,
                log_callback=upisi_log,
                pazar_callback=self._osvjezi_status_bar,
                get_sve_uredjaje=lambda: self.kartice,
            )
            kartica.pack(side="left", padx=6)
            self.kartice.append(kartica)

        if self.bocni_panel:
            self.bocni_panel.ucitaj_artikle()

        # Pokretanje timer petlje
        self._timer_loop()

    def _timer_loop(self):
        for kartica in self.kartice:
            kartica.osvjezi_prikaz()
        if self.bocni_panel:
            self.bocni_panel.osvjezi(self.kartice)
        self.root.after(1000, self._timer_loop)

    def _osvjezi_status_bar(self):
        smjena_id = self.state.trenutna_smjena_id
        if smjena_id is None:
            self.lbl_status_bar.configure(text="Nema otvorene smjene", text_color="#ef4444")
            return

        podaci = dohvati_pazar_smjene(smjena_id)
        self.lbl_status_bar.configure(
            text=f"Smjena: {self.state.ime_radnika}  |  Pazar: {podaci['ukupno']:.2f} KM",
            text_color="#22c55e"
        )

    def _meni_smjena(self):
        izbor = _DijalogSmjena(self.root)
        if izbor.rezultat == "zatvori":
            self._zatvori_smjenu()
        elif izbor.rezultat == "nova":
            self._otvori_smjenu_dijalog()

    def _zatvori_smjenu(self):
        smjena_id = self.state.trenutna_smjena_id
        if smjena_id is None:
            messagebox.showinfo("Info", "Nema otvorene smjene.")
            return

        aktivne_sesije = {k.ime: k.session for k in self.kartice if k.session is not None}
        sank_kosarica = self.bocni_panel.sank_kosarica if self.bocni_panel else []

        upozorenja = []
        if aktivne_sesije:
            upozorenja.append(f"• {len(aktivne_sesije)} aktivnih sesija će biti prekinuto")
        if sank_kosarica:
            upozorenja.append(f"• Šank košarica ({len(sank_kosarica)} stavki) bit će izgubljena!")

        if upozorenja:
            poruka = "Upozorenja:\n" + "\n".join(upozorenja) + "\n\nNastaviti?"
            if not messagebox.askyesno("Zatvaranje smjene", poruka):
                return

        # Dohvati pazar
        podaci_pazara = dohvati_pazar_smjene(smjena_id)

        zatvori_smjenu(smjena_id, aktivne_sesije, sank_kosarica, podaci_pazara["ukupno"])
        upisi_log(smjena_id, self.state.ime_radnika, "-", "ZATVARANJE SMJENE")

        # Generiši izvještaj
        podaci_izvj = {"preneseni_racunari": list(aktivne_sesije.keys())}
        from services.izvjestaj import generiši_tekstualni, generiši_pdf
        tekst = generiši_tekstualni(smjena_id, podaci_izvj)
        pdf_file = generiši_pdf(smjena_id, podaci_izvj)

        # Prikaži izvještaj
        _PrikazIzvjestaja(self.root, tekst, pdf_file)

        # Resetuj stanje — korisnik ručno otvara novu smjenu
        self.state.zatvori_smjenu()

        for k in self.kartice:
            k.session = None
            k.kosarica = []
            k.osvjezi_prikaz()

        if self.bocni_panel:
            self.bocni_panel.sank_kosarica = []

        self._osvjezi_status_bar()

    def _otvori_pazar(self):
        if self._pazar_prozor and self._pazar_prozor.winfo_exists():
            self._pazar_prozor.lift()
            return
        from ui.prikaz_pazara import PrikazPazara
        self._pazar_prozor = PrikazPazara(
            self.root,
            smjena_id_getter=lambda: self.state.trenutna_smjena_id
        )

    def _otvori_admin(self):
        from ui.admin_panel import AdminPanel
        AdminPanel(self.root, reload_callback=self._ucitaj_uredjaje)

    def run(self):
        self.root.mainloop()


class _DijalogSmjena(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Smjena")
        self.geometry("280x230")
        self.grab_set()
        self.lift()
        self.focus_force()
        self.rezultat = None

        ctk.CTkLabel(self, text="Upravljanje smjenom",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(pady=16)

        ctk.CTkButton(
            self, text="Otvori smjenu", width=200, height=36,
            fg_color="#22c55e", hover_color="#16a34a",
            command=lambda: self._odaberi("nova")
        ).pack(pady=4)

        ctk.CTkButton(
            self, text="Zatvori smjenu", width=200, height=36,
            fg_color="#ef4444", hover_color="#dc2626",
            command=lambda: self._odaberi("zatvori")
        ).pack(pady=4)

        ctk.CTkButton(
            self, text="Otkaži", width=200, height=32,
            fg_color="#6b7280", hover_color="#4b5563",
            command=self.destroy
        ).pack(pady=4)

        self.wait_window()

    def _odaberi(self, opcija):
        self.rezultat = opcija
        self.destroy()


class _PrikazIzvjestaja(ctk.CTkToplevel):
    def __init__(self, parent, tekst: str, pdf_file: str):
        super().__init__(parent)
        self.title("Izvještaj smjene")
        self.geometry("580x520")
        self.grab_set()
        self.lift()

        ctk.CTkLabel(self, text="Izvještaj zatvorene smjene",
                      font=ctk.CTkFont(size=15, weight="bold")).pack(pady=10)

        if pdf_file:
            ctk.CTkLabel(
                self, text=f"PDF snimljen: {pdf_file}",
                text_color="#22c55e", font=ctk.CTkFont(size=11)
            ).pack()

        textbox = ctk.CTkTextbox(self, height=380, font=ctk.CTkFont(family="Courier", size=11))
        textbox.pack(padx=12, pady=8, fill="both", expand=True)
        textbox.insert("0.0", tekst)
        textbox.configure(state="disabled")

        ctk.CTkButton(self, text="Zatvori", width=120,
                       command=self.destroy).pack(pady=8)
