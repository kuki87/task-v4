from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SessionState:
    vreme_starta: datetime
    limit_sekundi: Optional[int] = None
    is_prepaid: bool = False
    is_pass2: bool = False
    is_minecraft: bool = False
    kosarica: list = field(default_factory=list)
    # tip: 'neograniceno' | 'prepaid' | 'pass1' | 'pass2' | 'minecraft'
    tip: str = "neograniceno"

    def elapsed_sekundi(self) -> int:
        delta = datetime.now() - self.vreme_starta
        return int(delta.total_seconds())

    def preostalo_sekundi(self) -> Optional[int]:
        if self.limit_sekundi is None:
            return None
        preostalo = self.limit_sekundi - self.elapsed_sekundi()
        return max(0, preostalo)

    def je_istekao(self) -> bool:
        if self.limit_sekundi is None:
            return False
        return self.elapsed_sekundi() >= self.limit_sekundi

    def formatiraj_timer(self) -> str:
        ukupno = self.elapsed_sekundi()
        sati = ukupno // 3600
        minute = (ukupno % 3600) // 60
        sekunde = ukupno % 60
        if sati > 0:
            return f"{sati:02d}:{minute:02d}:{sekunde:02d}"
        return f"{minute:02d}:{sekunde:02d}"

    def formatiraj_preostalo(self) -> str:
        preostalo = self.preostalo_sekundi()
        if preostalo is None:
            return ""
        sati = preostalo // 3600
        minute = (preostalo % 3600) // 60
        sekunde = preostalo % 60
        if sati > 0:
            return f"{sati:02d}:{minute:02d}:{sekunde:02d}"
        return f"{minute:02d}:{sekunde:02d}"

    def progres_prepaid(self) -> float:
        if self.limit_sekundi is None or self.limit_sekundi == 0:
            return 0.0
        elapsed = self.elapsed_sekundi()
        return min(1.0, elapsed / self.limit_sekundi)
