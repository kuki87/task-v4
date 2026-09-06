import os
import sys
import logging
import traceback
from datetime import datetime
from database.db import get_db
from constants import BASE_DIR

# Fajl logger za greške
log = logging.getLogger("caffe")
log.setLevel(logging.ERROR)
log.propagate = False

if not log.handlers:
    try:
        _handler = logging.FileHandler(
            os.path.join(BASE_DIR, "caffe_errors.log"), encoding="utf-8"
        )
    except OSError:
        _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s — %(levelname)s — %(message)s")
    )
    log.addHandler(_handler)


def upisi_log(smjena_id, radnik: str, uredjaj: str, akcija: str):
    try:
        conn = get_db()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO logovi (vreme, smjena_id, radnik, uredjaj, akcija) VALUES (?, ?, ?, ?, ?)",
            (now, smjena_id, radnik, uredjaj, akcija)
        )
        conn.commit()
    except Exception as e:
        log.error(f"Greška pri upisivanju loga: {e}")


def _global_exception_handler(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log.error(f"Neuhvaćena greška:\n{error_msg}")
    try:
        conn = get_db()
        if conn.in_transaction:
            conn.rollback()
            log.error("Nedovršena transakcija poništena (rollback).")
    except Exception as e:
        log.error(f"Rollback nije uspio: {e}")


sys.excepthook = _global_exception_handler
