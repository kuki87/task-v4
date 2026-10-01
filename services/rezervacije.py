from datetime import date, datetime, time, timedelta
from functools import wraps
from threading import RLock
from typing import Iterable, Optional

from database.db import get_db
from services.audit import upisi_audit_u_transakciji
from services.permissions import RESERVATION_MANAGE, zahtijevaj_dozvolu


STATUS_REZERVISANO = "rezervisano"
STATUS_STIGAO = "stigao"
STATUS_ZAVRSENO = "zavrseno"
STATUS_OTKAZANO = "otkazano"
STATUS_NO_SHOW = "no_show"

STATUSI_REZERVACIJE = (
    STATUS_REZERVISANO,
    STATUS_STIGAO,
    STATUS_ZAVRSENO,
    STATUS_OTKAZANO,
    STATUS_NO_SHOW,
)
STATUSI_KOJI_BLOKIRAJU = (STATUS_REZERVISANO, STATUS_STIGAO)
DOZVOLJENE_TRANZICIJE = {
    STATUS_REZERVISANO: {STATUS_STIGAO, STATUS_OTKAZANO, STATUS_NO_SHOW},
    STATUS_STIGAO: {STATUS_ZAVRSENO},
    STATUS_ZAVRSENO: set(),
    STATUS_OTKAZANO: set(),
    STATUS_NO_SHOW: set(),
}
NAZIVI_STATUSA = {
    STATUS_REZERVISANO: "Rezervisano",
    STATUS_STIGAO: "Stigao",
    STATUS_ZAVRSENO: "Završeno",
    STATUS_OTKAZANO: "Otkazano",
    STATUS_NO_SHOW: "Nije došao",
}
_reservation_write_lock = RLock()


def _serijalizuj_upis(funkcija):
    @wraps(funkcija)
    def omotac(*args, **kwargs):
        with _reservation_write_lock:
            return funkcija(*args, **kwargs)

    return omotac


def _datum_vrijeme(vrijednost, naziv: str) -> datetime:
    if isinstance(vrijednost, datetime):
        return vrijednost.replace(microsecond=0)
    if isinstance(vrijednost, str):
        try:
            return datetime.fromisoformat(vrijednost).replace(microsecond=0)
        except ValueError as exc:
            raise ValueError(f"{naziv} nije ispravan datum i vrijeme.") from exc
    raise ValueError(f"{naziv} nije ispravan datum i vrijeme.")


def _tekst(vrijednost: Optional[str]) -> Optional[str]:
    if vrijednost is None:
        return None
    rezultat = str(vrijednost).strip()
    return rezultat or None


def _provjeri_osnovne_podatke(
    uredjaj_id: int,
    ime_gosta: str,
    pocetak,
    kraj,
) -> tuple[datetime, datetime]:
    ime = _tekst(ime_gosta)
    if not ime:
        raise ValueError("Ime gosta je obavezno.")
    pocetak_dt = _datum_vrijeme(pocetak, "Početak")
    kraj_dt = _datum_vrijeme(kraj, "Kraj")
    if pocetak_dt >= kraj_dt:
        raise ValueError("Početak rezervacije mora biti prije kraja.")
    if pocetak_dt < datetime.now().replace(microsecond=0):
        raise ValueError("Nije moguće rezervisati termin u prošlosti.")
    conn = get_db()
    if conn.execute("SELECT 1 FROM uredjaji WHERE id = ?", (uredjaj_id,)).fetchone() is None:
        raise ValueError("Odabrani uređaj više ne postoji.")
    return pocetak_dt, kraj_dt


def provjeri_konflikt_rezervacije(
    uredjaj_id: int,
    pocetak,
    kraj,
    izuzmi_id: Optional[int] = None,
):
    pocetak_dt = _datum_vrijeme(pocetak, "Početak")
    kraj_dt = _datum_vrijeme(kraj, "Kraj")
    if pocetak_dt >= kraj_dt:
        raise ValueError("Početak rezervacije mora biti prije kraja.")
    sql = """
        SELECT r.id, r.ime_gosta, r.pocetak, r.kraj, r.status, u.ime AS uredjaj
        FROM rezervacije r
        JOIN uredjaji u ON u.id = r.uredjaj_id
        WHERE r.uredjaj_id = ?
          AND r.status IN (?, ?)
          AND r.pocetak < ?
          AND r.kraj > ?
    """
    parametri = [
        uredjaj_id,
        STATUS_REZERVISANO,
        STATUS_STIGAO,
        kraj_dt.isoformat(),
        pocetak_dt.isoformat(),
    ]
    if izuzmi_id is not None:
        sql += " AND r.id <> ?"
        parametri.append(izuzmi_id)
    sql += " ORDER BY r.pocetak, r.id LIMIT 1"
    return get_db().execute(sql, parametri).fetchone()


