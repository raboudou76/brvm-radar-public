"""Position-aware extraction of native-text, side-by-side financial statement PDFs.
No OCR and no guessed amounts. Every extracted value retains its PDF page.
"""
import re
import unicodedata
import pandas as pd
from finance_engine import parse_amount

METRICS = {
 'chiffre_affaires': ('resultat', r'^chiffre d.affaires$'),
 'resultat_net': ('resultat', r'^resultat net$'),
 'resultat_exploitation': ('resultat', r'^resultat d.exploitation$'),
 'ebe': ('resultat', r'^excedent brut d.exploitation$'),
 'total_actif': ('bilan', r'^total actif$'),
 'total_passif': ('bilan', r'^total passif$'),
 'capitaux_propres': ('bilan', r'^capitaux propres$'),
 'dettes_financieres': ('bilan', r'^emprunts (?:&|et) dettes financieres$'),
 'tresorerie_actif': ('bilan', r'^tresorerie - actif$'),
 'flux_operationnel': ('tresorerie', r'^flux de tresorerie provenant des activites operationnelles'),
 'flux_investissement': ('tresorerie', r'^flux de tresorerie provenant des activites d.investissements'),
 'flux_financement': ('tresorerie', r'^flux de tresorerie provenant des activites de financement'),
 'dividendes_verses': ('tresorerie', r'^dividendes verses$'),
 'capex_decaissements': ('tresorerie', r'^decaissements lies aux acquisitions d.immobilisations'),
 'encaissements_cessions': ('tresorerie', r'^encaissements lies aux acquisitions d.immobilisations'),
}

def norm(s):
    t=unicodedata.normalize('NFKD',str(s).lower())
    return ' '.join(''.join(c for c in t if not unicodedata.combining(c)).split())

def grouped_words(words, tol=2.4):
    lines=[]
    for w in sorted(words,key=lambda w:(w[1],w[0])):
        y=(w[1]+w[3])/2
        if lines and abs(lines[-1]['y']-y)<=tol:
            lines[-1]['words'].append(w)
        else: lines.append({'y':y,'words':[w]})
    return lines

def region_rows(page, bbox, section, page_no):
    x0,y0,x1,y1=bbox
    words=[w for w in page.get_text('words') if x0<=((w[0]+w[2])/2)<=x1 and y0<=((w[1]+w[3])/2)<=y1]
    # The numeric columns are detected by the 2025/2024 headers, not guessed from the text order.
    headers=[w for w in words if re.fullmatch(r'20\d{2}',w[4]) and w[1]<y0+35]
    headers=sorted(headers,key=lambda w:w[0])
    if len(headers)<2:return []
    h0,h1=headers[-2:]
    year0,year1=int(h0[4]),int(h1[4])
    c0=(h0[0]+h0[2])/2; c1=(h1[0]+h1[2])/2
    split=(c0+c1)/2
    label_limit=c0-15
    rows=[]; pending=None
    for line in grouped_words(words):
        if line['y']<max(h0[3],h1[3])+1:continue
        ws=sorted(line['words'],key=lambda w:w[0])
        label=' '.join(w[4] for w in ws if (w[0]+w[2])/2<label_limit)
        v0=' '.join(w[4] for w in ws if label_limit <= (w[0]+w[2])/2 <split)
        v1=' '.join(w[4] for w in ws if (w[0]+w[2])/2>=split)
        a,b=parse_amount(v0),parse_amount(v1)
        if label and a is None and b is None:
            pending=(label,line['y'])
            continue
        if a is None and b is None:continue
        if not label and pending and line['y']-pending[1]<5:
            label=pending[0]
        if not label:continue
        rows.append({'Section':section,'Libellé':label,'Année N':year0,'Valeur N':a,'Année N-1':year1,'Valeur N-1':b,'Page':page_no,'Y':round(line['y'],1)})
        pending=None
    return rows

def extract_structured(pdf_bytes):
    import fitz
    if len(pdf_bytes)>25*1024*1024:raise ValueError('PDF supérieur à 25 Mo')
    doc=fitz.open(stream=pdf_bytes,filetype='pdf')
    if doc.page_count>100:raise ValueError('PDF supérieur à 100 pages')
    rows=[]
    for idx,page in enumerate(doc):
        # The three regions are detected from statement headings on this known compact layout.
        text=norm(page.get_text('text'))
        if not all(t in text for t in ['bilan','compte de resultat','tableau de flux de tresorerie']):continue
        w,h=page.rect.width,page.rect.height
        regions=[((.18*w,.11*h,.47*w,.59*h),'bilan'),((.48*w,.11*h,.82*w,.55*h),'resultat'),((.48*w,.55*h,.82*w,.91*h),'tresorerie')]
        for bbox,section in regions:rows.extend(region_rows(page,bbox,section,idx+1))
    doc.close()
    df=pd.DataFrame(rows,columns=['Section','Libellé','Année N','Valeur N','Année N-1','Valeur N-1','Page','Y'])
    metrics=[]
    for key,(section,pattern) in METRICS.items():
        if df.empty:break
        matches=df[(df['Section']==section)&df['Libellé'].map(lambda x:bool(re.search(pattern,norm(x))))]
        # Wrapped rows can split long labels. Match a prefix to the first numeric row.
        if matches.empty and key.startswith('flux_'):
            short={'flux_operationnel':'flux de tresorerie provenant des','flux_investissement':'flux de tresorerie provenant des','flux_financement':'flux de tresorerie provenant des'}[key]
            subset=df[(df['Section']==section)&df['Libellé'].map(lambda x:norm(x).startswith(short))]
            order={'flux_operationnel':0,'flux_investissement':1,'flux_financement':2}[key]
            if len(subset)>order:matches=subset.iloc[[order]]
        if len(matches)==1:
            r=matches.iloc[0]
            metrics.append({'Indicateur':key,'2025 ou N':r['Valeur N'],'2024 ou N-1':r['Valeur N-1'],'Exercice N':r['Année N'],'Exercice N-1':r['Année N-1'],'Unité':'millions FCFA' if 'en millions de fcfa' in norm(text) else 'à confirmer','Page':r['Page'],'Libellé source':r['Libellé'],'Statut':'Extrait automatiquement — à contrôler'})
    m=pd.DataFrame(metrics)
    checks=[]
    if not m.empty:
        by={r['Indicateur']:r for _,r in m.iterrows()}
        for year,col in [('N','2025 ou N'),('N-1','2024 ou N-1')]:
            if 'total_actif' in by and 'total_passif' in by:
                a,b=by['total_actif'][col],by['total_passif'][col]
                checks.append({'Contrôle':f'Bilan équilibré {year}','Écart (millions FCFA)':a-b,'Résultat':'OK' if a==b else 'ÉCART'})
    return df,m,pd.DataFrame(checks)
