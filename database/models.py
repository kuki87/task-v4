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
            tip TEXT
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
