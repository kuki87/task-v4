class AppState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.trenutna_smjena_id = None
            cls._instance.ime_radnika = ""
        return cls._instance

    def postavi_smjenu(self, smjena_id: int, radnik: str):
        self.trenutna_smjena_id = smjena_id
        self.ime_radnika = radnik

    def zatvori_smjenu(self):
        self.trenutna_smjena_id = None
        self.ime_radnika = ""

    def je_smjena_otvorena(self) -> bool:
        return self.trenutna_smjena_id is not None
