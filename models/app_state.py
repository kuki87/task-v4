class AppState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.trenutna_smjena_id = None
            cls._instance.ime_radnika = ""
            cls._instance.user_id = None
            cls._instance.username = ""
            cls._instance.ime = ""
            cls._instance.rola = ""
        return cls._instance

    def prijavi_korisnika(self, korisnik):
        from services.permissions import normalizuj_identitet

        identitet = normalizuj_identitet(korisnik)
        self.user_id = identitet.id
        self.username = identitet.username
        self.ime = identitet.ime
        self.rola = identitet.rola

    def trenutni_korisnik(self):
        if self.user_id is None:
            return None
        from models.user import UserIdentity

        return UserIdentity(self.user_id, self.username, self.ime, self.rola)

    def je_korisnik_prijavljen(self) -> bool:
        return self.user_id is not None

    def ima_dozvolu(self, dozvola: str) -> bool:
        from services.permissions import ima_dozvolu

        return ima_dozvolu(self.rola, dozvola)

    def odjavi_korisnika(self):
        self.zatvori_smjenu()
        self.user_id = None
        self.username = ""
        self.ime = ""
        self.rola = ""

    def postavi_smjenu(self, smjena_id: int, radnik: str = ""):
        self.trenutna_smjena_id = smjena_id
        self.ime_radnika = radnik or self.ime

    def zatvori_smjenu(self):
        self.trenutna_smjena_id = None
        self.ime_radnika = ""

    def je_smjena_otvorena(self) -> bool:
        return self.trenutna_smjena_id is not None
