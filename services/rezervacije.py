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


def _normalizuj_uredjaj_ids(uredjaj_ids: Iterable[int]) -> list[int]:
    try:
        rezultat = list(dict.fromkeys(int(uid) for uid in uredjaj_ids))
    except (TypeError, ValueError) as exc:
        raise ValueError("Lista uređaja nije ispravna.") from exc
    if len(rezultat) < 2:
        raise ValueError("Grupna rezervacija mora imati najmanje 2 uređaja.")
    return rezultat


def _provjeri_zajednicke_podatke(
    ime_gosta: str, pocetak, kraj
) -> tuple[str, datetime, datetime]:
    ime = _tekst(ime_gosta)
    if not ime:
        raise ValueError("Ime gosta je obavezno.")
    pocetak_dt = _datum_vrijeme(pocetak, "Početak")
    kraj_dt = _datum_vrijeme(kraj, "Kraj")
    if pocetak_dt >= kraj_dt:
        raise ValueError("Početak rezervacije mora biti prije kraja.")
    if pocetak_dt < datetime.now().replace(microsecond=0):
        raise ValueError("Nije moguće rezervisati termin u prošlosti.")
    return ime, pocetak_dt, kraj_dt


def _dohvati_uredjaje_u_transakciji(conn, uredjaj_ids: list[int]) -> dict[int, dict]:
    placeholders = ", ".join("?" for _ in uredjaj_ids)
    redovi = conn.execute(
        f"""SELECT id, ime, tip, grupa FROM uredjaji
            WHERE id IN ({placeholders}) ORDER BY grupa, ime, id""",
        uredjaj_ids,
    ).fetchall()
    rezultat = {red["id"]: dict(red) for red in redovi}
    nedostaju = [str(uid) for uid in uredjaj_ids if uid not in rezultat]
    if nedostaju:
        raise ValueError(
            "Odabrani uređaji više ne postoje: " + ", ".join(nedostaju) + "."
        )
    return rezultat


def _dohvati_konflikte_u_transakciji(
    conn,
    uredjaj_ids: list[int],
    pocetak_dt: datetime,
    kraj_dt: datetime,
    *,
    izuzmi_rezervacija_id: Optional[int] = None,
    izuzmi_grupa_id: Optional[int] = None,
) -> list:
    placeholders = ", ".join("?" for _ in uredjaj_ids)
    sql = f"""
        SELECT r.id, r.grupa_id, r.ime_gosta, r.pocetak, r.kraj,
               r.status, u.id AS uredjaj_id, u.ime AS uredjaj
        FROM rezervacije r
        JOIN uredjaji u ON u.id = r.uredjaj_id
        WHERE r.uredjaj_id IN ({placeholders})
          AND r.status IN (?, ?)
          AND r.pocetak < ?
          AND r.kraj > ?
    """
    parametri = [
        *uredjaj_ids,
        STATUS_REZERVISANO,
        STATUS_STIGAO,
        kraj_dt.isoformat(),
        pocetak_dt.isoformat(),
    ]
    if izuzmi_rezervacija_id is not None:
        sql += " AND r.id <> ?"
        parametri.append(izuzmi_rezervacija_id)
    if izuzmi_grupa_id is not None:
        sql += " AND (r.grupa_id IS NULL OR r.grupa_id <> ?)"
        parametri.append(izuzmi_grupa_id)
    sql += " ORDER BY u.ime, r.pocetak, r.id"
    return conn.execute(sql, parametri).fetchall()


def _poruka_konflikta(konflikti: list) -> str:
    uredjaji = ", ".join(dict.fromkeys(red["uredjaj"] for red in konflikti))
    return f"Termin se preklapa na uređajima: {uredjaji}."


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
    konflikti = _dohvati_konflikte_u_transakciji(
        get_db(), [uredjaj_id], pocetak_dt, kraj_dt,
        izuzmi_rezervacija_id=izuzmi_id,
    )
    return konflikti[0] if konflikti else None


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
        """SELECT r.*, u.ime AS uredjaj, u.tip AS tip_uredjaja,
                  CASE WHEN r.grupa_id IS NULL THEN NULL ELSE
                      (SELECT COUNT(*) FROM rezervacije rg
                       WHERE rg.grupa_id = r.grupa_id)
                  END AS grupa_velicina
           FROM rezervacije r
           JOIN uredjaji u ON u.id = r.uredjaj_id
           WHERE r.id = ?""",
        (rezervacija_id,),
    ).fetchone()


