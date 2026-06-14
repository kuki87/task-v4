import customtkinter as ctk
from tkinter import messagebox, simpledialog
from services.auth import provjeri_admin_lozinku, promijeni_lozinku
from services.artikli import ucitaj_artikle, dodaj_artikal, uredi_artikal, brisi_artikal
from services.uredjaji import ucitaj_uredjaje, dodaj_uredjaj, brisi_uredjaj, ucitaj_logove, postavi_cijenu_grupe


class AdminPanel(ctk.CTkToplevel):
    def __init__(self, parent, reload_callback=None):
        super().__init__(parent)
        self.withdraw()  # sakrij prozor dok se ne unese lozinka
        self.title("Admin Panel")
        self.geometry("700x660")
        self.reload_callback = reload_callback

        if not self._provjeri_lozinku():
            self.destroy()
            return

        self.grab_set()
        self.lift()
        self.focus_force()
        self.deiconify()  # prikaži tek nakon uspješne autentifikacije
        self._izgraduj_ui()

    def _provjeri_lozinku(self) -> bool:
        lozinka = simpledialog.askstring(
            "Admin", "Unesite admin lozinku:", show="*", parent=self.master
        )
        if lozinka is None:
            return False
        if not provjeri_admin_lozinku(lozinka):
            messagebox.showerror("Greška", "Pogrešna lozinka!", parent=self.master)
            return False
        return True

    def _izgraduj_ui(self):
        self.tabview = ctk.CTkTabview(self, width=600, height=520)
        self.tabview.pack(padx=12, pady=12, fill="both", expand=True)

        self.tabview.add("Artikli")
        self.tabview.add("Uređaji")
        self.tabview.add("Logovi")
        self.tabview.add("Lozinka")

        self._tab_artikli()
        self._tab_uredjaji()
        self._tab_logovi()
        self._tab_lozinka()

    # ---- TAB ARTIKLI ----

    def _tab_artikli(self):
        tab = self.tabview.tab("Artikli")

        # Input
        input_frame = ctk.CTkFrame(tab, fg_color="transparent")
        input_frame.pack(fill="x", pady=8, padx=8)

        ctk.CTkLabel(input_frame, text="Naziv:").pack(side="left")
        self.entry_artk_naziv = ctk.CTkEntry(input_frame, width=150, placeholder_text="Naziv artikla")
        self.entry_artk_naziv.pack(side="left", padx=4)

        ctk.CTkLabel(input_frame, text="Cijena (KM):").pack(side="left")
        self.entry_artk_cijena = ctk.CTkEntry(input_frame, width=80, placeholder_text="0.00")
        self.entry_artk_cijena.pack(side="left", padx=4)

        ctk.CTkButton(input_frame, text="Dodaj", width=80,
                       fg_color="#22c55e", hover_color="#16a34a",
                       command=self._dodaj_artikal).pack(side="left", padx=4)

        # Lista
        self.scroll_artikli = ctk.CTkScrollableFrame(tab, height=300)
        self.scroll_artikli.pack(padx=8, fill="both", expand=True)

        ctk.CTkButton(tab, text="Osvježi", width=120,
                       command=self._ucitaj_artikle).pack(pady=6)

        self._ucitaj_artikle()

    def _ucitaj_artikle(self):
        for w in self.scroll_artikli.winfo_children():
            w.destroy()

        for a in ucitaj_artikle():
            red = ctk.CTkFrame(self.scroll_artikli, fg_color="#2a2a3e", corner_radius=6)
            red.pack(fill="x", pady=2)

            ctk.CTkLabel(red, text=a["naziv"], width=160, anchor="w",
                          font=ctk.CTkFont(size=12)).pack(side="left", padx=8)
            ctk.CTkLabel(red, text=f"{a['cijena']:.2f} KM", width=80,
                          font=ctk.CTkFont(size=12)).pack(side="left")

            ctk.CTkButton(
                red, text="Uredi", width=60, height=26,
                fg_color="#f39c12", hover_color="#d97706",
                command=lambda aid=a["id"], an=a["naziv"], ac=a["cijena"]: self._uredi_artikal(aid, an, ac)
            ).pack(side="right", padx=4)

            ctk.CTkButton(
                red, text="Briši", width=60, height=26,
                fg_color="#ef4444", hover_color="#dc2626",
                command=lambda aid=a["id"]: self._brisi_artikal(aid)
            ).pack(side="right", padx=2)

    def _dodaj_artikal(self):
        naziv = self.entry_artk_naziv.get().strip()
        try:
            cijena = float(self.entry_artk_cijena.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Greška", "Nevalidna cijena!")
            return
        if not naziv:
            messagebox.showerror("Greška", "Unesite naziv!")
            return
        try:
            dodaj_artikal(naziv, cijena)
            self.entry_artk_naziv.delete(0, "end")
            self.entry_artk_cijena.delete(0, "end")
            self._ucitaj_artikle()
            if self.reload_callback:
                self.reload_callback()
        except Exception as e:
            messagebox.showerror("Greška", f"Artikal već postoji: {e}")

    def _uredi_artikal(self, aid: int, naziv: str, cijena: float):
        novi_naziv = simpledialog.askstring("Uredi", "Novi naziv:", initialvalue=naziv, parent=self)
        if novi_naziv is None:
            return
        nova_cijena = simpledialog.askfloat("Uredi", "Nova cijena:", initialvalue=cijena, parent=self)
        if nova_cijena is None:
            return
        uredi_artikal(aid, novi_naziv, nova_cijena)
        self._ucitaj_artikle()
        if self.reload_callback:
            self.reload_callback()

    def _brisi_artikal(self, aid: int):
        if not messagebox.askyesno("Potvrda", "Obrisati artikal?"):
            return
        brisi_artikal(aid)
        self._ucitaj_artikle()
        if self.reload_callback:
            self.reload_callback()

    # ---- TAB UREĐAJI ----

    def _tab_uredjaji(self):
        tab = self.tabview.tab("Uređaji")

        input_frame = ctk.CTkFrame(tab, fg_color="transparent")
        input_frame.pack(fill="x", pady=8, padx=8)

        ctk.CTkLabel(input_frame, text="Ime:").pack(side="left")
        self.entry_urd_ime = ctk.CTkEntry(input_frame, width=90, placeholder_text="PC")
        self.entry_urd_ime.pack(side="left", padx=4)

        ctk.CTkLabel(input_frame, text="KM/h:").pack(side="left")
        self.entry_urd_cena = ctk.CTkEntry(input_frame, width=55, placeholder_text="2.0")
        self.entry_urd_cena.pack(side="left", padx=4)

        ctk.CTkLabel(input_frame, text="Tip:").pack(side="left")
        self.var_tip = ctk.StringVar(value="PC")
        ctk.CTkOptionMenu(
            input_frame, values=["PC", "PS5"],
            variable=self.var_tip, width=65,
            command=self._on_tip_promjena
        ).pack(side="left", padx=4)

        ctk.CTkLabel(input_frame, text="Grupa:").pack(side="left")
        self.var_grupa = ctk.StringVar(value="Classic")
        self.menu_grupa = ctk.CTkOptionMenu(
            input_frame, values=["Classic", "VIP", "Super VIP"],
            variable=self.var_grupa, width=100
        )
        self.menu_grupa.pack(side="left", padx=4)

        ctk.CTkLabel(input_frame, text="Količina:").pack(side="left")
        self.entry_kolicina = ctk.CTkEntry(input_frame, width=45, placeholder_text="1")
        self.entry_kolicina.pack(side="left", padx=4)

        ctk.CTkButton(input_frame, text="Dodaj", width=65,
                       fg_color="#22c55e", hover_color="#16a34a",
                       command=self._dodaj_uredjaj).pack(side="left", padx=4)

        self.scroll_uredjaji = ctk.CTkScrollableFrame(tab, height=200)
        self.scroll_uredjaji.pack(padx=8, fill="both", expand=True)

        ctk.CTkButton(tab, text="Osvježi listu", width=120,
                       command=self._ucitaj_uredjaje).pack(pady=4)

        # ---- Cijena po grupi ----
        ctk.CTkLabel(tab, text="Postavi cijenu po grupi (KM/h)",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      text_color="#9ca3af").pack(pady=(8, 2))

        cijena_frame = ctk.CTkFrame(tab, fg_color="#1e1e2e", corner_radius=8)
        cijena_frame.pack(fill="x", padx=8, pady=4)

        self._entry_cijene: dict = {}
        for grupa in ["Classic", "VIP", "Super VIP", "PS5"]:
            red = ctk.CTkFrame(cijena_frame, fg_color="transparent")
            red.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(red, text=grupa, width=90, anchor="w",
                          font=ctk.CTkFont(size=12)).pack(side="left")
            entry = ctk.CTkEntry(red, width=80, placeholder_text="—")
            entry.pack(side="left", padx=6)
            self._entry_cijene[grupa] = entry
            ctk.CTkButton(
                red, text="Sačuvaj", width=80, height=26,
                fg_color="#22c55e", hover_color="#16a34a",
                command=lambda g=grupa: self._postavi_cijenu_grupe(g)
            ).pack(side="left", padx=4)

        self._ucitaj_uredjaje()

    def _on_tip_promjena(self, vrijednost: str):
        if vrijednost == "PS5":
            self.var_grupa.set("PS5")
            self.menu_grupa.configure(state="disabled")
        else:
            self.var_grupa.set("Classic")
            self.menu_grupa.configure(state="normal")

    def _osvjezi_cijene_grupe(self):
        cijene: dict = {}
        for u in ucitaj_uredjaje():
            g = u["grupa"]
            if g not in cijene:
                cijene[g] = u["cena"]
        for grupa, entry in self._entry_cijene.items():
            entry.delete(0, "end")
            if grupa in cijene:
                entry.insert(0, f"{cijene[grupa]:.2f}")

    def _ucitaj_uredjaje(self):
        for w in self.scroll_uredjaji.winfo_children():
            w.destroy()

        for u in ucitaj_uredjaje():
            red = ctk.CTkFrame(self.scroll_uredjaji, fg_color="#2a2a3e", corner_radius=6)
            red.pack(fill="x", pady=2)

            ctk.CTkLabel(red, text=u["ime"], width=80, anchor="w",
                          font=ctk.CTkFont(size=12)).pack(side="left", padx=8)
            ctk.CTkLabel(red, text=f"{u['cena']:.2f} KM/h", width=80).pack(side="left")
            tip_boja = "#6366f1" if u["tip"] == "PS5" else "#4f46e5"
            ctk.CTkLabel(red, text=u["tip"], width=45,
                          text_color=tip_boja).pack(side="left")
            ctk.CTkLabel(red, text=u["grupa"], width=80,
                          text_color="#9ca3af", font=ctk.CTkFont(size=11)).pack(side="left")

            ctk.CTkButton(
                red, text="Briši", width=60, height=26,
                fg_color="#ef4444", hover_color="#dc2626",
                command=lambda uid=u["id"]: self._brisi_uredjaj(uid)
            ).pack(side="right", padx=4)

        self._osvjezi_cijene_grupe()

    def _dodaj_uredjaj(self):
        base_ime = self.entry_urd_ime.get().strip()
        try:
            cena = float(self.entry_urd_cena.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Greška", "Nevalidna cijena!")
            return
        try:
            kolicina = max(1, int(self.entry_kolicina.get().strip() or "1"))
        except ValueError:
            messagebox.showerror("Greška", "Nevalidna količina!")
            return
        tip = self.var_tip.get()
        grupa = self.var_grupa.get()
        if not base_ime:
            messagebox.showerror("Greška", "Unesite ime uređaja!")
            return
        try:
            if kolicina == 1:
                dodaj_uredjaj(base_ime, cena, tip, grupa)
            else:
                import re
                svi = ucitaj_uredjaje()
                postojeci_imena = {u["ime"] for u in svi}
                # Nastavi od globalnog max broja (svi PC uređaji dijele numeraciju)
                svi_brojevi = [
                    int(m.group(1))
                    for u in svi
                    if (m := re.search(r'(\d+)$', u["ime"]))
                ]
                sljedeci = (max(svi_brojevi) + 1) if svi_brojevi else 1
                created = 0
                while created < kolicina:
                    kandidat = f"{base_ime}{sljedeci}"
                    if kandidat not in postojeci_imena:
                        dodaj_uredjaj(kandidat, cena, tip, grupa)
                        postojeci_imena.add(kandidat)
                        created += 1
                    sljedeci += 1
            self.entry_urd_ime.delete(0, "end")
            self.entry_urd_cena.delete(0, "end")
            self.entry_kolicina.delete(0, "end")
            self._ucitaj_uredjaje()
            if self.reload_callback:
                self.reload_callback()
        except Exception as e:
            messagebox.showerror("Greška", f"Greška pri dodavanju uređaja: {e}")

    def _postavi_cijenu_grupe(self, grupa: str):
        raw = self._entry_cijene[grupa].get().strip().replace(",", ".")
        try:
            cena = float(raw)
        except ValueError:
            messagebox.showerror("Greška", f"Nevalidna cijena za grupu {grupa}!")
            return
        azurirano = postavi_cijenu_grupe(grupa, cena)
        messagebox.showinfo("OK", f"Ažurirano {azurirano} uređaja u grupi '{grupa}' → {cena:.2f} KM/h")
        self._ucitaj_uredjaje()  # osvježava listu i cijene u poljima
        if self.reload_callback:
            self.reload_callback()

    def _brisi_uredjaj(self, uid: int):
        if not messagebox.askyesno("Potvrda", "Obrisati uređaj?"):
            return
        brisi_uredjaj(uid)
        self._ucitaj_uredjaje()
        if self.reload_callback:
            self.reload_callback()

    # ---- TAB LOGOVI ----

    def _tab_logovi(self):
        tab = self.tabview.tab("Logovi")

        filter_frame = ctk.CTkFrame(tab, fg_color="transparent")
        filter_frame.pack(fill="x", pady=8, padx=8)

        ctk.CTkLabel(filter_frame, text="Filter (datum):").pack(side="left")
        self.entry_filter = ctk.CTkEntry(filter_frame, width=120, placeholder_text="2024-01-01")
        self.entry_filter.pack(side="left", padx=4)
        ctk.CTkButton(filter_frame, text="Filtriraj", width=90,
                       command=self._ucitaj_logove).pack(side="left", padx=4)
        ctk.CTkButton(filter_frame, text="Sve", width=60,
                       command=lambda: (self.entry_filter.delete(0, "end"), self._ucitaj_logove())
                       ).pack(side="left", padx=4)

        self.textbox_logovi = ctk.CTkTextbox(tab, height=380, font=ctk.CTkFont(size=10))
        self.textbox_logovi.pack(padx=8, fill="both", expand=True)

        self._ucitaj_logove()

    def _ucitaj_logove(self):
        filter_dat = self.entry_filter.get().strip() or None
        rows = ucitaj_logove(filter_dat)

        self.textbox_logovi.delete("0.0", "end")
        for r in rows:
            vreme = r["vreme"][:19].replace("T", " ") if r["vreme"] else ""
            linija = f"{vreme}  [{r['radnik']}]  {r['uredjaj']}  →  {r['akcija']}\n"
            self.textbox_logovi.insert("end", linija)

    # ---- TAB LOZINKA ----

    def _tab_lozinka(self):
        tab = self.tabview.tab("Lozinka")

        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(expand=True)

        ctk.CTkLabel(frame, text="Promjena admin lozinke",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(pady=16)

        ctk.CTkLabel(frame, text="Nova lozinka:").pack()
        self.entry_nova_loz = ctk.CTkEntry(frame, width=200, show="*")
        self.entry_nova_loz.pack(pady=4)

        ctk.CTkLabel(frame, text="Ponovi lozinku:").pack()
        self.entry_ponovi_loz = ctk.CTkEntry(frame, width=200, show="*")
        self.entry_ponovi_loz.pack(pady=4)

        ctk.CTkButton(
            frame, text="Spremi lozinku", width=180,
            fg_color="#22c55e", hover_color="#16a34a",
            command=self._promijeni_lozinku
        ).pack(pady=12)

    def _promijeni_lozinku(self):
        nova = self.entry_nova_loz.get()
        ponovi = self.entry_ponovi_loz.get()
        if nova != ponovi:
            messagebox.showerror("Greška", "Lozinke se ne podudaraju!")
            return
        if len(nova) < 4:
            messagebox.showerror("Greška", "Lozinka mora imati najmanje 4 znaka!")
            return
        promijeni_lozinku(nova)
        messagebox.showinfo("Uspjeh", "Lozinka uspješno promijenjena!")
        self.entry_nova_loz.delete(0, "end")
        self.entry_ponovi_loz.delete(0, "end")
