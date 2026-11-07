"""BRVM interim cumulative reports: conservative extraction and TTM calculations.
Values are FCFA (not millions); returns no inferred missing values.
"""
import re
import unicodedata
import fitz
import pandas as pd

def normalize(s):
    s=unicodedata.normalize('NFKD',str(s).lower())
    return ' '.join(''.join(c for c in s if not unicodedata.combining(c)).split())

def parse_number(s):
    s=str(s).strip().replace('\u202f',' ').replace('\xa0',' ').replace('−','-')
    if not re.fullmatch(r'\(?-?\d[\d .]*\)?',s): return None
    neg=s.startswith('(')
    s=s.strip('()').replace(' ','').replace('.','')
    try: return -int(s) if neg else int(s)
    except ValueError: return None

METRICS={'Chiffre d’affaires':('chiffre d.affaires','chiffre d affaires'),
         'Résultat net':('resultat net','resultat net comptable'),
         'Résultat des activités ordinaires':('resultat des activites ordinaires',)}

def extract_interim(raw, period, year, unit='FCFA'):
    """Use PDF positional words; read FIRST two financial columns after the row label.
    Supports clean BRVM report table with N / N-1 columns, never guesses a year.
    """
    if period not in ('T1','S1','T3'): raise ValueError('Période inconnue')
    if unit not in ('FCFA','millions FCFA'): raise ValueError('Unité inconnue')
    doc=fitz.open(stream=raw,filetype='pdf')
    out=[]; multiplier=1_000_000 if unit=='millions FCFA' else 1
    for page_index,page in enumerate(doc):
        lines=[]
        words=page.get_text('words',sort=True)
        # Group words into visually aligned lines, preserving x position
        for word in words:
            x0,y0,x1,y1,txt,*_=word
            target=next((ln for ln in lines if abs(ln['y']-y0)<3),None)
            if target is None:
                target={'y':y0,'items':[]};lines.append(target)
            target['items'].append((x0,txt))
        for line in lines:
            items=sorted(line['items'])
            full=normalize(' '.join(t for _,t in items))
            for metric,aliases in METRICS.items():
                for alias in aliases:
                    m=re.search(r'\b'+alias+r'\b',full)
                    if not m:continue
                    # Prefer label before first numeric column; prevent false hits in prose
                    numeric=[]
                    groups=[]; current=[]; last_x=None
                    for x,t in items:
                        if re.fullmatch(r'[\d\s().−-]+',t) and re.search(r'\d',t):
                            if last_x is not None and x-last_x>28 and current:
                                groups.append(current);current=[]
                            current.append(t);last_x=x
                        elif current:
                            groups.append(current);current=[];last_x=None
                    if current:groups.append(current)
                    for group in groups:
                        val=parse_number(' '.join(group))
                        if val is not None and abs(val)>100: numeric.append(val)
                    if len(numeric)>=2:
                        out.append({'Indicateur':metric,'Période':period,'Année':year,
                                    'N':numeric[0]*multiplier,'N-1':numeric[1]*multiplier,
                                    'Page':page_index+1,'Unité saisie':unit})
                    break
    doc.close()
    # One value per metric; duplicates are ambiguous, don't silently pick.
    frame=pd.DataFrame(out)
    if frame.empty:return frame
    counts=frame.groupby('Indicateur').size()
    return frame[frame['Indicateur'].map(counts)==1].reset_index(drop=True)

def compute_ttm(annual, interim_current, interim_prior, shares, price=None):
    if min(annual,interim_current,interim_prior)<0:
        # negative net income is possible; do not reject it
        pass
    if shares<=0:raise ValueError('Nombre d’actions invalide')
    ttm=annual+interim_current-interim_prior
    eps=ttm/shares
    per=price/eps if price and eps>0 else None
    return {'Résultat net TTM (FCFA)':ttm,'BPA TTM (FCFA)':eps,'PER TTM':per,
            'Variation période (%)':(interim_current/interim_prior-1)*100 if interim_prior else None}
