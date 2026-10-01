from dataclasses import dataclass


@dataclass
class Settings:
    payments_url: str = "http://payments"