def dohvati_rezervacijsku_grupu(grupa_id: int) -> Optional[dict]:
    conn = get_db()
    grupa = conn.execute(
        "SELECT * FROM rezervacijske_grupe WHERE id = ?", (grupa_id,)
    ).fetchone()
    if grupa is None:
        return None
    rezultat = dict(grupa)
    rezultat["uredjaji"] = [
        dict(red) for red in conn.execute(
            """SELECT u.id, u.ime, u.tip, u.grupa, r.id AS rezervacija_id
               FROM rezervacije r
               JOIN uredjaji u ON u.id = r.uredjaj_id
               WHERE r.grupa_id = ?
               ORDER BY u.grupa, u.ime, u.id""",
            (grupa_id,),
        ).fetchall()
    ]
    return rezultat


@_serijalizuj_upis
def kreiraj_rezervacijsku_grupu(
    uredjaj_ids: Iterable[int],
    ime_gosta: str,
    pocetak,
    kraj,
    actor,
    telefon: Optional[str] = None,
    napomena: Optional[str] = None,
    smjena_id: Optional[int] = None,
) -> int:
    ids = _normalizuj_uredjaj_ids(uredjaj_ids)
    ime, pocetak_dt, kraj_dt = _provjeri_zajednicke_podatke(
        ime_gosta, pocetak, kraj
    )
    actor = zahtijevaj_dozvolu(actor, RESERVATION_MANAGE)
    conn = get_db()
    sada = datetime.now().replace(microsecond=0).isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        uredjaji = _dohvati_uredjaje_u_transakciji(conn, ids)
        konflikti = _dohvati_konflikte_u_transakciji(
            conn, ids, pocetak_dt, kraj_dt
        )
        if konflikti:
            raise ValueError(_poruka_konflikta(konflikti))

        cursor = conn.execute(
            """INSERT INTO rezervacijske_grupe
               (ime_gosta, telefon, pocetak, kraj, status, napomena,
                kreirao_user_id, kreirao_radnik, kreirano, azurirano)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ime, _tekst(telefon), pocetak_dt.isoformat(), kraj_dt.isoformat(),
                STATUS_REZERVISANO, _tekst(napomena), actor.id, actor.ime,
                sada, sada,
            ),
        )
        grupa_id = int(cursor.lastrowid)
        for uredjaj_id in ids:
            conn.execute(
                """INSERT INTO rezervacije
                   (uredjaj_id, ime_gosta, telefon, pocetak, kraj, status,
                    napomena, kreirano, izmijenjeno, kreirao_radnik,
                    kreirao_user_id, grupa_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uredjaj_id, ime, _tekst(telefon), pocetak_dt.isoformat(),
                    kraj_dt.isoformat(), STATUS_REZERVISANO, _tekst(napomena),
                    sada, sada, actor.ime, actor.id, grupa_id,
                ),
            )
        nazivi = [uredjaji[uid]["ime"] for uid in ids]
        upisi_audit_u_transakciji(
            conn, actor, "RESERVATION_GROUP_CREATED", "rezervacijska_grupa",
            entitet_id=grupa_id, smjena_id=smjena_id,
            uredjaj=", ".join(nazivi),
            detalj=(
                f"Grupa #{grupa_id}; uređaji: {', '.join(nazivi)}; "
                f"termin {pocetak_dt.isoformat()}–{kraj_dt.isoformat()}."
            ),
        )
        conn.commit()
        return grupa_id
    except Exception:
        conn.rollback()
        raise


