# Caffe & Gaming Zone

Desktop aplikacija za svakodnevnu operativu gaming kafića: upravljanje gaming
uređajima, sesijama i smjenama, quick POS prodaju, rezervacije, finansijske
preglede i administraciju korisnika. Aplikacija je napisana u Pythonu, koristi
PySide6 za interfejs i SQLite za lokalnu bazu podataka.

## Funkcionalnosti

- start i naplata regularnih, prepaid, Pass 1, Pass 2 i Minecraft sesija;
- transfer aktivne sesije i njene nenaplaćene košarice na drugi uređaj;
- dodavanje artikala na aktivni uređaj i zasebna quick POS prodaja na šanku;
- otvaranje, preuzimanje i zatvaranje smjene;
- automatska naplata aktivnih sesija pri zatvaranju smjene;
- recovery aktivnih sesija i nenaplaćenih artikala nakon restarta ili pada;
- operativni dashboard trenutne smjene;
- read-only historija aktivnih i završenih sesija;
- periodični poslovni izvještaji i TXT/PDF izvoz;
- pojedinačne i grupne rezervacije sa atomskom provjerom konflikta;
- dnevni timeline rezervacija po uređaju;
- automatski prijedlog slobodnih uređaja za grupnu rezervaciju;
- korisnički login, role, centralne dozvole i role-aware navigacija;
- upravljanje korisnicima, uređajima, artiklima i cijenama;
- audit log poslovnih i administrativnih akcija;
- operativni alert bar koji prikazuje najhitnije upozorenje i broj dodatnih.

## Sesije, smjene i prodaja

| Tip sesije | Ponašanje | Naplata |
|---|---|---|
| `neograniceno` | Timer broji naviše bez limita | Po cijeni uređaja pri naplati |
| `prepaid` | Odbrojavanje prema uplaćenom iznosu | Unaprijed pri startu |
| `pass1` | 5 plaćenih sati, 6 sati korištenja | Unaprijed pri startu |
| `pass2` | Ulaz od 18:00 do prije 20:00, 5 plaćenih sati | Unaprijed pri startu |
| `minecraft` | Timer broji naviše | 2,00 KM po satu pri naplati |

Parametri pass sistema i Minecraft cijena nalaze se u `constants.py`.

Artikli dodani na aktivni uređaj naplaćuju se zajedno sa sesijom. Šank ima
zasebnu košaricu i evidentira prihod kao `sank`. Pri zatvaranju smjene servis
naplaćuje sve aktivne sesije u istoj transakciji prije nego što zatvori smjenu.
Odjava korisnika ne zatvara smjenu i ne briše aktivne sesije.

## Korisnici i autentikacija

Prvo pokretanje zavisi od stanja baze:

- ako nema korisnika ni legacy admin zapisa, kreira se prvi admin nalog;
- ako postoji ispravan legacy admin zapis, postojeća lozinka se provjerava i
  atomskom migracijom kreira prvi admin nalog;
- oštećen ili parcijalan legacy zapis se ne resetuje automatski;
- nakon uspješne migracije prijava ide isključivo preko korisničkih naloga.

Lozinke novih korisnika čuvaju se kao verzionisani PBKDF2-SHA256 zapisi sa
nasumičnim saltom i 600.000 iteracija. Neaktivni korisnik se ne može prijaviti,
a zaštićeni servisi ponovo čitaju trenutno stanje korisnika i role iz baze.
Posljednji aktivni admin ne može biti deaktiviran niti izgubiti admin rolu.

Odjava se auditira, trenutni prozor i njegov actor state se uklanjaju, a nova
prijava dobija svježe dozvole iz baze. Ako smjena ostane otvorena, novi korisnik
je može eksplicitno preuzeti. Preuzimanje se auditira, a otvorena smjena dobija
`user_id` i ime korisnika koji ju je preuzeo.

### Role i dozvole

Matrica je definisana centralno u `services/permissions.py` i koriste je i UI
navigacija i servisne provjere.

