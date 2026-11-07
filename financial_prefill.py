"""Prefill financial data from a user-supplied PDF, with transparent provenance.
No scraping of an unverified report is represented as live automatic ingestion.
"""
import re

SMB_REFERENCE = {
    'company': 'SMB', 'year': 2025, 'equity_m': 42913.0,
    'prior_equity_m': 35294.0, 'net_income_m': 13075.0,
    'shares': 7795200, 'dividend_gross': 800.0,
    'dividend_net_individual': 704.0, 'individual_irvm_percent': 12.0,
    'financial_source': 'SMB — États financiers exercice 2025, BRVM (30 avril 2026)',
    'dividend_source': 'Dividende brut 800 FCFA/action — à confirmer dans l’avis de distribution applicable',
}

def _numbers_after_label(text, label):
    pattern = re.compile(r'(?im)^\s*'+re.escape(label)+r'\s+([\d\s\u00a0\u202f]+?)\s{2,}([\d\s\u00a0\u202f]+?)(?=\s{2,}|$)')
    for m in pattern.finditer(text):
        try:
            return [float(re.sub(r'\s','',m.group(i))) for i in (1,2)]
        except ValueError:
            pass
    return None

def extract_equity_from_pdf(data):
    """Only accept the explicit CAPITAUX PROPRES row, never infer from other totals."""
    import fitz
    doc = fitz.open(stream=data, filetype='pdf')
    for page_num, page in enumerate(doc,1):
        text=page.get_text('text',sort=True)
        for line in text.splitlines():
            if re.match(r'^\s*CAPITAUX PROPRES\s',line,re.I):
                vals=re.findall(r'(?<!\d)(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d{4,})(?!\d)',line)
                if len(vals)>=2:
                    return {'equity_m':float(re.sub(r'\s','',vals[0])),
                            'prior_equity_m':float(re.sub(r'\s','',vals[1])),
                            'page':page_num, 'line':line.strip()}
    return None

def net_dividend(gross, tax_percent):
    if gross < 0 or not (0 <= tax_percent <= 100):
        raise ValueError('Montant ou taux IRVM invalide')
    return gross*(1-tax_percent/100)
