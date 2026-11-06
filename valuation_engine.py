"""Conservative, traceable FCFE scenarios for non-bank issuers."""
import pandas as pd
from finance_engine import dcf_fcfe

SCENARIOS = {
    'Prudent': {'growth':-0.03,'discount':0.19,'terminal_growth':0.01},
    'Central': {'growth':0.02,'discount':0.16,'terminal_growth':0.02},
    'Optimiste': {'growth':0.05,'discount':0.14,'terminal_growth':0.025},
}

def reconstruct_fcfe(analysis):
    if not analysis.get('ready'):
        return None, 'Contrôle des bilans non validé.'
    d=analysis['data']
    def current(k):
        values=d.get(k)
        return values[0] if values else None
    op,inv,fin,div=(current(k) for k in ('flux_operationnel','flux_investissement','flux_financement','dividendes_verses'))
    if any(x is None for x in (op,inv,fin,div)):
        return None,'Flux opérationnel, investissement, financement ou dividendes manquants.'
    if div<0:
        return None,'Signe des dividendes incohérent.'
    # Financing cash flow = net borrowing - dividends paid, provided no other equity transactions.
    # This is an explicit modeling assumption, not a certified reconciliation.
    net_borrowing=fin+div
    fcfe=op+inv+net_borrowing
    return {'operating':op,'investing':inv,'financing':fin,'dividends':div,
            'net_borrowing_proxy':net_borrowing,'fcfe_proxy':fcfe,
            'year':analysis['years'][0]},''

def run_scenarios(analysis,shares,quote=None,assumptions=None):
    bridge,error=reconstruct_fcfe(analysis)
    if error:return pd.DataFrame(),None,error
    if shares is None or shares<=0:return pd.DataFrame(),bridge,'Nombre d’actions confirmé obligatoire.'
    if bridge['fcfe_proxy']<=0:return pd.DataFrame(),bridge,'FCFE de référence non positif : modèle simplifié inadapté.'
    rows=[]
    for name,params in (assumptions or SCENARIOS).items():
        result=dcf_fcfe(bridge['fcfe_proxy']*1_000_000,params['growth'],params['discount'],params['terminal_growth'],shares,5)
        v=result['value_per_share']
        rows.append({'Scénario':name,'Croissance 5 ans (%)':params['growth']*100,
            'Actualisation (%)':params['discount']*100,'Croissance terminale (%)':params['terminal_growth']*100,
            'Valeur indicative (FCFA/action)':round(v,2),'Prix max -10%':round(v*.9,2),
            'Prix max -20%':round(v*.8,2),'Prix max -30%':round(v*.7,2),
            'Poids valeur terminale (%)':round(result['terminal_share']*100,1),
            'Décote vs cours (%)':round((v/quote-1)*100,1) if quote and quote>0 else None})
    return pd.DataFrame(rows),bridge,''