| Dozvola | admin | manager | radnik |
|---|:---:|:---:|:---:|
| `pos.use` | ✓ | ✓ | ✓ |
| `shift.open` | ✓ | ✓ | ✓ |
| `shift.close` | ✓ | ✓ | ✓ |
| `reservation.manage` | ✓ | ✓ | ✓ |
| `dashboard.view` | ✓ | ✓ | ✓ |
| `report.view` | ✓ | ✓ | — |
| `session_history.view` | ✓ | ✓ | — |
| `audit.view` | ✓ | ✓ | — |
| `device.manage` | ✓ | — | — |
| `article.manage` | ✓ | — | — |
| `user.manage` | ✓ | — | — |

## Rezervacije

### Pojedinačne rezervacije

Pojedinačna rezervacija čuva stabilni ID uređaja, termin, ime gosta, telefon,
napomenu, autora i status. Podržani statusi su:

- `rezervisano`;
- `stigao`;
- `zavrseno`;
- `otkazano`;
- `no_show`.

Uobičajeni tok je `rezervisano → stigao → zavrseno`. Rezervisana rezervacija
se može i otkazati ili označiti kao `no_show`. Završeni statusi više ne blokiraju
termin.

Konflikt postoji kada važe oba uslova:

```text
nova.pocetak < postojeca.kraj
nova.kraj > postojeca.pocetak
```

Zbog stroge nejednakosti termini koji se samo dodiruju su dozvoljeni.

### Grupne rezervacije

`rezervacijske_grupe` je stabilni parent zapis sa zajedničkim gostom, kontaktom,
terminom, napomenom i statusom. Svaki rezervisani uređaj ima svoj child red u
`rezervacije`, povezan preko `grupa_id`.

Grupa mora imati najmanje dva uređaja. Kreiranje i izmjena grupe rade pod
`BEGIN IMMEDIATE`: servis jednim set-based upitom provjerava sve odabrane
uređaje prije INSERT/UPDATE operacija. Ako samo jedan uređaj ima konflikt,
cijela operacija se rollbackuje. Promjena statusa parenta i svih child redova
takođe je atomska. Prilikom izmjene vlastiti child redovi ne računaju se kao
konflikt.

Dijalog može filtrirati uređaje po tipu i grupi te predložiti traženi broj
slobodnih uređaja. Finalnu provjeru dostupnosti uvijek ponavlja servis unutar
write transakcije.

### Dnevni timeline

Rezervacije imaju tabelarni i timeline pogled. Timeline prikazuje:

- jedan red po uređaju i horizontalnu vremensku osu;
- blok proporcionalan početku i trajanju rezervacije;
- pojedinačne i grupne rezervacije sa statusnim stilom;
- klik na blok za detalje ili izmjenu dozvoljene rezervacije;
- vertikalni i horizontalni scroll.

Timeline učitava rezervacije jednim periodskim queryjem i grupiše ih po uređaju
u memoriji. Nema drag-and-dropa ni kompleksnog zooma; promjena termina ide kroz
dijalog i servisnu validaciju.

## Operativni dashboard smjene

Dashboard prikazuje:

- ukupan pazar te prihode od računara, artikala uz računare i šanka;
- broj aktivnih i slobodnih uređaja;
- broj aktivnih prepaid/pass sesija;
- sesije kojima uskoro ističe vremenski limit;
- početak i trenutno trajanje smjene;
- broj prodanih artikala i top 5 artikala po količini;
- posljednjih 5 transakcija;
- jednostavan trend kumulativnog pazara.

Finansijski i operativni agregati osvježavaju se nakon poslovnog događaja.
Sekundni timer mijenja samo prikaz trajanja smjene i countdown iz već učitanih
podataka; ne ponavlja kompletne SQL agregate svake sekunde.

## Historija sesija

Historija je read-only i prikazuje najnovije sesije prve, uz paginaciju po 100
redova. Dostupni su filteri po datumu OD/DO, uređaju, tipu, statusu
aktivna/završena i tekstualna pretraga. Prikazuju se početak, kraj, trajanje,
smjena, radnik te evidentirani iznosi računara i artikala.

