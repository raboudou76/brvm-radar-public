"""SMB reference snapshot. Verified public links, not a live scraper.
Financial data: https://www.ilboursa.com/marches/societe/SMBC.CI
Dividend sources: official BRVM 2025, 2024, 2023, 2022; Sika 2021.
No unverified gross dividend is inferred from a net dividend.
"""
import pandas as pd

FINANCIAL_SOURCE = "https://www.ilboursa.com/marches/societe/SMBC.CI"
DIVIDEND_SOURCES = {
    2025: "https://www.brvm.org/fr/smb-ci-paiement-de-dividendes-exercice-2025",
    2024: "https://www.brvm.org/sites/default/files/20250827_-_avis_ndeg211_brvmdg_-_paiement_de_dividendes_exercice_2024_-_smb_ci.pdf",
    2023: "https://www.brvm.org/fr/smb-cote-divoire-paiement-de-dividendes-exercice-2023",
    2022: "https://www.brvm.org/fr/smb-cote-divoire-paiement-de-dividendes-exercice-2022",
    2021: "https://www.sikafinance.com/marches/cotation_SMBC.ci",
}

def smb_financial_history():
    """Millions FCFA; exercise years 2021-2025."""
    return pd.DataFrame([
        {"Année":2021,"Chiffre d'affaires":139353,"Résultat net":8623},
        {"Année":2022,"Chiffre d'affaires":276854,"Résultat net":9421},
        {"Année":2023,"Chiffre d'affaires":247646,"Résultat net":17255},
        {"Année":2024,"Chiffre d'affaires":229061,"Résultat net":8698},
        {"Année":2025,"Chiffre d'affaires":206740,"Résultat net":13075},
    ])

def smb_dividend_history():
    """FCFA/share; NA gross when official source only reports net.
    2025 BRVM official net=800 conflicts with third-party 704; flag explicitly.
    2024 BRVM gross=700; 12% IRVM individual -> net=616.
    """
    return pd.DataFrame([
        {"Année":2021,"Dividende brut":float('nan'),"Dividende net":720.,"Statut":"Net rapporté par source secondaire","Source":DIVIDEND_SOURCES[2021]},
        {"Année":2022,"Dividende brut":float('nan'),"Dividende net":720.,"Statut":"Net publié BRVM","Source":DIVIDEND_SOURCES[2022]},
        {"Année":2023,"Dividende brut":float('nan'),"Dividende net":1080.,"Statut":"Net publié BRVM","Source":DIVIDEND_SOURCES[2023]},
        {"Année":2024,"Dividende brut":700.,"Dividende net":616.,"Statut":"Brut BRVM 700; net calculé à 12 %","Source":DIVIDEND_SOURCES[2024]},
        {"Année":2025,"Dividende brut":float('nan'),"Dividende net":800.,"Statut":"Net BRVM 800; divergence avec sources secondaires (704)","Source":DIVIDEND_SOURCES[2025]},
    ])
