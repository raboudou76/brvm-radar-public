"""BRVM RADAR 1.8.2: conservative live financial-report discovery and extraction.

Only extract when the existing structured extractor identifies both a period and
explicit millions-FCFA units. Missing or conflicting values are left blank.
"""
from datetime import datetime, timezone
import re
import pandas as pd
from auto_financials import discover, download_pdf
from structured_financials import extract_structured

METRICS = {"chiffre_affaires": "Chiffre d'affaires", "resultat_net": "Résultat net"}

def _is_annual(item):
    title = str(item.get('Titre','') + ' ' + item.get('Contexte','')).casefold()
    return not any(word in title for word in ('trimestre', 'trimestriel', 'semestre', 'semestriel', 't1 ', 't3 ', 's1 ', '9 mois'))

def find_reports(issuer, pages=5):
    if not issuer or len(issuer.strip()) < 2:
        return []
    found = discover(issuer.strip(), pages=pages, max_detail=18)
    return [r for r in found if r.get('PDF') and _is_annual(r)]

def parse_report(pdf_bytes, url, title):
    _, metrics, _ = extract_structured(pdf_bytes)
    if metrics.empty:
        return []
    rows = []
    for _, metric in metrics.iterrows():
        key = metric.get('Indicateur')
        if key not in METRICS or 'millions fcfa' not in str(metric.get('Unité', '')).lower():
            continue
        for year_key, value_key in [('Exercice N','2025 ou N'),('Exercice N-1','2024 ou N-1')]:
            year = pd.to_numeric(metric.get(year_key), errors='coerce')
            amount = pd.to_numeric(metric.get(value_key), errors='coerce')
            if pd.notna(year) and 2000 <= year <= 2100 and pd.notna(amount):
                rows.append({'Année':int(year), 'Indicateur':METRICS[key], 'Montant':float(amount),
                             'Source':url, 'Publication':title, 'Page PDF':metric.get('Page'),
                             'Statut':'Extraction automatique à vérifier'})
    return rows

def consolidate(records):
    """Reject conflicting figures for a given year and metric rather than choose one."""
    if not records:
        return pd.DataFrame(columns=['Année',"Chiffre d'affaires",'Résultat net']), pd.DataFrame()
    detail = pd.DataFrame(records).drop_duplicates(subset=['Année','Indicateur','Montant','Source'])
    safe = []
    for (year, metric), group in detail.groupby(['Année','Indicateur']):
        values = group['Montant'].unique()
        if len(values) == 1:
            safe.append({'Année':year, 'Indicateur':metric, 'Montant':values[0]})
        else:
            detail.loc[group.index, 'Statut'] = 'Conflit entre publications — valeur non affichée'
    if not safe:
        return pd.DataFrame(columns=['Année',"Chiffre d'affaires",'Résultat net']), detail
    history = pd.DataFrame(safe).pivot(index='Année', columns='Indicateur', values='Montant').reset_index()
    history.columns.name = None
    for metric in METRICS.values():
        if metric not in history: history[metric] = float('nan')
    return history[['Année',"Chiffre d'affaires",'Résultat net']].sort_values('Année').tail(5), detail

def sync_financials(reports, max_reports=5):
    records=[]; errors=[]
    for report in reports[:max_reports]:
        try:
            raw = download_pdf(report['URL'])
            extracted = parse_report(raw, report['URL'], report['Titre'])
            if not extracted:
                errors.append(f"{report['Titre'][:70]} : structure non reconnue ou unité non vérifiable")
            records.extend(extracted)
        except Exception as exc:
            errors.append(f"{report['Titre'][:70]} : {type(exc).__name__} — {str(exc)[:120]}")
    history, detail = consolidate(records)
    return history, detail, errors, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
