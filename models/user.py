from dataclasses import dataclass


@dataclass(frozen=True)
class UserIdentity:
    id: int
    username: str
    ime: str
    rola: str

    @classmethod
    def iz_reda(cls, red):
        return cls(
            id=int(red["id"]),
            username=str(red["korisnicko_ime"]),
            ime=str(red["ime"]),
            rola=str(red["rola"]),
        )
