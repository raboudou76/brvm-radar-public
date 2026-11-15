"""BRVM Radar V2.8.9: read-only, auditable multi-issuer synchronization pilot.
No updates to valuations, PostgreSQL, or issuer share counts.
"""
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import re
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup

DIVIDEND_PAGE = 'https://www.brvm.org/fr/esv/paiement-de-dividendes'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; BRVMRadar/2.8.9; research)'}

@st.cache_data(ttl=3600, show_spinner=False)
def discover_dividend_documents():
    """Discovery only: no interpretation of gross/net from page labels."""
    response = requests.get(DIVIDEND_PAGE, headers=HEADERS, timeout=25)
    response.raise_for_status()
    if urlparse(response.url).hostname not in ('www.brvm.org', 'brvm.org'):
        raise ValueError('Redirection vers une source non officielle')
    soup = BeautifulSoup(response.text, 'html.parser')
    records, seen = [], set()
    for a in soup.select('a[href]'):
        href = urljoin(response.url, a.get('href', ''))
        if urlparse(href).hostname not in ('www.brvm.org', 'brvm.org') or href in seen:
            continue
        label = ' '.join(a.get_text(' ', strip=True).split())
        parent = a.find_parent(['tr', 'article', 'li']) or a.parent
        context = ' '.join(parent.get_text(' ', strip=True).split())[:400] if parent else label
        if not (re.search(r'dividend|avis|paiement|\.pdf', label+' '+context+' '+href, re.I)):
            continue
        seen.add(href)
        records.append({'Document': label[:130] or 'Lien BRVM', 'Contexte': context,
                        'URL officielle': href, 'Qualification': 'À vérifier dans l’avis'})
    return records


def render_sync_panel(load_market):
    st.subheader('V2.8.9 — Synchronisation généralisée · lecture seule')
    st.caption('Aucune valeur de ce panneau ne remplace automatiquement les données de valorisation ou les références de capital.')
    st.markdown('#### 1. Cours des sociétés cotées')
    try:
        df, source_date = load_market()
        needed = {'Symbole', 'Société', 'Clôture'}
        if not needed.issubset(df.columns):
            raise ValueError('Colonnes BRVM manquantes')
        quotes = df.copy()
        quotes['Clôture'] = pd.to_numeric(quotes['Clôture'], errors='coerce')
        quotes['Statut'] = quotes['Clôture'].apply(lambda x: 'Cours présent' if pd.notna(x) and x > 0 else 'Cours indisponible')
        quotes['Source'] = 'BRVM — tableau des cours actions'
        quotes['Date source'] = source_date
        st.metric('Émetteurs récupérés', len(quotes))
        st.caption(f'Date indiquée par la BRVM : {source_date}. Les cours absents ou nuls ne sont pas remplacés par une estimation.')
        st.dataframe(quotes[['Symbole','Société','Clôture','Statut','Date source','Source']], use_container_width=True, hide_index=True)
        st.download_button('Exporter les cours et leur traçabilité (CSV)',
                           quotes.to_csv(index=False, sep=';').encode('utf-8-sig'),
                           file_name='brvm_v289_cours_audites.csv', mime='text/csv')
    except Exception as exc:
        st.warning(f'Collecte des cours non concluante : {exc}. Aucune donnée fictive injectée.')

    st.markdown('#### 2. Avis de paiement des dividendes')
    st.caption('Découverte de liens officiels uniquement. Un document doit être lu et qualifié avant tout préremplissage brut/net.')
    try:
        docs = discover_dividend_documents()
        if docs:
            st.dataframe(pd.DataFrame(docs), hide_index=True, use_container_width=True,
                         column_config={'URL officielle': st.column_config.LinkColumn('URL officielle')})
            st.download_button('Exporter le catalogue des liens (CSV)',
                               pd.DataFrame(docs).to_csv(index=False,sep=';').encode('utf-8-sig'),
                               'brvm_v289_dividendes_candidats.csv','text/csv')
        else:
            st.info('Aucun lien exploitable détecté dans la page HTML ; consulter directement la rubrique BRVM.')
    except Exception as exc:
        st.warning(f'Inventaire des avis non disponible : {exc}')
    st.link_button('Ouvrir les avis officiels BRVM', DIVIDEND_PAGE)

    st.markdown('#### 3. Nombre d’actions et opérations sur capital')
    st.info('La synchronisation du nombre d’actions n’est pas encore automatisée. Les volumes échangés ne sont jamais assimilés au nombre d’actions émises. Les références actives BOAB et SMB restent inchangées.')
    st.caption('Étape suivante : registre des opérations sur capital, justificatifs datés, contrôle des augmentations et divisions, puis validation avant activation.')
    st.caption('Lecture effectuée le '+datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')+' ; résultats éventuellement mis en cache pendant 15 à 60 minutes.')