@_serijalizuj_upis
def izmijeni_rezervacijsku_grupu(
    grupa_id: int,
    uredjaj_ids: Iterable[int],
    ime_gosta: str,
    pocetak,
    kraj,
    actor,
    telefon: Optional[str] = None,
    napomena: Optional[str] = None,
    smjena_id: Optional[int] = None,
) -> None:
    ids = _normalizuj_uredjaj_ids(uredjaj_ids)
    ime, pocetak_dt, kraj_dt = _provjeri_zajednicke_podatke(
        ime_gosta, pocetak, kraj
    )
    actor = zahtijevaj_dozvolu(actor, RESERVATION_MANAGE)
    conn = get_db()
    sada = datetime.now().replace(microsecond=0).isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        grupa = conn.execute(
            "SELECT * FROM rezervacijske_grupe WHERE id = ?", (grupa_id,)
        ).fetchone()
        if grupa is None:
            raise ValueError("Grupna rezervacija ne postoji.")
        if grupa["status"] != STATUS_REZERVISANO:
            raise ValueError(
                "Mijenjati se može samo grupa u statusu 'rezervisano'."
            )
        uredjaji = _dohvati_uredjaje_u_transakciji(conn, ids)
        konflikti = _dohvati_konflikte_u_transakciji(
            conn, ids, pocetak_dt, kraj_dt, izuzmi_grupa_id=grupa_id
        )
        if konflikti:
            raise ValueError(_poruka_konflikta(konflikti))

        postojeci_ids = {
            red["uredjaj_id"] for red in conn.execute(
                "SELECT uredjaj_id FROM rezervacije WHERE grupa_id = ?",
                (grupa_id,),
            ).fetchall()
        }
        conn.execute(
            """UPDATE rezervacijske_grupe
               SET ime_gosta = ?, telefon = ?, pocetak = ?, kraj = ?,
                   napomena = ?, azurirano = ? WHERE id = ?""",
            (
                ime, _tekst(telefon), pocetak_dt.isoformat(), kraj_dt.isoformat(),
                _tekst(napomena), sada, grupa_id,
            ),
        )
        placeholders = ", ".join("?" for _ in ids)
        conn.execute(
            f"DELETE FROM rezervacije WHERE grupa_id = ? "
            f"AND uredjaj_id NOT IN ({placeholders})",
            [grupa_id, *ids],
        )
        conn.execute(
            """UPDATE rezervacije
               SET ime_gosta = ?, telefon = ?, pocetak = ?, kraj = ?,
                   napomena = ?, izmijenjeno = ? WHERE grupa_id = ?""",
            (
                ime, _tekst(telefon), pocetak_dt.isoformat(), kraj_dt.isoformat(),
                _tekst(napomena), sada, grupa_id,
            ),
        )
        for uredjaj_id in ids:
            if uredjaj_id in postojeci_ids:
                continue
            conn.execute(
                """INSERT INTO rezervacije
                   (uredjaj_id, ime_gosta, telefon, pocetak, kraj, status,
                    napomena, kreirano, izmijenjeno, kreirao_radnik,
                    kreirao_user_id, grupa_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uredjaj_id, ime, _tekst(telefon), pocetak_dt.isoformat(),
                    kraj_dt.isoformat(), STATUS_REZERVISANO, _tekst(napomena),
                    sada, sada, actor.ime, actor.id, grupa_id,
                ),
            )
        nazivi = [uredjaji[uid]["ime"] for uid in ids]
        upisi_audit_u_transakciji(
            conn, actor, "RESERVATION_GROUP_UPDATED", "rezervacijska_grupa",
            entitet_id=grupa_id, smjena_id=smjena_id,
            uredjaj=", ".join(nazivi),
            detalj=(
                f"Grupa #{grupa_id}; uređaji: {', '.join(nazivi)}; "
                f"termin {pocetak_dt.isoformat()}–{kraj_dt.isoformat()}."
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


@_serijalizuj_upis
def promijeni_status_rezervacijske_grupe(
    grupa_id: int,
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
        grupa = conn.execute(
            "SELECT * FROM rezervacijske_grupe WHERE id = ?", (grupa_id,)
        ).fetchone()
        if grupa is None:
            raise ValueError("Grupna rezervacija ne postoji.")
        stari_status = grupa["status"]
        if novi_status not in DOZVOLJENE_TRANZICIJE[stari_status]:
            raise ValueError(
                f"Prelaz iz statusa '{stari_status}' u '{novi_status}' nije dozvoljen."
            )
        sada = datetime.now().replace(microsecond=0).isoformat()
        conn.execute(
            "UPDATE rezervacijske_grupe SET status = ?, azurirano = ? WHERE id = ?",
            (novi_status, sada, grupa_id),
        )
        conn.execute(
            "UPDATE rezervacije SET status = ?, izmijenjeno = ? WHERE grupa_id = ?",
            (novi_status, sada, grupa_id),
        )
        uredjaji = [
            red["ime"] for red in conn.execute(
                """SELECT u.ime FROM rezervacije r
                   JOIN uredjaji u ON u.id = r.uredjaj_id
                   WHERE r.grupa_id = ? ORDER BY u.ime""",
                (grupa_id,),
            ).fetchall()
        ]
        akcije = {
            STATUS_STIGAO: "RESERVATION_GROUP_ARRIVED",
            STATUS_ZAVRSENO: "RESERVATION_GROUP_COMPLETED",
            STATUS_OTKAZANO: "RESERVATION_GROUP_CANCELLED",
            STATUS_NO_SHOW: "RESERVATION_GROUP_NO_SHOW",
        }
        upisi_audit_u_transakciji(
            conn, actor, akcije[novi_status], "rezervacijska_grupa",
            entitet_id=grupa_id, smjena_id=smjena_id,
            uredjaj=", ".join(uredjaji),
            detalj=(
                f"Grupa #{grupa_id}; uređaji: {', '.join(uredjaji)}; "
                f"status {stari_status} → {novi_status}."
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


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
        if postojeca["grupa_id"] is not None:
            raise ValueError("Grupna rezervacija se mijenja kao cjelina.")
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
        if postojeca["grupa_id"] is not None:
            raise ValueError("Status grupne rezervacije mijenja se kao cjelina.")
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


def dohvati_slobodne_uredjaje_za_period(
    pocetak,
    kraj,
    *,
    tip: Optional[str] = None,
    grupa: Optional[str] = None,
    broj: Optional[int] = None,
    izuzmi_grupa_id: Optional[int] = None,
) -> list:
    pocetak_dt = _datum_vrijeme(pocetak, "Početak")
    kraj_dt = _datum_vrijeme(kraj, "Kraj")
    if pocetak_dt >= kraj_dt:
        raise ValueError("Početak rezervacije mora biti prije kraja.")
    if broj is not None and broj < 1:
        raise ValueError("Traženi broj uređaja nije ispravan.")
    limit = broj if broj is not None else 500
    tip = _tekst(tip)
    grupa = _tekst(grupa)
    return get_db().execute(
        """SELECT u.id, u.ime, u.tip, u.grupa, u.cena
           FROM uredjaji u
           WHERE (? IS NULL OR u.tip = ?)
             AND (? IS NULL OR u.grupa = ?)
             AND NOT EXISTS (
                 SELECT 1 FROM rezervacije r
                 WHERE r.uredjaj_id = u.id
                   AND r.status IN (?, ?)
                   AND r.pocetak < ?
                   AND r.kraj > ?
                   AND (? IS NULL OR r.grupa_id IS NULL OR r.grupa_id <> ?)
             )
           ORDER BY u.grupa, u.tip, u.ime, u.id
           LIMIT ?""",
        (
            tip, tip, grupa, grupa,
            STATUS_REZERVISANO, STATUS_STIGAO,
            kraj_dt.isoformat(), pocetak_dt.isoformat(),
            izuzmi_grupa_id, izuzmi_grupa_id, limit,
        ),
    ).fetchall()


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
        f"""SELECT r.*, u.ime AS uredjaj, u.tip AS tip_uredjaja,
                   CASE WHEN r.grupa_id IS NULL THEN NULL ELSE
                       (SELECT COUNT(*) FROM rezervacije rg
                        WHERE rg.grupa_id = r.grupa_id)
                   END AS grupa_velicina
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
        """SELECT r.*, u.ime AS uredjaj, u.tip AS tip_uredjaja,
                  CASE WHEN r.grupa_id IS NULL THEN NULL ELSE
                      (SELECT COUNT(*) FROM rezervacije rg
                       WHERE rg.grupa_id = r.grupa_id)
                  END AS grupa_velicina
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
        f"""SELECT r.*, u.ime AS uredjaj, u.tip AS tip_uredjaja,
                   CASE WHEN r.grupa_id IS NULL THEN NULL ELSE
                       (SELECT COUNT(*) FROM rezervacije rg
                        WHERE rg.grupa_id = r.grupa_id)
                   END AS grupa_velicina
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
