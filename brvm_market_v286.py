"""V2.8.6: BRVM official BOC discovery and conservative close extraction.
Never interprets trading volume as shares outstanding. Read-only.
"""
import re
from datetime import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import fitz

LISTING = 'https://www.brvm.org/fr/bulletins-officiels-de-la-cote'
HEADERS = {'User-Agent':'Mozilla/5.0 (compatible; BRVMRadar/2.8.6; financial research)'}
MONTHS = {'janvier':1,'février':2,'fevrier':2,'mars':3,'avril':4,'mai':5,'juin':6,'juillet':7,'août':8,'aout':8,'septembre':9,'octobre':10,'novembre':11,'décembre':12,'decembre':12}

class OfficialSourceError(ValueError): pass

def _fetch(url):
    if not url.startswith('https://www.brvm.org/'):
        raise OfficialSourceError('Domaine non autorisé : seul brvm.org est accepté.')
    r=requests.get(url,headers=HEADERS,timeout=22,allow_redirects=True)
    r.raise_for_status()
    if not r.url.startswith('https://www.brvm.org/'):
        raise OfficialSourceError('Redirection hors du domaine officiel BRVM.')
    if len(r.content)>20_000_000:raise OfficialSourceError('Document trop volumineux.')
    return r.content

def latest_official_boc():
    html=_fetch(LISTING)
    soup=BeautifulSoup(html,'html.parser')
    candidates=[]
    pattern=re.compile(r'Bulletin Officiel de la Cote du\s+(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(20\d\d)',re.I)
    for node in soup.find_all(string=pattern):
        m=pattern.search(str(node))
        if not m:continue
        month=MONTHS.get(m.group(2).lower())
        if not month:continue
        try:date=datetime(int(m.group(3)),month,int(m.group(1))).date()
        except ValueError:continue
        parent=node.parent
        link=parent.find('a',href=True) if parent else None
        if link is None and parent and parent.parent:link=parent.parent.find('a',href=True)
        if link:
            url=urljoin(LISTING,link['href'])
            if url.startswith('https://www.brvm.org/') and '.pdf' in url.lower():candidates.append((date,url))
    if not candidates:raise OfficialSourceError('Aucun lien PDF officiel identifiable dans la liste des BOC.')
    return max(candidates,key=lambda x:x[0])

def _num(s):
    return int(re.sub(r'[\s\u00a0\u202f]','',s))

def extract_close_from_pdf(pdf_bytes, ticker):
    """Read BRVM equity close using PDF word geometry and the Clôt. column.

    Only accepts a ticker row under a header explicitly labelled Clôt.;
    never substitutes previous, opening, reference price or traded volume.
    """
    ticker = ticker.upper().strip()
    if not re.fullmatch(r'[A-Z]{3,6}', ticker):
        raise OfficialSourceError('Ticker invalide.')
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    results = []
    for page_index, page in enumerate(doc):
        words = page.get_text('words')
        headers = [w for w in words if w[4].lower().strip() in ('clôt.', 'clot.', 'clôture')]
        if not headers:
            continue
        for header in headers:
            hx = (header[0] + header[2]) / 2
            for target in (w for w in words if w[4].upper() == ticker and w[1] > header[3]):
                cy = (target[1] + target[3]) / 2
                # Ignore unrelated table sections or page headings.
                row = [w for w in words if abs((w[1] + w[3]) / 2 - cy) < 3.0]
                # The closing-price cell is located directly below Clôt.,
                # with its numeric groups positioned around the header center.
                cell = sorted([w for w in row if hx - 10 <= (w[0]+w[2])/2 <= hx + 17], key=lambda w:w[0])
                raw = ''.join(w[4] for w in cell).replace('\u202f','').replace('\xa0','')
                if not re.fullmatch(r'\d{1,7}', raw):
                    continue
                price = int(raw)
                if not 1 <= price <= 5_000_000:
                    continue
                results.append((price, page_index + 1, ' '.join(w[4] for w in sorted(row,key=lambda w:w[0]))))
    # Deduplicate overlapping headers on the same page/row.
    results = list(dict.fromkeys(results))
    if len(results) != 1:
        raise OfficialSourceError(f'Clôture {ticker} non déterminable sans ambiguïté dans le PDF ({len(results)} lignes). Vérifier la mise en page.')
    price, page, raw = results[0]
    return {'ticker':ticker,'price_xof':price,'pdf_page':page,'raw_row':raw}

def get_official_market_price(ticker):
    date,url=latest_official_boc()
    pdf=_fetch(url)
    result=extract_close_from_pdf(pdf,ticker)
    result.update({'date':date.isoformat(),'url':url,'source':'BRVM — Bulletin Officiel de la Cote'})
    return result

# Number of shares is intentionally NOT derived from the BOC's daily traded volume.
# An independently verifiable issuer filing or validated share-capital register is required.
def extract_shares_from_issuer_pdf(pdf_bytes):
    doc=fitz.open(stream=pdf_bytes,filetype='pdf')
    patterns=[r'(?:nombre|total)\s+(?:d[’\']|des\s+)?actions\s+(?:en\s+circulation\s*)?(?:est\s+de|:)?\s*([\d\s.]{5,20})',
              r'capital\s+(?:est\s+)?(?:divis[ée]\s+en|compos[ée]\s+de)\s*([\d\s.]{5,20})\s+actions']
    hits=[]
    for page_num,p in enumerate(doc):
        text=' '.join(p.get_text().split())
        for pat in patterns:
            for m in re.finditer(pat,text,re.I):
                raw=m.group(1).strip().rstrip('.')
                try:
                    n=int(re.sub(r'[\s.]','',raw))
                    if n>=1000:hits.append((n,page_num+1,m.group(0)))
                except ValueError:pass
    unique={n for n,_,_ in hits}
    if len(unique)!=1:raise OfficialSourceError('Nombre d’actions non identifié de manière univoque dans le rapport officiel.')
    n=next(iter(unique));page=next(page for value,page,_ in hits if value==n)
    return {'shares':n,'pdf_page':page,'evidence':next(e for value,_,e in hits if value==n)}
