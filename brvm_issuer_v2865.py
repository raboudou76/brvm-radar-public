"""BRVM Radar V2.8.6.5 — extraction conservative des actions sur fiches BRVM."""
import re
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

class IssuerExtractionError(ValueError):
    pass

def get_official_shares(ticker: str, url: str):
    """Return shares, reference date and evidence; never guess from other quantities."""
    ticker = ticker.strip().upper()
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('brvm.org', 'www.brvm.org') or not parsed.path.startswith('/fr/emetteurs/societes-cotees/'):
        raise IssuerExtractionError('URL de fiche émetteur BRVM non autorisée.')
    response = requests.get(url, timeout=25, headers={'User-Agent':'Mozilla/5.0 (BRVM Radar 2.8.6.5)'}, allow_redirects=True)
    response.raise_for_status()
    final = urlparse(response.url)
    if final.scheme != 'https' or final.hostname not in ('brvm.org', 'www.brvm.org'):
        raise IssuerExtractionError('Redirection vers un domaine non autorisé.')
    if len(response.content) > 5_000_000:
        raise IssuerExtractionError('Page trop volumineuse.')
    soup = BeautifulSoup(response.content, 'html.parser')
    for el in soup(['script','style','nav','footer','header']):
        el.decompose()
    text = soup.get_text(' ', strip=True).replace('\u00a0',' ')
    symbols = set(re.findall(r'\bSymbole\s*:\s*([A-Z]{3,6})\b', text, re.I))
    if ticker not in {s.upper() for s in symbols}:
        raise IssuerExtractionError(f'Symbole {ticker} non confirmé sur la fiche.')
    pattern = re.compile(r"Nombre\s+total\s+d['’]actions\s*\(\s*au\s*(\d{1,2}/\d{1,2}/20\d{2})\s*\)\s*[:|]?\s*([\d\s\u00a0\u202f]+)", re.I)
    candidates = {(m.group(1), int(re.sub(r'\D','',m.group(2)))) for m in pattern.finditer(text)}
    candidates = {(d,n) for d,n in candidates if n > 0}
    if len(candidates) != 1:
        raise IssuerExtractionError(f'Nombre d’actions non déterminable sans ambiguïté ({len(candidates)} candidats).')
    date, shares = candidates.pop()
    return {'ticker':ticker, 'shares':shares, 'reference_date':date, 'url':response.url,
            'evidence':f"Nombre total d'actions (au {date}) : {shares:,}",
            'source_type':'BRVM_ISSUER_PROFILE', 'validation_status':'OFFICIAL_HISTORICAL'}

if __name__ == '__main__':
    import sys
    print(get_official_shares(sys.argv[1], sys.argv[2]))
