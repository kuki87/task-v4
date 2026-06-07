from dataclasses import dataclass


@dataclass
class Artikal:
    naziv: str
    cijena: float
    kolicina: int = 1

    def ukupno(self) -> float:
        return round(self.cijena * self.kolicina, 2)

    def __str__(self) -> str:
        return f"{self.naziv} x{self.kolicina} = {self.ukupno():.2f} KM"
