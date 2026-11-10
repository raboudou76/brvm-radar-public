"""BRVM Radar V2.8.2 — read-only synchronized financial panels.
Requires brvm_radar_postgres_v281.py, Streamlit, pandas and psycopg.
"""
import pandas as pd
from brvm_radar_postgres_v281 import fetch_validated, financial_view, tableau_francais, graphique_financier, libelle_financier


def _load(st):
    url = st.secrets.get('DATABASE_URL', '')
    if not url:
        st.warning('DATABASE_URL absent des secrets Streamlit : synchronisation indisponible.')
        return None
    @st.cache_data(ttl=300, show_spinner=False)
    def read_validated(_url):
        return fetch_validated(_url)
    try:
        return read_validated(url)
    except Exception as exc:
        st.warning(f'Synchronisation PostgreSQL indisponible : {exc}')
        return None


def _money(x):
    return f'{x:,.1f}'.replace(',', ' ').replace('.', ',')


def render_synced_panel(st, ticker=None, title='Historique financier validé', key='sync'):
    st.subheader(title)
    if st.button('Rafraîchir les données financières', key=f'{key}_refresh'):
        st.cache_data.clear()
    result = _load(st)
    if result is None:
        return
    valid, excluded = result
    if not excluded.empty:
        st.warning(f'{len(excluded)} observations ambiguës exclues des calculs.')
    if valid.empty:
        st.info('Aucune donnée financière VALIDATED disponible.')
        return
    options = sorted(valid['ticker'].dropna().unique().tolist())
    if ticker is not None and ticker not in options:
        st.info(f'Pas encore de données financières validées pour {ticker}.')
        return
    selected = ticker or st.selectbox('Société financière', options, key=f'{key}_ticker')
    subset = valid[valid['ticker'].eq(selected)].copy()
    st.caption(f'{selected} · {len(subset)} observations validées · Source PostgreSQL · Lecture seule')
    pivot, ratios = financial_view(valid, selected)
    if pivot.empty:
        st.info('Historique non disponible.')
        return
    graphique_financier(st, pivot)
    historique_fr, ratios_fr = tableau_francais(pivot, ratios)
    st.dataframe(historique_fr.round(3), use_container_width=True)
    if not ratios.empty:
        st.markdown('**Croissance et rentabilité**')
        st.dataframe(ratios_fr.round(2), use_container_width=True)
    st.markdown('**Traçabilité et précision**')
    cols = [c for c in ('fiscal_year','standardized_account','amount_xof','precision','source_page','quality_status') if c in subset]
    details = subset[cols].copy()
    if 'standardized_account' in details:
        details['standardized_account'] = details['standardized_account'].map(libelle_financier)
    st.dataframe(details.rename(columns={'fiscal_year': 'Exercice', 'standardized_account': 'Indicateur', 'amount_xof': 'Montant (FCFA)', 'precision': 'Précision', 'source_page': 'Page source', 'quality_status': 'Statut'}), hide_index=True, use_container_width=True)
    if (subset['precision'].astype(str) == 'ROUNDED_MILLION').any():
        st.info('Certaines valeurs sont arrondies au million FCFA ; ne pas les interpréter comme exactes au franc près.')
    st.caption('Les marges bancaires et industrielles ne sont pas directement comparables. Les historiques ne remplacent pas des états financiers complets.')


def render_valuation_reference(st, ticker='SMBC'):
    """Display reference data only; never silently overwrite user inputs or TTM."""
    with st.expander('V2.8.2 — Références PostgreSQL validées (lecture seule)', expanded=False):
        result = _load(st)
        if result is None:
            return
        valid, excluded = result
        if ticker not in set(valid['ticker']):
            st.info(f'Aucune référence validée pour {ticker}.')
            return
        subset = valid.loc[valid['ticker'].eq(ticker)].copy()
        details = subset[['fiscal_year','standardized_account','amount_xof','precision','source_page']].copy()
        details['standardized_account'] = details['standardized_account'].map(libelle_financier)
        st.dataframe(details.rename(columns={'fiscal_year':'Exercice','standardized_account':'Indicateur','amount_xof':'Montant (FCFA)','precision':'Précision','source_page':'Page source'}), hide_index=True, use_container_width=True)
        st.info('Les données ci-dessus sont une référence de contrôle. Elles ne remplacent pas automatiquement les champs TTM, le nombre d’actions, le cours, les dividendes ou les hypothèses de valorisation.')
