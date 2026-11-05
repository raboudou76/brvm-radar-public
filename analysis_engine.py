"""Auditable financial analytics. No fabricated fields or implicit zeros."""
import math
import pandas as pd
from finance_engine import dcf_fcfe

KEYS = {'chiffre_affaires':'Chiffre d’affaires','resultat_net':'Résultat net','resultat_exploitation':'Résultat d’exploitation','ebe':'EBE','total_actif':'Total actif','total_passif':'Total passif','capitaux_propres':'Capitaux propres','dettes_financieres':'Emprunts et dettes financières','tresorerie_actif':'Trésorerie actif','flux_operationnel':'Flux opérationnel','flux_investissement':'Flux d’investissement','flux_financement':'Flux de financement','dividendes_verses':'Dividendes versés','capex_decaissements':'Acquisitions immobilisations','encaissements_cessions':'Encaissements immobilisations'}

def normalize_indicators(indicators):
    """Extract two periods with provenance and strict numeric validation."""
    if indicators is None or indicators.empty: return {}, {}
    required={'Indicateur','2025 ou N','2024 ou N-1','Exercice N','Exercice N-1','Unité','Page'}
    if not required.issubset(indicators.columns): return {}, {}
    data={}; meta={}
    for _,r in indicators.iterrows():
        key=str(r['Indicateur'])
        if key not in KEYS or key in data:continue
        unit=str(r['Unité']).lower()
        if 'millions fcfa' not in unit:continue
        values=[]
        for col in ('2025 ou N','2024 ou N-1'):
            v=pd.to_numeric(r[col],errors='coerce')
            values.append(float(v) if pd.notna(v) and math.isfinite(float(v)) else None)
        data[key]=values
        meta[key]={'page':int(r['Page']),'unit':str(r['Unité']),'years':(int(r['Exercice N']),int(r['Exercice N-1'])),'label':str(r.get('Libellé source',''))}
    return data,meta

def fundamental_analysis(indicators):
    data,meta=normalize_indicators(indicators)
    if not data:return pd.DataFrame(),pd.DataFrame(),{'ready':False,'reason':'Aucune donnée structurée avec unité confirmée.'}
    years=next(iter(meta.values()))['years']
    def val(key,idx):return data.get(key,[None,None])[idx]
    def div(a,b):return a/b if a is not None and b is not None and b!=0 else None
    def growth(key):
        a,b=val(key,0),val(key,1)
        return (a/b-1) if a is not None and b is not None and b>0 else None
    rows=[]
    for key,label in KEYS.items():
        if key in data:
            rows.append({'Indicateur':label,str(years[0]):val(key,0),str(years[1]):val(key,1),'Unité':'millions FCFA','Page PDF':meta[key]['page']})
    ratios=[]
    for label,now,prior,unit in [
        ('Croissance CA',growth('chiffre_affaires'),None,'%'),
        ('Croissance résultat net',growth('resultat_net'),None,'%'),
        ('Marge nette',div(val('resultat_net',0),val('chiffre_affaires',0)),div(val('resultat_net',1),val('chiffre_affaires',1)),'%'),
        ('Marge opérationnelle',div(val('resultat_exploitation',0),val('chiffre_affaires',0)),div(val('resultat_exploitation',1),val('chiffre_affaires',1)),'%'),
        ('ROE sur capitaux propres de clôture',div(val('resultat_net',0),val('capitaux_propres',0)),div(val('resultat_net',1),val('capitaux_propres',1)),'%'),
        ('Dette financière / capitaux propres',div(val('dettes_financieres',0),val('capitaux_propres',0)),div(val('dettes_financieres',1),val('capitaux_propres',1)),'x'),
        ('FCF simplifié = flux opérationnel + flux investissement',None if val('flux_operationnel',0) is None or val('flux_investissement',0) is None else val('flux_operationnel',0)+val('flux_investissement',0),None if val('flux_operationnel',1) is None or val('flux_investissement',1) is None else val('flux_operationnel',1)+val('flux_investissement',1),'millions FCFA'),
    ]:
        ratios.append({'Ratio':label,str(years[0]):now*100 if now is not None and unit=='%' else now,str(years[1]):prior*100 if prior is not None and unit=='%' else prior,'Unité':unit})
    controls=[]
    for idx,year in enumerate(years):
        a,b=val('total_actif',idx),val('total_passif',idx)
        if a is not None and b is not None:controls.append((year,abs(a-b)<=1))
    ready=bool(controls) and all(ok for _,ok in controls)
    return pd.DataFrame(rows),pd.DataFrame(ratios),{'ready':ready,'years':years,'data':data,'meta':meta,'checks':controls,'reason':'Bilan non vérifié ou déséquilibré.' if not ready else ''}

def valuation_scenarios(analysis,shares=None):
    """Scenario FCFE DCF; not a verified intrinsic value. Requires a verified share count."""
    if not analysis.get('ready'):return pd.DataFrame(),'Bilans non validés.'
    d=analysis['data']; op=d.get('flux_operationnel',[None])[0]; inv=d.get('flux_investissement',[None])[0]
    if op is None or inv is None:return pd.DataFrame(),'Flux opérationnel ou investissement absent.'
    # FCF to the firm proxy, not FCFE. Never use as FCFE without net borrowing.
    return pd.DataFrame(), 'FCFE non calculable : il manque une réconciliation complète du financement net. La valeur par action reste suspendue.'