@_serijalizuj_upis
def kreiraj_rezervaciju(
    uredjaj_id: int,
    ime_gosta: str,
    pocetak,
    kraj,
    actor,
    telefon: Optional[str] = None,
    napomena: Optional[str] = None,
    smjena_id: Optional[int] = None,
) -> int:
    pocetak_dt, kraj_dt = _provjeri_osnovne_podatke(
        uredjaj_id, ime_gosta, pocetak, kraj
    )
    actor = zahtijevaj_dozvolu(actor, RESERVATION_MANAGE)
    conn = get_db()
    sada = datetime.now().replace(microsecond=0).isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        konflikt = provjeri_konflikt_rezervacije(uredjaj_id, pocetak_dt, kraj_dt)
        if konflikt:
            raise ValueError(
                f"Termin se preklapa s rezervacijom "
                f"{konflikt['pocetak']}–{konflikt['kraj']}."
            )
        red = conn.execute("SELECT ime FROM uredjaji WHERE id = ?", (uredjaj_id,)).fetchone()
        cursor = conn.execute(
            """INSERT INTO rezervacije
               (uredjaj_id, ime_gosta, telefon, pocetak, kraj, status,
                napomena, kreirano, izmijenjeno, kreirao_radnik,
                kreirao_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uredjaj_id,
                ime_gosta.strip(),
                _tekst(telefon),
                pocetak_dt.isoformat(),
                kraj_dt.isoformat(),
                STATUS_REZERVISANO,
                _tekst(napomena),
                sada,
                sada,
                actor.ime,
                actor.id,
            ),
        )
        rezervacija_id = cursor.lastrowid
        upisi_audit_u_transakciji(
            conn,
            actor,
            "RESERVATION_CREATED",
            "rezervacija",
            entitet_id=rezervacija_id,
            smjena_id=smjena_id,
            uredjaj=red["ime"],
            detalj=f"Termin {pocetak_dt.isoformat()}–{kraj_dt.isoformat()}.",
        )
        conn.commit()
        return rezervacija_id
    except Exception:
        conn.rollback()
        raise


def dohvati_rezervaciju(rezervacija_id: int):
    return get_db().execute(
        """SELECT r.*, u.ime AS uredjaj, u.tip AS tip_uredjaja
           FROM rezervacije r
           JOIN uredjaji u ON u.id = r.uredjaj_id
           WHERE r.id = ?""",
        (rezervacija_id,),
    ).fetchone()


@_serijalizuj_upis
def izmijeni_rezervaciju(
    rezervacija_id: int,
    uredjaj_id: int,
    ime_gosta: str,
    pocetak,
    kraj,
    actor,
    telefon: Optional[str] = None,
    napomena: Optional[str] = None,
    smjena_id: Optional[int] = None,
) -> None:
    pocetak_dt, kraj_dt = _provjeri_osnovne_podatke(
        uredjaj_id, ime_gosta, pocetak, kraj
    )
    actor = zahtijevaj_dozvolu(actor, RESERVATION_MANAGE)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        postojeca = dohvati_rezervaciju(rezervacija_id)
        if postojeca is None:
            raise ValueError("Rezervacija ne postoji.")
        if postojeca["status"] != STATUS_REZERVISANO:
            raise ValueError(
                "Mijenjati se može samo rezervacija u statusu 'rezervisano'."
            )
        konflikt = provjeri_konflikt_rezervacije(
            uredjaj_id, pocetak_dt, kraj_dt, rezervacija_id
        )
        if konflikt:
            raise ValueError(
                f"Termin se preklapa s rezervacijom "
                f"{konflikt['pocetak']}–{konflikt['kraj']}."
            )
        red = conn.execute("SELECT ime FROM uredjaji WHERE id = ?", (uredjaj_id,)).fetchone()
        conn.execute(
            """UPDATE rezervacije
               SET uredjaj_id = ?, ime_gosta = ?, telefon = ?, pocetak = ?, kraj = ?,
                   napomena = ?, izmijenjeno = ?
               WHERE id = ?""",
            (
                uredjaj_id,
                ime_gosta.strip(),
                _tekst(telefon),
                pocetak_dt.isoformat(),
                kraj_dt.isoformat(),
                _tekst(napomena),
                datetime.now().replace(microsecond=0).isoformat(),
                rezervacija_id,
            ),
        )
        upisi_audit_u_transakciji(
            conn,
            actor,
            "RESERVATION_UPDATED",
            "rezervacija",
            entitet_id=rezervacija_id,
            smjena_id=smjena_id,
            uredjaj=red["ime"],
            detalj=f"Izmijenjena; status {postojeca['status']}.",
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


@_serijalizuj_upis
def promijeni_status_rezervacije(
    rezervacija_id: int,
    novi_status: str,
    actor,
    smjena_id: Optional[int] = None,
) -> None:
    if novi_status not in STATUSI_REZERVACIJE:
        raise ValueError("Nepoznat status rezervacije.")
    actor = zahtijevaj_dozvolu(actor, RESERVATION_MANAGE)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        postojeca = dohvati_rezervaciju(rezervacija_id)
        if postojeca is None:
            raise ValueError("Rezervacija ne postoji.")
        stari_status = postojeca["status"]
        if novi_status not in DOZVOLJENE_TRANZICIJE[stari_status]:
            raise ValueError(
                f"Prelaz iz statusa '{stari_status}' u '{novi_status}' nije dozvoljen."
            )
        conn.execute(
            "UPDATE rezervacije SET status = ?, izmijenjeno = ? WHERE id = ?",
            (
                novi_status,
                datetime.now().replace(microsecond=0).isoformat(),
                rezervacija_id,
            ),
        )
        akcije_statusa = {
            STATUS_STIGAO: "RESERVATION_ARRIVED",
            STATUS_ZAVRSENO: "RESERVATION_FINISHED",
            STATUS_OTKAZANO: "RESERVATION_CANCELLED",
            STATUS_NO_SHOW: "RESERVATION_NO_SHOW",
        }
        upisi_audit_u_transakciji(
            conn,
            actor,
            akcije_statusa[novi_status],
            "rezervacija",
            entitet_id=rezervacija_id,
            smjena_id=smjena_id,
            uredjaj=postojeca["uredjaj"],
            detalj=f"Status: {stari_status} → {novi_status}.",
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def otkazi_rezervaciju(
    rezervacija_id: int, actor, smjena_id: Optional[int] = None
) -> None:
    promijeni_status_rezervacije(
        rezervacija_id, STATUS_OTKAZANO, actor, smjena_id
    )


def _granice_dana(vrijednost) -> tuple[datetime, datetime]:
    if isinstance(vrijednost, str):
        vrijednost = date.fromisoformat(vrijednost)
    if not isinstance(vrijednost, date):
        raise ValueError("Datum nije ispravan.")
    pocetak = datetime.combine(vrijednost, time.min)
    return pocetak, pocetak + timedelta(days=1)


def dohvati_rezervacije(
    datum=None,
    uredjaj_id: Optional[int] = None,
    status: Optional[str] = None,
    pretraga: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> list:
    if limit < 1 or limit > 500 or offset < 0:
        raise ValueError("Limit ili offset nije ispravan.")
    uslovi = []
    parametri = []
    if datum is not None:
        od, do = _granice_dana(datum)
        uslovi.append("r.pocetak >= ? AND r.pocetak < ?")
        parametri.extend((od.isoformat(), do.isoformat()))
    if uredjaj_id is not None:
        uslovi.append("r.uredjaj_id = ?")
        parametri.append(uredjaj_id)
    if status is not None:
        if status not in STATUSI_REZERVACIJE:
            raise ValueError("Nepoznat status rezervacije.")
        uslovi.append("r.status = ?")
        parametri.append(status)
    if pretraga and pretraga.strip():
        obrazac = f"%{pretraga.strip()}%"
        uslovi.append("(r.ime_gosta LIKE ? OR COALESCE(r.telefon, '') LIKE ? OR u.ime LIKE ?)")
        parametri.extend((obrazac, obrazac, obrazac))
    gdje = f"WHERE {' AND '.join(uslovi)}" if uslovi else ""
    parametri.extend((limit, offset))
    return get_db().execute(
        f"""SELECT r.*, u.ime AS uredjaj, u.tip AS tip_uredjaja
            FROM rezervacije r
            JOIN uredjaji u ON u.id = r.uredjaj_id
            {gdje}
            ORDER BY r.pocetak, r.id
            LIMIT ? OFFSET ?""",
        parametri,
    ).fetchall()


def dohvati_narednu_rezervaciju_uredjaja(uredjaj_id: int, sada=None):
    sada_dt = _datum_vrijeme(sada or datetime.now(), "Vrijeme")
    return get_db().execute(
        """SELECT r.*, u.ime AS uredjaj
           FROM rezervacije r
           JOIN uredjaji u ON u.id = r.uredjaj_id
           WHERE r.uredjaj_id = ? AND r.status IN (?, ?) AND r.kraj > ?
           ORDER BY r.pocetak, r.id LIMIT 1""",
        (
            uredjaj_id,
            STATUS_REZERVISANO,
            STATUS_STIGAO,
            sada_dt.isoformat(),
        ),
    ).fetchone()


def dohvati_naredne_rezervacije_uredjaja(
    uredjaj_ids: Iterable[int], sada=None
) -> dict:
    ids = list(dict.fromkeys(int(uid) for uid in uredjaj_ids))
    if not ids:
        return {}
    sada_dt = _datum_vrijeme(sada or datetime.now(), "Vrijeme")
    placeholders = ", ".join("?" for _ in ids)
    redovi = get_db().execute(
        f"""SELECT r.*, u.ime AS uredjaj
            FROM rezervacije r
            JOIN uredjaji u ON u.id = r.uredjaj_id
            WHERE r.uredjaj_id IN ({placeholders})
              AND r.status IN (?, ?)
              AND r.kraj > ?
            ORDER BY r.uredjaj_id, r.pocetak, r.id""",
        [*ids, STATUS_REZERVISANO, STATUS_STIGAO, sada_dt.isoformat()],
    ).fetchall()
    rezultat = {}
    for red in redovi:
        rezultat.setdefault(red["uredjaj_id"], red)
    return rezultat
