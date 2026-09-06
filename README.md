# POS System & Management App (Task v4.0)

Desktop aplikacija razvijena u Python-u sa **CustomTkinter** grafičkim interfejsom, namenjena za vođenje smjena, evidentiranje pazara, artikala, izvještaja i upravljanje uređajima.

---

## 🚀 Ključne Funkcionalnosti

* **Upravljanje Smjenama:** Otvaranje, praćenje i zatvaranje smjena sa automatskim obračunom pazara.
* **Rad sa Uređajima:** Praćenje aktivnih uređaja/računara, vremenskih intervala i obračun usluga.
* **Prodaja Artikala:** Evidencija prodatih artikala, zaliha i kategorija.
* **Izvještaji i Logovi:** Automatsko generisanje tekstualnih i struktuiranih izvještaja po smjenama i detaljno logovanje grešaka.
* **Admin Panel & Autentifikacija:** Zaštićene opcije za administratore i radnike.

---

## 🛠️ Tehnologije

* **Jezik:** Python 3.13+
* **GUI:** CustomTkinter / Tkinter
* **Baza podataka:** SQLite (`caffe.db`)

---

## 📁 Struktura Projekta

```text
├── services/          # Poslovna logika i rad sa bazom
│   ├── artikli.py     # Upravljanje artiklima
│   ├── auth.py        # Autentifikacija i korisnici
│   ├── izvjestaj.py   # Generisanje izvještaja
│   ├── pazar.py       # Obračun i praćenje pazara
│   └── smjena.py      # Logika za smjene
├── ui/                # Korisnički interfejs (CustomTkinter)
│   ├── admin_panel.py # Admin podešavanja
│   ├── glavni_prozor.py# Glavni ekranski prikaz
│   └── ...
├── Izvještaji/        # Automatski generisane potvrde i izvještaji
└── main.py            # Ulazna tačka za pokretanje aplikacije
