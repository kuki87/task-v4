import sys
import logging
import traceback
from datetime import datetime
from database.db import get_db

# Fajl logger za greške
logging.basicConfig(
    filename="caffe_errors.log",
    level=logging.ERROR,
    format="%(asctime)s — %(levelname)s — %(message)s",
    encoding="utf-8"
)


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
        logging.error(f"Greška pri upisivanju loga: {e}")


def _global_exception_handler(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.error(f"Neuhvaćena greška:\n{error_msg}")


sys.excepthook = _global_exception_handler
