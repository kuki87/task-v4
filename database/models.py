import sqlite3


def kreiraj_tabele(conn: sqlite3.Connection):
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS uredjaji (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ime TEXT UNIQUE NOT NULL,
            cena REAL DEFAULT 2.0,
            tip TEXT DEFAULT 'PC',
            grupa TEXT DEFAULT 'Classic',
            vreme_starta TEXT,
            limit_sekundi INTEGER,
            is_prepaid INTEGER DEFAULT 0,
            is_pass2 INTEGER DEFAULT 0,
            is_minecraft INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sesije_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            smjena_id INTEGER,
            uredjaj TEXT,
            vreme_starta TEXT,
            vreme_kraja TEXT,
            iznos REAL,
            tip TEXT,
            limit_sekundi INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS prodaja_artikala (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vreme TEXT,
            smjena_id INTEGER,
            uredjaj TEXT,
            naziv_artikla TEXT,
            kolicina INTEGER,
            ukupna_cijena REAL,
            naplaceno INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS pazar_arhiva (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vreme TEXT,
            uredjaj TEXT,
            iznos REAL,
            smjena_id INTEGER,
            vreme_starta TEXT,
            tip_prodaje TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS smjene (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pocetak TEXT,
            kraj TEXT,
            radnik TEXT,
            pazar REAL DEFAULT 0.0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS artikli (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            naziv TEXT UNIQUE NOT NULL,
            cijena REAL NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS logovi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vreme TEXT,
            smjena_id INTEGER,
            radnik TEXT,
            uredjaj TEXT,
            akcija TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS config (
            kljuc TEXT PRIMARY KEY,
            vrijednost TEXT
        )
    """)

    conn.commit()


def pokreni_migracije(conn: sqlite3.Connection):
    c = conn.cursor()

    # Korisnički nalozi su odvojeni od legacy admin zapisa u config tabeli.
    c.execute("""
        CREATE TABLE IF NOT EXISTS korisnici (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            korisnicko_ime TEXT NOT NULL UNIQUE COLLATE NOCASE,
            ime TEXT NOT NULL CHECK (TRIM(ime) <> ''),
            password_hash TEXT NOT NULL,
            rola TEXT NOT NULL CHECK (rola IN ('admin', 'manager', 'radnik')),
            aktivan INTEGER NOT NULL DEFAULT 1 CHECK (aktivan IN (0, 1)),
            kreiran TEXT NOT NULL,
            azuriran TEXT NOT NULL,
            zadnja_prijava TEXT
        )
    """)
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_korisnici_rola_aktivan "
        "ON korisnici (rola, aktivan)"
    )
    conn.commit()

    # Migracija: dodaj kolone koje fale na tabeli uredjaji
    ocekivane_kolone = [
        ("is_minecraft", "INTEGER DEFAULT 0"),
        ("tip", "TEXT DEFAULT 'PC'"),
        ("grupa", "TEXT DEFAULT 'Classic'"),
    ]
    c.execute("PRAGMA table_info(uredjaji)")
    postojece_kolone = {red["name"] for red in c.fetchall()}
    for ime_kolone, definicija in ocekivane_kolone:
        if ime_kolone not in postojece_kolone:
            c.execute(f"ALTER TABLE uredjaji ADD COLUMN {ime_kolone} {definicija}")
    conn.commit()

    # Migracija: sačuvaj vremenski limit aktivne prepaid/pass sesije za recovery
    c.execute("PRAGMA table_info(sesije_log)")
    kolone_sesije = {red["name"] for red in c.fetchall()}
    if "limit_sekundi" not in kolone_sesije:
        c.execute("ALTER TABLE sesije_log ADD COLUMN limit_sekundi INTEGER")
        conn.commit()

    # Grupna rezervacija je stabilan parent za zajednički termin i status.
    c.execute("""
        CREATE TABLE IF NOT EXISTS rezervacijske_grupe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ime_gosta TEXT NOT NULL CHECK (TRIM(ime_gosta) <> ''),
            telefon TEXT,
            pocetak TEXT NOT NULL,
            kraj TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'rezervisano'
                CHECK (status IN ('rezervisano', 'stigao', 'zavrseno', 'otkazano', 'no_show')),
            napomena TEXT,
            kreirao_user_id INTEGER,
            kreirao_radnik TEXT NOT NULL,
            kreirano TEXT NOT NULL,
            azurirano TEXT NOT NULL,
            FOREIGN KEY (kreirao_user_id) REFERENCES korisnici(id) ON DELETE SET NULL,
            CHECK (pocetak < kraj)
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_rezervacijske_grupe_termin_status
        ON rezervacijske_grupe (pocetak, kraj, status)
    """)
    conn.commit()

    # Rezervacije su vezane za stabilni ID uređaja, a historija se čuva.
    c.execute("""
        CREATE TABLE IF NOT EXISTS rezervacije (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uredjaj_id INTEGER NOT NULL,
            ime_gosta TEXT NOT NULL CHECK (TRIM(ime_gosta) <> ''),
            telefon TEXT,
            pocetak TEXT NOT NULL,
            kraj TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'rezervisano'
                CHECK (status IN ('rezervisano', 'stigao', 'zavrseno', 'otkazano', 'no_show')),
            napomena TEXT,
            kreirano TEXT NOT NULL,
            izmijenjeno TEXT NOT NULL,
            kreirao_radnik TEXT NOT NULL,
            FOREIGN KEY (uredjaj_id) REFERENCES uredjaji(id) ON DELETE RESTRICT,
            CHECK (pocetak < kraj)
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_rezervacije_uredjaj_termin
        ON rezervacije (uredjaj_id, pocetak, kraj)
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_rezervacije_pocetak_status
        ON rezervacije (pocetak, status)
    """)
    conn.commit()

    # Nullable FK kolone čuvaju stare zapise bez nepouzdanog povezivanja po imenu.
    migracijske_kolone = {
        "smjene": [
            ("user_id", "INTEGER REFERENCES korisnici(id) ON DELETE SET NULL"),
        ],
        "rezervacije": [
            ("kreirao_user_id", "INTEGER REFERENCES korisnici(id) ON DELETE SET NULL"),
            (
                "grupa_id",
                "INTEGER REFERENCES rezervacijske_grupe(id) ON DELETE RESTRICT",
            ),
        ],
        "logovi": [
            ("user_id", "INTEGER REFERENCES korisnici(id) ON DELETE SET NULL"),
            ("username", "TEXT"),
            ("entitet", "TEXT"),
            ("entitet_id", "TEXT"),
            ("detalj", "TEXT"),
        ],
    }
    for tabela, kolone in migracijske_kolone.items():
        c.execute(f"PRAGMA table_info({tabela})")
        postojece = {red["name"] for red in c.fetchall()}
        for naziv, definicija in kolone:
            if naziv not in postojece:
                c.execute(f"ALTER TABLE {tabela} ADD COLUMN {naziv} {definicija}")
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_smjene_user_id ON smjene (user_id)"
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_logovi_user_vreme "
        "ON logovi (user_id, vreme DESC)"
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_logovi_entitet_akcija "
        "ON logovi (entitet, akcija)"
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_rezervacije_grupa_id "
        "ON rezervacije (grupa_id, uredjaj_id)"
    )
    conn.commit()

    # Migracija: ispravi PS5 uređaje koji su dobili grupu 'Classic' po defaultu
    c.execute("UPDATE uredjaji SET grupa = 'PS5' WHERE tip = 'PS5' AND grupa = 'Classic'")
    conn.commit()

    # Seed default artikli ako tabela prazna
    c.execute("SELECT COUNT(*) FROM artikli")
    if c.fetchone()[0] == 0:
        artikli = [
            ("Kafa", 1.5),
            ("Sok", 2.0),
            ("Voda", 1.0),
            ("Red Bull", 3.0),
            ("Čips", 1.5),
        ]
        c.executemany("INSERT OR IGNORE INTO artikli (naziv, cijena) VALUES (?, ?)", artikli)
        conn.commit()
