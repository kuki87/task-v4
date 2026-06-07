import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from constants import (
    BOJA_PASS1, BOJA_PASS2, BOJA_MINECRAFT, CIJENA_MINECRAFT,
    PASS1_PLACENIH_SATI, PASS1_DOBIJENIH_SATI,
    PASS2_PLACENIH_SATI, PASS2_ULAZ_OD, PASS2_ULAZ_DO
)


class IzborStartaDijalog(ctk.CTkToplevel):
    def __init__(self, parent, tip_uredjaja: str = "PC", cena_po_satu: float = 2.0):
        super().__init__(parent)
        self.title("Odaberi tip starta")
        self.geometry("420x360")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()

        self.tip_uredjaja = tip_uredjaja.upper()
        self.cena_po_satu = cena_po_satu
        self.rezultat = None

        self._izgraduj_ui()
        self.protocol("WM_DELETE_WINDOW", self._otkazi)
        self.wait_window()

    def _izgraduj_ui(self):
        naslov = ctk.CTkLabel(self, text="Odaberi tip starta",
                               font=ctk.CTkFont(size=16, weight="bold"))
        naslov.pack(pady=(16, 8))

        self.tabview = ctk.CTkTabview(self, width=390, height=240)
        self.tabview.pack(padx=12, pady=4, fill="both", expand=True)

        # Uvijek dostupni tabovi
        self.tabview.add("Neograničeno")
        self.tabview.add("Unaprijed")

        # PC-only tabovi
        if self.tip_uredjaja == "PC":
            self.tabview.add("Pass 1")
            self.tabview.add("Pass 2")
            self.tabview.add("Minecraft")

        self._tab_neograniceno()
        self._tab_unaprijed()
        if self.tip_uredjaja == "PC":
            self._tab_pass1()
            self._tab_pass2()
            self._tab_minecraft()

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=8, fill="x", padx=16)

        ctk.CTkButton(
            btn_frame, text="✓ Pokreni", width=180,
            command=self._potvrdi
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_frame, text="✕ Otkaži", width=180,
            fg_color="#ef4444", hover_color="#dc2626",
            command=self._otkazi
        ).pack(side="right", padx=4)

    def _tab_neograniceno(self):
        tab = self.tabview.tab("Neograničeno")
        ctk.CTkLabel(
            tab,
            text=f"Neograničeno trajanje\nCijena: {self.cena_po_satu:.2f} KM/h\nNaplata pri kraju sesije.",
            font=ctk.CTkFont(size=13),
            justify="center"
        ).pack(expand=True, pady=20)

    def _tab_unaprijed(self):
        tab = self.tabview.tab("Unaprijed")
        ctk.CTkLabel(tab, text="Uplati iznos → dobije odgovarajuće vrijeme",
                     font=ctk.CTkFont(size=12)).pack(pady=(16, 4))
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(pady=8)
        ctk.CTkLabel(frame, text="Iznos (KM):", width=100).pack(side="left")
        self.entry_prepaid = ctk.CTkEntry(frame, width=100, placeholder_text="npr. 5.00")
        self.entry_prepaid.pack(side="left", padx=8)

    def _tab_pass1(self):
        tab = self.tabview.tab("Pass 1")
        cijena = PASS1_PLACENIH_SATI * self.cena_po_satu
        tekst = (
            f"Plati {PASS1_PLACENIH_SATI}h → dobije {PASS1_DOBIJENIH_SATI}h\n"
            f"Cijena: {cijena:.2f} KM\n"
            f"Progress bar prikazuje preostalo vrijeme."
        )
        ctk.CTkLabel(
            tab, text=tekst,
            font=ctk.CTkFont(size=13),
            justify="center",
            text_color=BOJA_PASS1
        ).pack(expand=True, pady=20)

    def _tab_pass2(self):
        tab = self.tabview.tab("Pass 2")
        cijena = PASS2_PLACENIH_SATI * self.cena_po_satu
        tekst = (
            f"Plati {PASS2_PLACENIH_SATI}h → igra do kraja smjene\n"
            f"Ulaz: {PASS2_ULAZ_OD}:00 – {PASS2_ULAZ_DO}:00\n"
            f"Cijena: {cijena:.2f} KM"
        )
        ctk.CTkLabel(
            tab, text=tekst,
            font=ctk.CTkFont(size=13),
            justify="center",
            text_color=BOJA_PASS2
        ).pack(expand=True, pady=20)

    def _tab_minecraft(self):
        tab = self.tabview.tab("Minecraft")
        tekst = (
            f"Pass Minecraft\n"
            f"Fiksna cijena: {CIJENA_MINECRAFT:.2f} KM/h\n"
            f"Naplata po provedenom vremenu."
        )
        ctk.CTkLabel(
            tab, text=tekst,
            font=ctk.CTkFont(size=13),
            justify="center",
            text_color=BOJA_MINECRAFT
        ).pack(expand=True, pady=20)

    def _potvrdi(self):
        aktivan_tab = self.tabview.get()

        if aktivan_tab == "Neograničeno":
            self.rezultat = {"tip": "neograniceno", "iznos": 0.0, "limit_sekundi": None}

        elif aktivan_tab == "Unaprijed":
            try:
                iznos = float(self.entry_prepaid.get().replace(",", "."))
                if iznos <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Greška", "Unesite validan iznos (npr. 5.00)")
                return
            limit_sek = int((iznos / self.cena_po_satu) * 3600)
            self.rezultat = {"tip": "prepaid", "iznos": iznos, "limit_sekundi": limit_sek}

        elif aktivan_tab == "Pass 1":
            iznos = PASS1_PLACENIH_SATI * self.cena_po_satu
            limit_sek = PASS1_DOBIJENIH_SATI * 3600
            self.rezultat = {"tip": "pass1", "iznos": iznos, "limit_sekundi": limit_sek}

        elif aktivan_tab == "Pass 2":
            sad = datetime.now().hour
            if not (PASS2_ULAZ_OD <= sad < PASS2_ULAZ_DO):
                messagebox.showerror(
                    "Greška",
                    f"Pass 2 je dostupan samo između {PASS2_ULAZ_OD}:00 i {PASS2_ULAZ_DO}:00!"
                )
                return
            iznos = PASS2_PLACENIH_SATI * self.cena_po_satu
            self.rezultat = {"tip": "pass2", "iznos": iznos, "limit_sekundi": None}

        elif aktivan_tab == "Minecraft":
            self.rezultat = {"tip": "minecraft", "iznos": 0.0, "limit_sekundi": None}

        self.destroy()

    def _otkazi(self):
        self.rezultat = None
        self.destroy()