Trenutna šema nema stabilni `sesija_id` na `prodaja_artikala`. Zbog toga se za
historijsku sesiju ne prikazuje izmišljena lista naziva i količina artikala, a
servis eksplicitno označava da detalji artikala nisu dostupni po sesiji.

## Izvještaji

### Izvještaj zatvorene smjene

Nakon uspješnog zatvaranja smjene aplikacija generiše tekstualni izvještaj i
pokušava generisati PDF. Greška generisanja ili prikaza izvještaja ne vraća već
zatvorenu smjenu; korisnik dobija upozorenje, a greška se loguje.

### Periodični poslovni izvještaji

Period OD–DO je uključiv na oba kraja u UI-u. Servis ga obrađuje kao interval od
početka dana OD do početka dana poslije DO. Dostupni preset periodi su:

- danas i juče;
- ova i prošla sedmica;
- ovaj i prošli mjesec.

Izvještaj sadrži finansijske agregate, broj i tipove sesija, trajanja, top
uređaje, artikle, smjene i satni ili dnevni trend. Rezultat se može izvesti u
TXT i PDF. `reportlab` je naveden u `requirements.txt`; ako nije dostupan, PDF
izvoz se evidentira kao greška, dok TXT ostaje dostupan.

Model trenutno ima tri relevantna ograničenja: šank čuva zbirni iznos bez
naziva i količine artikala, imenovani artikli se filtriraju po vremenu dodavanja
na uređaj, a prihod uređaja prati oznaku zapisanu na transakciji.

## Recovery nakon restarta

Pri prijavi aplikacija prepoznaje otvorenu smjenu i nudi nastavak/preuzimanje.
Za svaki aktivni `sesije_log` zapis (`vreme_kraja IS NULL`) obnavlja se:

- `SessionState` sa stvarnim tipom i vremenom početka;
- `limit_sekundi` za prepaid/pass sesije kada je sačuvan;
- odgovarajuće session zastavice;
- agregirana nenaplaćena košarica uređaja iz `prodaja_artikala`.

Recovery je read-only: ne stvara nove lifecycle, prodajne ili pazar zapise.
Aktivna sesija čiji uređaj više ne postoji ostaje u bazi, loguje se i prikazuje
kao upozorenje umjesto da bude tiho odbačena.

## Baza podataka

Baza je `caffe.db` u korijenu projekta i automatski se inicijalizuje pri prvom
pokretanju.

| Tabela | Namjena |
|---|---|
| `uredjaji` | Gaming uređaji, cijena, tip, grupa i legacy runtime kolone |
| `artikli` | Šifarnik artikala i aktuelnih cijena |
| `smjene` | Početak/kraj smjene, radnik, pazar i stabilni korisnik |
| `sesije_log` | Lifecycle sesije, tip, vrijeme, limit i iznos |
| `prodaja_artikala` | Artikli dodani uređaju i status naplate |
| `pazar_arhiva` | Finansijske transakcije po smjeni i tipu prodaje |
| `logovi` | Audit zapis sa actorom, akcijom, entitetom i detaljem |
| `config` | Legacy auth kompatibilnost i konfiguracijski key/value zapisi |
| `korisnici` | Korisnički nalozi, password hash, rola i aktivnost |
| `rezervacije` | Pojedinačne rezervacije i child redovi grupnih rezervacija |
| `rezervacijske_grupe` | Parent podaci i zajednički status grupne rezervacije |

`pazar_arhiva.tip_prodaje` razlikuje `racunar`, `prepaid`, `pass1`, `pass2`,
`minecraft`, `artikal` i `sank`.

SQLite konekcija uključuje WAL, foreign key provjeru i busy timeout. Migracije
su idempotentne; migracija grupnih rezervacija čuva stare individualne
rezervacije sa `NULL grupa_id`.

## Arhitektura

Slojevi prate tok:

```text
database/ → models/ → services/ → ui/
```

- `database/` upravlja konekcijom, tabelama i migracijama;
- `models/` sadrži runtime state i domenske strukture;
- `services/` sadrži poslovne validacije, autorizaciju, transakcije i SQL;
- `ui/` prikazuje PySide6 interfejs i poziva servisni sloj.

