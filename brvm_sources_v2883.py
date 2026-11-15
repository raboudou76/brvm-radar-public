"""Sources documentaires officielles V2.8.8.3, lecture seule.
Les références de capital sont des snapshots datés, PAS une synchronisation live.
"""
SHARE_REFERENCES = {
    "BOAB": {"shares": 40561048, "as_of": "2026-11-13 (référence de contrôle)",
             "source": "BRVM — opération sur capital 2024 / référence de contrôle; justificatif détaillé à revalider", "status": "CONTROL_REFERENCE"},
    "SMBC": {"shares": 7795200, "as_of": "2021-08-16 (fiche historique)",
             "source": "BRVM — fiche émetteur; confirmer les opérations sur capital ultérieures", "status": "HISTORICAL"},
}
DIVIDEND_REFERENCES = {
    "BOAB": {"year": 2025, "amount": 585.0, "kind": "NET", "status": "OFFICIAL_NOTICE",
             "url": "https://www.brvm.org/sites/default/files/20260508_-_avis_ndeg121_brvmdg_-_paiement_de_dividendes_exo_2025_-_boab.pdf"},
    "SMBC": {"year": 2025, "amount": 800.0, "kind": "ANNONCE_NON_QUALIFIEE",
             "status": "NOTICE_REVIEWED",
             "url": "https://www.brvm.org/fr/esv/paiement-de-dividendes"},
}
def share_reference(ticker):
    return SHARE_REFERENCES.get(str(ticker).upper())
def dividend_reference(ticker):
    return DIVIDEND_REFERENCES.get(str(ticker).upper())
