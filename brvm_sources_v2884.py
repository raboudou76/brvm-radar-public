"""V2.8.8.4: métadonnées des avis documentés, sans scraping ni modification DB.
Les champs ne doivent pas être confondus avec un flux live BRVM.
"""
NOTICES = {
    'SMBC': {
        'notice_id': '261-2026/BRVM/DG',
        'fiscal_year': 2025,
        'announced_per_share': 800.0,
        'amount_kind': 'ANNOUNCED_UNQUALIFIED',
        'physical_rate': 12.0,
        'legal_rate': 10.0,
        'payment_date': '2026-09-18',
        'ex_date': '2026-09-17',
        'meeting_date': '2026-06-23',
        'source_label': 'Avis BRVM n°261-2026, image fournie par utilisateur',
        'source_url': None,
        'verification': 'NOTICE_IMAGE_REVIEWED',
    },
    'BOAB': {
        'notice_id': '121-2026/BRVM/DG',
        'fiscal_year': 2025,
        'announced_per_share': 585.0,
        'amount_kind': 'NET_EXPLICIT',
        'source_label': 'Avis de paiement BRVM BOAB exercice 2025',
        'source_url': 'https://www.brvm.org/sites/default/files/20260508_-_avis_ndeg121_brvmdg_-_paiement_de_dividendes_exo_2025_-_boab.pdf',
        'verification': 'OFFICIAL_NOTICE_REFERENCE',
    },
}

def notice_for(ticker):
    return NOTICES.get(str(ticker).upper())

def estimate_net_from_notice(ticker, investor_type):
    """Estimation seulement, jamais un net officiellement publié."""
    n = notice_for(ticker)
    if not n:
        return None
    if n['amount_kind'] == 'NET_EXPLICIT':
        return n['announced_per_share']
    rate = n.get('physical_rate' if investor_type == 'physical' else 'legal_rate')
    if rate is None:
        return None
    return n['announced_per_share'] * (1 - rate / 100)
