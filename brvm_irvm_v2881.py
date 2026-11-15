"""BRVM Radar V2.8.8.1 — fiscalité des dividendes (module isolé).
Taux de travail communiqués par l'utilisateur, non validés juridiquement.
Aucune requête réseau, aucune écriture PostgreSQL.
"""
from dataclasses import dataclass
from typing import Optional

RATES = {
    "BJ": {"physical": 5.0, "legal": None},
    "BF": {"physical": 12.5, "legal": None},
    "CI": {"physical": 12.0, "legal": 10.0},
    "ML": {"physical": 7.0, "legal": None},
    "NE": {"physical": 7.0, "legal": None},
    "SN": {"physical": 10.0, "legal": None},
    "TG": {"physical": 3.0, "legal": 7.0},
}
ISSUER_COUNTRY = {
    "SMBC": "CI", "SMB": "CI", "BOAB": "BJ",
}
# Pilote : montant net connu, sans inférer de dividende brut.
# Source documentaire à rapprocher de l'avis de paiement officiel.
DIVIDEND_REFERENCES = {
    "BOAB": {
        "year": 2025, "net": 585.0, "gross": None,
        "source": "BOAB — dividende net 2025 de référence ; avis officiel à rapprocher",
        "status": "REFERENCE_TO_VERIFY",
    },
}
def rate_for(ticker, investor_type="physical"):
    country = ISSUER_COUNTRY.get(str(ticker).upper())
    return RATES.get(country, {}).get(investor_type)

def calculate(gross=None, net=None, rate=None):
    """Ne taxe jamais un montant déjà net; ne reconstitue pas un brut non vérifié."""
    if gross is not None and gross < 0 or net is not None and net < 0:
        raise ValueError("Un dividende ne peut être négatif.")
    if rate is not None and not 0 <= rate < 100:
        raise ValueError("Taux IRVM invalide.")
    if net is not None:
        return float(net)
    if gross is None or rate is None:
        return None
    return float(gross) * (1 - rate / 100.0)

def reference_for(ticker):
    return DIVIDEND_REFERENCES.get(str(ticker).upper())
