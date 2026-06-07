import customtkinter as ctk
from typing import Callable


class PrikazPazara(ctk.CTkToplevel):
    def __init__(self, parent, smjena_id_getter: Callable):
        super().__init__(parent)
        self.title("Pazar smjene")
        self.geometry("520x560")
        self.smjena_id_getter = smjena_id_getter

        self._izgraduj_ui()
        self._osvjezi()

    def _izgraduj_ui(self):
        naslov = ctk.CTkLabel(
            self, text="💰 PAZAR SMJENE",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        naslov.pack(pady=(16, 8))

        # Sumarni frame
        sumarni = ctk.CTkFrame(self, corner_radius=10)
        sumarni.pack(padx=16, fill="x", pady=4)

        self.lbl_racunari = ctk.CTkLabel(
            sumarni, text="Računari: 0.00 KM",
            font=ctk.CTkFont(size=13)
        )
        self.lbl_racunari.pack(side="left", padx=20, pady=10)

        self.lbl_sank = ctk.CTkLabel(
            sumarni, text="Šank: 0.00 KM",
            font=ctk.CTkFont(size=13)
        )
        self.lbl_sank.pack(side="left", padx=20, pady=10)

        self.lbl_ukupno = ctk.CTkLabel(
            sumarni, text="UKUPNO: 0.00 KM",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#fbbf24"
        )
        self.lbl_ukupno.pack(side="right", padx=20, pady=10)

        # Transakcije
        ctk.CTkLabel(self, text="Transakcije",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      text_color="#9ca3af").pack(pady=(8, 2))

        self.scroll = ctk.CTkScrollableFrame(self, height=380)
        self.scroll.pack(padx=16, pady=4, fill="both", expand=True)

        # Dugme zatvori
        ctk.CTkButton(
            self, text="Zatvori", width=120,
            fg_color="#6b7280", hover_color="#4b5563",
            command=self.destroy
        ).pack(pady=8)

    def _osvjezi(self):
        smjena_id = self.smjena_id_getter()
        if smjena_id is None:
            self.after(5000, self._osvjezi)
            return

        from services.pazar import dohvati_pazar_smjene
        podaci = dohvati_pazar_smjene(smjena_id)

        self.lbl_racunari.configure(text=f"Računari: {podaci['racunari']:.2f} KM")
        self.lbl_sank.configure(text=f"Šank: {podaci['sank']:.2f} KM")
        self.lbl_ukupno.configure(text=f"UKUPNO: {podaci['ukupno']:.2f} KM")

        for widget in self.scroll.winfo_children():
            widget.destroy()

        # Zaglavlje
        zag = ctk.CTkFrame(self.scroll, fg_color="#374151", corner_radius=6)
        zag.pack(fill="x", pady=(0, 2))
        for txt, w in [("Vrijeme", 120), ("Uređaj", 100), ("Tip", 90), ("Iznos", 80)]:
            ctk.CTkLabel(zag, text=txt, width=w,
                          font=ctk.CTkFont(size=10, weight="bold")).pack(side="left", padx=4)

        # Redovi transakcija
        boje = ["#1f2937", "#111827"]
        for i, t in enumerate(podaci["transakcije"]):
            red = ctk.CTkFrame(self.scroll, fg_color=boje[i % 2], corner_radius=4)
            red.pack(fill="x", pady=1)

            vreme = t["vreme"][:16].replace("T", " ") if t.get("vreme") else ""
            for txt, w in [
                (vreme, 120),
                (t.get("uredjaj", ""), 100),
                (t.get("tip_prodaje", ""), 90),
                (f"{t.get('iznos', 0):.2f} KM", 80),
            ]:
                ctk.CTkLabel(red, text=txt, width=w,
                              font=ctk.CTkFont(size=10)).pack(side="left", padx=4)

        # Auto-refresh svakih 5 sekundi
        if self.winfo_exists():
            self.after(5000, self._osvjezi)
