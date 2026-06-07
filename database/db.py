import sqlite3
import threading
from constants import DB_PATH
from database.models import kreiraj_tabele, pokreni_migracije

_lock = threading.Lock()
_connection = None


def get_db() -> sqlite3.Connection:
    global _connection
    with _lock:
        if _connection is None:
            _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
            _connection.row_factory = sqlite3.Row
            _connection.execute("PRAGMA journal_mode=WAL")
            _connection.execute("PRAGMA foreign_keys=ON")
            _connection.commit()
    return _connection


def inicijalizuj_bazu():
    conn = get_db()
    kreiraj_tabele(conn)
    pokreni_migracije(conn)