Servisni sloj nema Qt zavisnosti. UI ne izvršava SQL direktno, a lifecycle
inicijalizacija/zatvaranje konekcije ostaje u glavnom prozoru. Vrijednosti u SQL
upitima prosljeđuju se parametrizovano. Finansijske promjene koje zahtijevaju
audit upisuju poslovni podatak i audit u istoj transakciji.

## Struktura projekta

```text
task v4.0/
├── main.py                       # Entry point
├── constants.py                  # Putanja baze i session/pass konstante
├── requirements.txt
├── requirements-dev.txt
├── database/
│   ├── db.py                     # SQLite konekcija, WAL i foreign_keys
│   └── models.py                 # Tabele, migracije i početni artikli
├── models/
│   ├── app_state.py              # Trenutni korisnik i smjena
│   ├── user.py                   # UserIdentity
│   ├── session_state.py          # Aktivna sesija i timer
│   └── artikal.py                # Stavka košarice
├── services/
│   ├── auth.py                   # PBKDF2 i legacy auth podrška
│   ├── users.py                  # Korisnički nalozi i login
│   ├── permissions.py            # Centralna matrica dozvola
│   ├── audit.py                  # Audit upis i read-only pregled
│   ├── pazar.py                  # Sesije, naplata, dashboard i historija
│   ├── smjena.py                 # Lifecycle smjene
│   ├── uredjaji.py               # Uređaji i recovery query
│   ├── rezervacije.py            # Individualne i grupne rezervacije
│   ├── izvjestaj.py              # TXT/PDF export
│   └── izvjestaj_perioda.py      # Agregati periodičnog izvještaja
├── ui/
│   ├── glavni_prozor.py          # Operativni ekran i role-aware navigacija
│   ├── login.py                  # Login i first-run tok
│   ├── kartica_uredjaja.py       # Uređaj, session timer i naredna rezervacija
│   ├── rezervacije.py            # Tabela i grupni reservation dijalog
│   ├── timeline_rezervacija.py   # Dnevni timeline
│   ├── korisnici.py              # Upravljanje korisnicima
│   ├── audit.py                  # Read-only audit pregled
│   ├── historija_sesija.py       # Historija i filteri
│   ├── prikaz_pazara.py          # Dashboard smjene
│   └── izvjestaji.py             # Periodični poslovni izvještaji
└── tests/                        # Service i headless pytest-qt regresioni testovi
```

## Instalacija na Windowsu

Potreban je Python 3.13 ili noviji.

```powershell
git clone https://github.com/kuki87/task-v4.git
cd task-v4

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Za razvoj i testove:

```powershell
python -m pip install -r requirements-dev.txt
```

Ako PowerShell execution policy blokira aktivaciju virtualnog okruženja, koristi
interpreter direktno:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Pokretanje

```powershell
python main.py
```

Bez aktivacije virtualnog okruženja:

```powershell
.\.venv\Scripts\python.exe main.py
```

Baza, migracije i početni artikli kreiraju se automatski.

## Testovi

Testovi koriste privremene SQLite baze i headless Qt konfiguraciju.

```powershell
python -m pytest -q
```

Aktuelni rezultat nakon TASK 16.0:

```text
272 passed
```

## Generisani fajlovi

Git ignoriše lokalnu bazu i njene WAL/SHM fajlove, logove, izvještaje,
`graphify-out/` te Python/test cache fajlove, uključujući:

```text
__pycache__/
*.py[cod]
.pytest_cache/
```

## Poznata ograničenja

- Timeline rezervacija nema drag-and-drop ni kompleksan zoom.
- Sistem ne može zaključiti koji su uređaji fizički „jedan do drugog“.
- Grupna rezervacija ima zajednički status; nema parcijalne statuse po uređaju.
- Historija nema stabilan exact join između artikla i konkretne sesije.
- Šank historijski čuva zbirni iznos, ne nazive i količine pojedinačnih artikala.
- Alert bar prikazuje najhitnije upozorenje i broj preostalih upozorenja.

## Status

Aktivan razvoj, verzija 4.0.
