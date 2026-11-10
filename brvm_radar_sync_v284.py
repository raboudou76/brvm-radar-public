"""V2.8.4: synchronisation financière et préremplissage contrôlé (lecture seule)."""
import pandas as pd
from brvm_radar_postgres_v281 import fetch_validated, financial_view, tableau_francais, graphique_financier, graphiques_ratios, libelle_financier


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
    st.markdown('**Montants et croissance annuelle — histogrammes avec courbe de croissance**')
    graphique_financier(st, pivot)
    historique_fr, ratios_fr = tableau_francais(pivot, ratios)
    st.dataframe(historique_fr.round(3), use_container_width=True)
    if not ratios.empty:
        st.markdown('**Ratios de rentabilité — histogrammes individuels**')
        graphiques_ratios(st, pivot, ratios)
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


def get_valuation_prefill(st, ticker):
    """Retourne seulement les chiffres ANNUELS validés; jamais TTM, cours, titres ou dividendes."""
    result = _load(st)
    if result is None:
        return None
    valid, excluded = result
    if ticker not in set(valid['ticker']):
        return None
    subset = valid.loc[valid['ticker'].eq(ticker)].copy()
    if subset.empty:
        return None
    years = sorted(subset['fiscal_year'].astype(int).unique(), reverse=True)
    if not years:
        return None
    year = years[0]
    previous_year = year - 1
    def fact(metric, fiscal_year):
        rows = subset.loc[(subset['standardized_account'] == metric) & (subset['fiscal_year'] == fiscal_year)]
        if len(rows) != 1:
            return None
        return rows.iloc[0]
    latest_rn = fact('NET_INCOME', year)
    latest_equity = fact('EQUITY', year)
    prior_rn = fact('NET_INCOME', previous_year)
    prior_equity = fact('EQUITY', previous_year)
    def amount_m(row):
        return float(row['amount_xof']) / 1_000_000 if row is not None else None
    return {'ticker':ticker, 'year':year, 'previous_year':previous_year,
            'annual':amount_m(latest_rn), 'previous':amount_m(prior_rn),
            'equity':amount_m(latest_equity), 'prior_equity':amount_m(prior_equity),
            'precision':{name: (str(row.get('precision', 'EXACT_OR_UNSPECIFIED')) if row is not None else 'ABSENT')
                         for name,row in [('Résultat net',latest_rn),('Capitaux propres',latest_equity),
                                          ('Résultat net N-1',prior_rn),('Capitaux propres N-1',prior_equity)]}}


def render_valuation_reference(st, ticker='SMBC'):
    with st.expander('V2.8.4 — Références PostgreSQL validées (lecture seule)', expanded=False):
        result = _load(st)
        if result is None:
            return
        valid, _ = result
        subset = valid.loc[valid['ticker'].eq(ticker)].copy()
        if subset.empty:
            st.info(f'Aucune référence validée pour {ticker}.')
            return
        details = subset[['fiscal_year','standardized_account','amount_xof','precision','source_page']].copy()
        details['standardized_account'] = details['standardized_account'].map(libelle_financier)
        st.dataframe(details.rename(columns={'fiscal_year':'Exercice','standardized_account':'Indicateur','amount_xof':'Montant (FCFA)','precision':'Précision','source_page':'Page source'}), hide_index=True, use_container_width=True)
        st.info('Seuls les résultats annuels et capitaux propres vérifiés peuvent être préremplis sur confirmation. Aucun TTM, cours, nombre d’actions, dividende ou hypothèse n’est inventé.')
