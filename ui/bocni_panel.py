import customtkinter as ctk
from tkinter import messagebox
from typing import List, Callable, Optional
from models.artikal import Artikal
from services.artikli import ucitaj_artikle


class BocniPanel(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        smjena_id_getter: Callable,
        radnik_getter: Callable,
        log_callback: Callable,
        pazar_callback: Callable,
        get_kartice: Callable,
    ):
        super().__init__(parent, width=220, fg_color="#1e1e2e", corner_radius=0)
        self.pack_propagate(False)

        self.smjena_id_getter = smjena_id_getter
        self.radnik_getter = radnik_getter
        self.log_callback = log_callback
        self.pazar_callback = pazar_callback
        self.get_kartice = get_kartice

        self.sank_kosarica: List[Artikal] = []
        self.odabrani_cilj: str = "Šank"

        self._izgraduj_ui()

    def _izgraduj_ui(self):
        naslov = ctk.CTkLabel(
            self, text="☕ ŠANK",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        naslov.pack(pady=(12, 4))

        # Segmented button za odabir cilja
        self.segment_var = ctk.StringVar(value="Šank")
        self.segment = ctk.CTkSegmentedButton(
            self,
            values=["Šank"],
            variable=self.segment_var,
            command=self._promijeni_cilj,
            width=200
        )
        self.segment.pack(pady=(0, 8), padx=8)

        # Artikli scroll
        ctk.CTkLabel(self, text="Artikli", font=ctk.CTkFont(size=12, weight="bold"),
                      text_color="#9ca3af").pack()

        self.scroll_artikli = ctk.CTkScrollableFrame(self, height=180, width=200)
        self.scroll_artikli.pack(padx=8, pady=4, fill="x")

        # Separator
        ctk.CTkLabel(self, text="─" * 26, text_color="#374151").pack()

        # Košarica
        ctk.CTkLabel(self, text="Košarica", font=ctk.CTkFont(size=12, weight="bold"),
                      text_color="#9ca3af").pack(pady=(4, 0))

        self.scroll_kosarica = ctk.CTkScrollableFrame(self, height=140, width=200)
        self.scroll_kosarica.pack(padx=8, pady=4, fill="x")

        # Ukupno
        self.lbl_ukupno = ctk.CTkLabel(
            self, text="Ukupno: 0.00 KM",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24"
        )
        self.lbl_ukupno.pack(pady=4)

        # Dugme naplati šank
        self.btn_naplati = ctk.CTkButton(
            self, text="💰 NAPLATI ŠANK",
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#4f46e5", hover_color="#3730a3",
            command=self._naplati_sank
        )
        self.btn_naplati.pack(pady=(0, 8), padx=8, fill="x")

        self.ucitaj_artikle()

    def ucitaj_artikle(self):
        for widget in self.scroll_artikli.winfo_children():
            widget.destroy()

        for a in ucitaj_artikle():
            frame = ctk.CTkFrame(self.scroll_artikli, fg_color="transparent")
            frame.pack(fill="x", pady=2)

            ctk.CTkLabel(
                frame,
                text=f"{a['naziv']}",
                font=ctk.CTkFont(size=11),
                width=110, anchor="w"
            ).pack(side="left")

            ctk.CTkLabel(
                frame,
                text=f"{a['cijena']:.2f}",
                font=ctk.CTkFont(size=10),
                text_color="#9ca3af",
                width=40
            ).pack(side="left")

            ctk.CTkButton(
                frame, text="+", width=28, height=24,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="#22c55e", hover_color="#16a34a",
                command=lambda naziv=a["naziv"], cijena=a["cijena"]: self._dodaj_artikal(naziv, cijena)
            ).pack(side="right", padx=2)

    def azuriraj_segment(self, kartice):
        vrijednosti = ["Šank"] + [k.ime for k in kartice if k.session is not None]
        self.segment.configure(values=vrijednosti)
        if self.segment_var.get() not in vrijednosti:
            self.segment_var.set("Šank")
            self.odabrani_cilj = "Šank"

    def _promijeni_cilj(self, vrijednost: str):
        self.odabrani_cilj = vrijednost
        self._osvjezi_kosaricu()

    def _dodaj_artikal(self, naziv: str, cijena: float):
        if self.smjena_id_getter() is None:
            messagebox.showinfo("Info", "Nema otvorene smjene.")
            return
        artikal = Artikal(naziv=naziv, cijena=cijena, kolicina=1)
        cilj = self.odabrani_cilj

        if cilj == "Šank":
            # Dodaj u šank košaricu
            for a in self.sank_kosarica:
                if a.naziv == naziv:
                    a.kolicina += 1
                    self._osvjezi_kosaricu()
                    return
            self.sank_kosarica.append(artikal)
            self._osvjezi_kosaricu()
        else:
            # Dodaj na računar
            kartice = self.get_kartice()
            kartica = next((k for k in kartice if k.ime == cilj), None)
            if kartica:
                kartica.dodaj_u_kosaricu(artikal)
                self._osvjezi_kosaricu()
            else:
                messagebox.showwarning("Info", f"Uređaj {cilj} nije aktivan.")

    def _osvjezi_kosaricu(self):
        for widget in self.scroll_kosarica.winfo_children():
            widget.destroy()

        cilj = self.odabrani_cilj

        if cilj == "Šank":
            stavke = self.sank_kosarica
        else:
            kartice = self.get_kartice()
            kartica = next((k for k in kartice if k.ime == cilj), None)
            stavke = kartica.kosarica if kartica else []

        ukupno = 0.0
        for artikal in stavke:
            ukupno += artikal.ukupno()
            red = ctk.CTkFrame(self.scroll_kosarica, fg_color="transparent")
            red.pack(fill="x", pady=1)

            ctk.CTkLabel(
                red,
                text=f"{artikal.naziv} x{artikal.kolicina}",
                font=ctk.CTkFont(size=10),
                width=110, anchor="w"
            ).pack(side="left")

            ctk.CTkLabel(
                red,
                text=f"{artikal.ukupno():.2f}",
                font=ctk.CTkFont(size=10),
                text_color="#fbbf24",
                width=40
            ).pack(side="left")

            ctk.CTkButton(
                red, text="-", width=24, height=20,
                fg_color="#ef4444", hover_color="#dc2626",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda a=artikal: self._ukloni_artikal(a)
            ).pack(side="right", padx=2)

        self.lbl_ukupno.configure(text=f"Ukupno: {ukupno:.2f} KM")

    def _ukloni_artikal(self, artikal: Artikal):
        cilj = self.odabrani_cilj
        if cilj == "Šank":
            if artikal.kolicina > 1:
                artikal.kolicina -= 1
            else:
                self.sank_kosarica = [a for a in self.sank_kosarica if a.naziv != artikal.naziv]
        else:
            kartice = self.get_kartice()
            kartica = next((k for k in kartice if k.ime == cilj), None)
            if kartica:
                if artikal.kolicina > 1:
                    artikal.kolicina -= 1
                else:
                    kartica.kosarica = [a for a in kartica.kosarica if a.naziv != artikal.naziv]
        self._osvjezi_kosaricu()

    def _naplati_sank(self):
        if self.smjena_id_getter() is None:
            messagebox.showinfo("Info", "Nema otvorene smjene.")
            return
        cilj = self.odabrani_cilj
        if cilj != "Šank":
            messagebox.showinfo("Info", "Prebaci se na Šank košaricu za naplatu.")
            return

        if not self.sank_kosarica:
            messagebox.showinfo("Info", "Šank košarica je prazna.")
            return

        smjena_id = self.smjena_id_getter()
        radnik = self.radnik_getter()

        from services.pazar import naplati_sank_kosaricu
        ukupno = naplati_sank_kosaricu(self.sank_kosarica, smjena_id)

        self.log_callback(smjena_id, radnik, "Šank",
                          f"NAPLATA ŠANK — {ukupno:.2f} KM")

        self.sank_kosarica = []
        self._osvjezi_kosaricu()
        self.pazar_callback()
        messagebox.showinfo("Naplata", f"Šank naplaćen: {ukupno:.2f} KM")

    def osvjezi(self, kartice):
        self.azuriraj_segment(kartice)
        self._osvjezi_kosaricu()
        smjena_ok = self.smjena_id_getter() is not None
        self.btn_naplati.configure(state="normal" if smjena_ok else "disabled")
