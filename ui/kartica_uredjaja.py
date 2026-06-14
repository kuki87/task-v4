import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from typing import Optional, Callable
from models.session_state import SessionState
from models.artikal import Artikal
from constants import (
    KARTICA_BG, KARTICA_AKTIVNA,
    BOJA_NAPLATI, BOJA_PREBACI,
    BOJA_PASS1, BOJA_PASS2, BOJA_MINECRAFT,
    CIJENA_MINECRAFT
)


BOJA_STATUS = {
    "SLOBODNO": "#9ca3af",
    "U RADU": "#60a5fa",
    "UNAPRIJED": "#a78bfa",
    "PASS 1": "#4ade80",
    "PASS 2": "#fb923c",
    "MINECRAFT": "#22c55e",
}


class UredjajKontroler(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        ime: str,
        tip: str,
        cena: float,
        smjena_id_getter: Callable,
        radnik_getter: Callable,
        log_callback: Callable,
        pazar_callback: Callable,
        get_sve_uredjaje: Callable,
    ):
        super().__init__(parent, width=190, height=240,
                         fg_color=KARTICA_BG, corner_radius=12)
        self.pack_propagate(False)

        self.ime = ime
        self.tip = tip.upper()
        self.cena = cena
        self.smjena_id_getter = smjena_id_getter
        self.radnik_getter = radnik_getter
        self.log_callback = log_callback
        self.pazar_callback = pazar_callback
        self.get_sve_uredjaje = get_sve_uredjaje

        self.session: Optional[SessionState] = None
        self.kosarica: list = []

        self._izgraduj_ui()

    def _izgraduj_ui(self):
        # Naziv
        self.lbl_naziv = ctk.CTkLabel(
            self, text=self.ime,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.lbl_naziv.pack(pady=(12, 2))

        # Tip oznaka
        boja_tip = "#6366f1" if self.tip == "PS5" else "#4f46e5"
        self.lbl_tip = ctk.CTkLabel(
            self, text=self.tip,
            font=ctk.CTkFont(size=10),
            text_color=boja_tip
        )
        self.lbl_tip.pack()

        # Status
        self.lbl_status = ctk.CTkLabel(
            self, text="SLOBODNO",
            font=ctk.CTkFont(size=11),
            text_color=BOJA_STATUS["SLOBODNO"]
        )
        self.lbl_status.pack(pady=(4, 0))

        # Timer
        self.lbl_timer = ctk.CTkLabel(
            self, text="--:--",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.lbl_timer.pack(pady=(2, 0))

        # Iznos
        self.lbl_iznos = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=11),
            text_color="#fbbf24"
        )
        self.lbl_iznos.pack()

        # Progress bar (prepaid/pass1)
        self.progress = ctk.CTkProgressBar(self, width=155, height=8)
        self.progress.set(0)
        self.progress.pack(pady=2)
        self.progress.pack_forget()

        # Košarica label
        self.lbl_kosarica = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=9),
            text_color="#9ca3af"
        )
        self.lbl_kosarica.pack()

        # Dugmad
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=(0, 8))

        self.btn_start = ctk.CTkButton(
            btn_frame, text="START", width=82, height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.start_sesiju
        )
        self.btn_start.grid(row=0, column=0, padx=3)

        self.btn_naplati = ctk.CTkButton(
            btn_frame, text="NAPLATI", width=82, height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=BOJA_NAPLATI,
            command=self.naplati,
            state="disabled"
        )
        self.btn_naplati.grid(row=0, column=1, padx=3)

        self.btn_prebaci = ctk.CTkButton(
            btn_frame, text="PREBACI", width=168, height=26,
            font=ctk.CTkFont(size=10),
            fg_color=BOJA_PREBACI, hover_color="#d97706",
            command=self.prebaci,
            state="disabled"
        )
        self.btn_prebaci.grid(row=1, column=0, columnspan=2, pady=(5, 0))

    def start_sesiju(self):
        if self.smjena_id_getter() is None:
            messagebox.showinfo("Info", "Nema otvorene smjene.")
            return
        if self.session is not None:
            return
        from ui.dijalog_start import IzborStartaDijalog
        dijalog = IzborStartaDijalog(self.winfo_toplevel(), self.tip, self.cena)
        if dijalog.rezultat is None:
            return

        rezultat = dijalog.rezultat
        tip = rezultat["tip"]

        self.session = SessionState(
            vreme_starta=datetime.now(),
            limit_sekundi=rezultat.get("limit_sekundi"),
            is_prepaid=(tip == "prepaid"),
            is_pass2=(tip == "pass2"),
            is_minecraft=(tip == "minecraft"),
            tip=tip
        )
        self.kosarica = []

        smjena_id = self.smjena_id_getter()
        radnik = self.radnik_getter()

        # Naplati pass tip odmah
        if tip in ("prepaid", "pass1", "pass2") and rezultat["iznos"] > 0:
            from services.pazar import start_sesija_prepaid
            start_sesija_prepaid(self.ime, rezultat["iznos"], smjena_id, tip)
            self.pazar_callback()

        self.log_callback(smjena_id, radnik, self.ime, f"START — {tip.upper()}")
        self.osvjezi_prikaz()

    def naplati(self):
        if self.smjena_id_getter() is None:
            messagebox.showinfo("Info", "Nema otvorene smjene.")
            return
        if self.session is None:
            return

        smjena_id = self.smjena_id_getter()
        radnik = self.radnik_getter()

        from services.pazar import naplati_uredjaj
        iznos = naplati_uredjaj(
            self.ime, self.session, self.kosarica, self.cena, smjena_id
        )

        self.log_callback(smjena_id, radnik, self.ime,
                          f"NAPLATA — {self.session.tip.upper()} — {iznos:.2f} KM")

        self.session = None
        self.kosarica = []
        self.pazar_callback()
        self.osvjezi_prikaz()

    def prebaci(self):
        if self.session is None:
            return

        svi = self.get_sve_uredjaje()
        slobodni = [u for u in svi if u.ime != self.ime and u.session is None]

        if not slobodni:
            messagebox.showinfo("Info", "Nema slobodnih uređaja za prijenos.")
            return

        names = [u.ime for u in slobodni]
        izbor = _DijalogIzbora(self.winfo_toplevel(), "Odaberi uređaj", names)
        if izbor.rezultat is None:
            return

        cilj = next((u for u in slobodni if u.ime == izbor.rezultat), None)
        if cilj is None:
            return

        # Prenesi sesiju i košaricu
        from copy import deepcopy
        cilj.session = deepcopy(self.session)
        cilj.kosarica = deepcopy(self.kosarica)

        smjena_id = self.smjena_id_getter()
        radnik = self.radnik_getter()
        self.log_callback(smjena_id, radnik, self.ime,
                          f"PRIJENOS → {cilj.ime}")

        self.session = None
        self.kosarica = []
        self.osvjezi_prikaz()
        cilj.osvjezi_prikaz()

    def dodaj_u_kosaricu(self, artikal: Artikal):
        for a in self.kosarica:
            if a.naziv == artikal.naziv:
                a.kolicina += artikal.kolicina
                self.osvjezi_prikaz()
                return
        from copy import deepcopy
        self.kosarica.append(deepcopy(artikal))
        self.osvjezi_prikaz()

        smjena_id = self.smjena_id_getter()
        from services.pazar import dodaj_artikal_na_uredjaj
        dodaj_artikal_na_uredjaj(smjena_id, self.ime, artikal.naziv,
                                  artikal.kolicina, artikal.cijena)

    def osvjezi_prikaz(self):
        if self.session is None:
            self.configure(fg_color=KARTICA_BG)
            self.lbl_status.configure(text="SLOBODNO",
                                       text_color=BOJA_STATUS["SLOBODNO"])
            self.lbl_timer.configure(text="--:--")
            self.lbl_iznos.configure(text="")
            self.lbl_kosarica.configure(text="")
            self.progress.pack_forget()
            smjena_ok = self.smjena_id_getter() is not None
            self.btn_start.configure(state="normal" if smjena_ok else "disabled")
            self.btn_naplati.configure(state="disabled")
            self.btn_prebaci.grid_remove()
            return

        tip = self.session.tip
        timer_txt = self.session.formatiraj_timer()
        self.lbl_timer.configure(text=timer_txt)

        # Status i boja
        status_mapa = {
            "neograniceno": "U RADU",
            "prepaid": "UNAPRIJED",
            "pass1": "PASS 1",
            "pass2": "PASS 2",
            "minecraft": "MINECRAFT",
        }
        status = status_mapa.get(tip, "U RADU")
        boja_status = BOJA_STATUS.get(status, "#60a5fa")
        self.lbl_status.configure(text=status, text_color=boja_status)

        # Boja kartice
        if tip == "minecraft":
            self.configure(fg_color="#1a2e1a")
        elif tip == "pass1":
            self.configure(fg_color="#1a2e1a")
        elif tip == "pass2":
            self.configure(fg_color="#2e1a0a")
        else:
            self.configure(fg_color=KARTICA_AKTIVNA)

        # Iznos
        if tip == "minecraft":
            elapsed_sati = self.session.elapsed_sekundi() / 3600
            iznos_trenutan = round(elapsed_sati * CIJENA_MINECRAFT, 2)
            self.lbl_iznos.configure(text=f"≈ {iznos_trenutan:.2f} KM")
        elif tip == "neograniceno":
            elapsed_sati = self.session.elapsed_sekundi() / 3600
            iznos_trenutan = round(elapsed_sati * self.cena, 2)
            self.lbl_iznos.configure(text=f"≈ {iznos_trenutan:.2f} KM")
        else:
            self.lbl_iznos.configure(text="")

        # Progress bar
        if tip in ("prepaid", "pass1"):
            self.progress.pack(pady=2)
            self.progress.set(self.session.progres_prepaid())
            preostalo = self.session.formatiraj_preostalo()
            if preostalo:
                self.lbl_iznos.configure(text=f"⏳ {preostalo}")
        else:
            self.progress.pack_forget()

        # Košarica
        if self.kosarica:
            ukupno_k = sum(a.ukupno() for a in self.kosarica)
            self.lbl_kosarica.configure(
                text=f"🛒 {len(self.kosarica)} art. {ukupno_k:.2f}KM"
            )
        else:
            self.lbl_kosarica.configure(text="")

        smjena_ok = self.smjena_id_getter() is not None
        self.btn_start.configure(state="disabled")
        self.btn_naplati.configure(state="normal" if smjena_ok else "disabled")
        self.btn_prebaci.grid(row=1, column=0, columnspan=2, pady=(5, 0))
        self.btn_prebaci.configure(state="normal" if smjena_ok else "disabled")

        # Upozorenje za isteklu sesiju
        if self.session.je_istekao():
            self.lbl_status.configure(text="⚠ ISTEKLO!", text_color="#ef4444")


class _DijalogIzbora(ctk.CTkToplevel):
    def __init__(self, parent, naslov: str, opcije: list):
        super().__init__(parent)
        self.title(naslov)
        self.geometry("280x320")
        self.grab_set()
        self.lift()
        self.focus_force()
        self.rezultat = None

        ctk.CTkLabel(self, text=naslov,
                      font=ctk.CTkFont(size=14, weight="bold")).pack(pady=12)

        scroll = ctk.CTkScrollableFrame(self, height=200)
        scroll.pack(padx=12, fill="both", expand=True)

        for opcija in opcije:
            ctk.CTkButton(
                scroll, text=opcija,
                command=lambda o=opcija: self._odaberi(o)
            ).pack(pady=3, fill="x")

        ctk.CTkButton(self, text="Otkaži", fg_color="#6b7280",
                       command=self.destroy).pack(pady=8)
        self.wait_window()

    def _odaberi(self, opcija):
        self.rezultat = opcija
        self.destroy()
