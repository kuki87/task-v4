# Caffe & Gaming Zone, POS i upravljanje smjenama (task v4.0)

Desktop aplikacija u Python-u sa **PySide6 (Qt)** interfejsom, namijenjena vođenju smjena,
evidenciji pazara, prodaji artikala, praćenju gaming uređaja i generisanju izvještaja.

---

## Ključne funkcionalnosti

* **Smjene** — otvaranje i zatvaranje smjene po radniku, prenos aktivnih sesija i nenaplaćenih artikala u novu smjenu.
* **Uređaji** — PC i PS5 stanice grupisane po grupama, praćenje vremena i obračun po satu.
* **Pass sistemi** — Neograničeno, Prepaid, Pass 1, Pass 2 i Minecraft pass.
* **Šank** — zasebna košarica za prodaju artikala koji nisu vezani za uređaj.
* **Artikli na uređaju** — dodavanje pića i grickalica na aktivnu sesiju, naplata zajedno sa sesijom.
* **Izvještaji** — tekstualni izvještaj smjene, PDF opcionalno (ako je `reportlab` instaliran).
* **Logovi** — akcije radnika u bazi, neuhvaćene greške u `caffe_errors.log`.
* **Admin panel** — zaštićen lozinkom, upravljanje uređajima, artiklima i cijenama grupa.

---

## Tipovi sesija

| Tip | Ponašanje | Naplata |
|---|---|---|
| **Neograničeno** | Timer broji naviše, bez limita | Po satu, cijena uređaja, pri naplati |
| **Prepaid** | Timer sa limitom, odbrojava | Unaprijed, pri startu sesije |
| **Pass 1** | 5 plaćenih sati, 6 dobijenih | Unaprijed |
| **Pass 2** | Ulaz dozvoljen između 18:00 i 20:00, 5 plaćenih sati | Unaprijed |
| **Minecraft** | Timer broji naviše | 2.00 KM po satu, pri naplati |

Parametri se mijenjaju u `constants.py`.

---

## Tehnologije

* **Jezik:** Python 3.13+
* **GUI:** PySide6 (Qt 6), stilizovan preko `ui/style.qss`
* **Baza:** SQLite (`caffe.db`), WAL mod, jedna dijeljena konekcija
* **PDF (opcionalno):** reportlab

---

## Instalacija i pokretanje

```bash
git clone https://github.com/kuki87/task-v4.git
cd task-v4

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

pip install PySide6
pip install reportlab         # opcionalno, samo za PDF izvještaje

python main.py
```

Baza `caffe.db` se kreira automatski pri prvom pokretanju, zajedno sa tabelama,
migracijama i podrazumijevanim artiklima.

---

## Struktura projekta

```text
task v4.0/
├── main.py                  # Ulazna tačka, pokreće GlavniProzor
├── constants.py             # Cijene, boje, parametri pass-eva, putanja baze
│
├── database/
│   ├── db.py                # Jedna dijeljena SQLite konekcija (WAL, foreign_keys)
│   └── models.py            # CREATE TABLE definicije i migracije
│
├── models/
│   ├── session_state.py     # SessionState, jedini izvor istine za aktivnu sesiju
│   ├── app_state.py         # AppState singleton, trenutna smjena i radnik
│   └── artikal.py           # Artikal dataclass
│
├── services/                # Poslovna logika, jedini sloj koji dira bazu
│   ├── pazar.py             # Obračun sesija, naplata, arhiva pazara
│   ├── smjena.py            # Otvaranje, zatvaranje i prenos smjene
│   ├── uredjaji.py          # CRUD uređaja, cijene grupa, logovi
│   ├── artikli.py           # CRUD artikala
│   ├── auth.py              # Admin lozinka (SHA-256 + salt)
│   ├── izvjestaj.py         # Tekstualni i PDF izvještaji
│   └── logger.py            # Log akcija u bazu i global exception handler
│
├── ui/                      # PySide6 interfejs
│   ├── glavni_prozor.py     # Glavni prozor, grid uređaja, timeri
│   ├── kartica_uredjaja.py  # Kartica pojedinačnog uređaja
│   ├── bocni_panel.py       # Šank panel i košarica
│   ├── admin_panel.py       # Admin podešavanja
│   ├── dijalog_start.py     # Dijalog za pokretanje sesije
│   ├── prikaz_pazara.py     # Pregled pazara smjene
│   └── style.qss            # Qt stylesheet
│
└── Izvještaji/              # Generisani .txt i .pdf izvještaji smjena
```

---

## Arhitektura

Aplikacija poštuje strogu podjelu slojeva:

```
ui/  →  services/  →  database/
```

**Pravila:**

* UI **nikad** ne poziva bazu direktno, sve ide kroz `services/`.
* `SessionState` je jedini izvor istine o trajanju i tipu aktivne sesije.
* `AppState` je singleton koji drži ID trenutne smjene i ime radnika.
* Sve novčane vrijednosti su `float` u KM, zaokružene na 2 decimale pri upisu.

---

## Baza podataka

| Tabela | Sadržaj |
|---|---|
| `uredjaji` | Stanice, cijena, tip (PC / PS5), grupa |
| `smjene` | Početak, kraj, radnik, ukupan pazar |
| `sesije_log` | Historija sesija po uređaju sa iznosom |
| `pazar_arhiva` | Sve novčane transakcije smjene, podijeljene po `tip_prodaje` |
| `prodaja_artikala` | Artikli dodati na uređaj, sa flagom `naplaceno` |
| `artikli` | Šifarnik artikala i cijena |
| `logovi` | Akcije radnika |
| `config` | Admin hash i salt |

Vrijednosti `tip_prodaje` u `pazar_arhiva`: `racunar`, `prepaid`, `pass1`, `pass2`,
`minecraft`, `artikal`, `sank`.

---

## Admin pristup

Podrazumijevana lozinka je definisana u `constants.py` kao `ADMIN_DEFAULT_LOZINKA`.

**Promijeni je pri prvom pokretanju** kroz Admin panel. Lozinka se čuva kao SHA-256
hash sa nasumičnim salt-om u tabeli `config`.

---

## Napomene

* `.gitignore` isključuje `caffe.db`, `__pycache__/`, `*.log` i `graphify-out/`, baza se ne verzioniše.
* Ako `reportlab` nije instaliran, PDF izvještaj se tiho preskače, tekstualni se i dalje generiše.
* Projekat je prvobitno pisan u CustomTkinter-u, pa prepisan u PySide6 radi nativnijeg izgleda.
* `graphify` knowledge graph se osvježava ručno komandom `graphify update .` (vidi `CLAUDE.md`).

---

## Status

Aktivan razvoj. Verzija 4.0.
