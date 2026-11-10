"""BRVM Radar V2.8.1: lecture seule des faits financiers VALIDATED.
Aucun secret n'est stocké dans ce fichier.
"""
import pandas as pd

COLUMNS = ['ticker','company_name','fiscal_year','standardized_account','amount_xof',
           'precision','quality_status','source_page','report_url','fact_id','sector_type']


def fetch_validated(database_url):
    """Récupère les faits validés depuis PostgreSQL; aucune écriture SQL."""
    if not database_url:
        raise ValueError('DATABASE_URL absent des secrets Streamlit.')
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('Installer psycopg[binary] dans requirements.txt.') from exc
    sql = """
        SELECT c.ticker, c.company_name, f.fiscal_year,
               f.standardized_account, f.amount AS amount_xof,
               f.quality_status, f.source_page, f.evidence,
               f.scale_basis, f.currency_basis, f.fact_id
        FROM public.financial_facts AS f
        JOIN public.companies AS c ON c.company_id = f.company_id
        WHERE f.quality_status = 'VALIDATED'
          AND f.fiscal_year IS NOT NULL
          AND f.currency = 'XOF'
        ORDER BY c.ticker, f.fiscal_year, f.standardized_account, f.fact_id
    """
    with psycopg.connect(database_url, connect_timeout=12, options='-c statement_timeout=15000') as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute(sql)
            names = [d.name for d in cur.description]
            records = cur.fetchall()
    df = pd.DataFrame(records, columns=names)
    if df.empty:
        return validate_export(pd.DataFrame(columns=COLUMNS))
    # Les métadonnées de précision sont parfois dans evidence/scale_basis.
    # Une précision non prouvée reste non spécifiée.
    def precision(row):
        blob = ' '.join(str(row.get(k) or '') for k in ('evidence','scale_basis','currency_basis')).upper()
        if 'ROUNDED_MILLION' in blob or 'ARRONDI AU MILLION' in blob or 'ARRONDIS AU MILLION' in blob:
            return 'ROUNDED_MILLION'
        return 'EXACT_OR_UNSPECIFIED'
    df['precision'] = df.apply(precision, axis=1)
    df['sector_type'] = df['ticker'].map({'BOAB':'BANK','SMBC':'INDUSTRIAL'}).fillna('UNCLASSIFIED')
    # L'URL est une source optionnelle; ne jamais inventer un lien.
    df['report_url'] = ''
    df = df[COLUMNS]
    return validate_export(df)


def validate_export(frame):
    """Filtrage défensif pour un export DB ou un CSV contrôlé."""
    df = frame.copy()
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError('Colonnes absentes : ' + ', '.join(sorted(missing)))
    df = df.loc[df['quality_status'].astype(str).str.upper().eq('VALIDATED')].copy()
    df['amount_xof'] = pd.to_numeric(df['amount_xof'], errors='coerce')
    df['fiscal_year'] = pd.to_numeric(df['fiscal_year'], errors='coerce')
    df = df.dropna(subset=['ticker','fiscal_year','standardized_account','amount_xof'])
    df['fiscal_year'] = df['fiscal_year'].astype(int)
    df = df.loc[df['fiscal_year'].between(2000,2100)]
    keys = ['ticker','fiscal_year','standardized_account']
    ambiguous = df.duplicated(keys, keep=False)
    excluded = df.loc[ambiguous].copy()
    return df.loc[~ambiguous].copy().reset_index(drop=True), excluded.reset_index(drop=True)


def financial_view(df, ticker):
    company = df.loc[df['ticker'].eq(ticker)].copy()
    if company.empty:
        return pd.DataFrame(), pd.DataFrame()
    company['montant_mfcfa'] = company['amount_xof'] / 1_000_000
    pivot = company.pivot(index='fiscal_year', columns='standardized_account', values='montant_mfcfa').sort_index()
    ratios = pd.DataFrame(index=pivot.index)
    for key in ('REVENUE','PNB','NET_INCOME','OPERATING_INCOME','EQUITY'):
        if key in pivot:
            ratios[f'{key} croissance %'] = pivot[key].pct_change(fill_method=None).mul(100)
    base = 'PNB' if ticker == 'BOAB' else 'REVENUE'
    if base in pivot and 'NET_INCOME' in pivot:
        ratios['Marge nette %'] = pivot['NET_INCOME'].div(pivot[base].where(pivot[base].ne(0))).mul(100)
    if base in pivot and 'OPERATING_INCOME' in pivot:
        ratios['Marge exploitation %'] = pivot['OPERATING_INCOME'].div(pivot[base].where(pivot[base].ne(0))).mul(100)
    return pivot, ratios


# Traduction des libellés sans modification des identifiants PostgreSQL.
LIBELLES_FINANCIERS = {
    'EQUITY': 'Capitaux propres',
    'NET_INCOME': 'Résultat net',
    'OPERATING_INCOME': 'Résultat d’exploitation',
    'PNB': 'Produit net bancaire',
    'REVENUE': 'Chiffre d’affaires',
}

def libelle_financier(code):
    return LIBELLES_FINANCIERS.get(str(code), str(code))

def tableau_francais(pivot, ratios):
    historique = pivot.rename(columns=LIBELLES_FINANCIERS)
    traductions = {f'{code} croissance %': f'Croissance {libelle} (%)'
                   for code, libelle in LIBELLES_FINANCIERS.items()}
    traductions.update({'Marge nette %': 'Marge nette (%)',
                         'Marge exploitation %': 'Marge d’exploitation (%)'})
    return historique, ratios.rename(columns=traductions)

def graphique_financier(st, pivot):
    """Barres groupées : ne pas additionner des grandeurs comptables distinctes."""
    import altair as alt
    historique = pivot.rename(columns=LIBELLES_FINANCIERS)
    data = historique.reset_index().melt(id_vars=['fiscal_year'], var_name='Indicateur', value_name='Millions FCFA')
    data['Exercice'] = data['fiscal_year'].astype(str)
    chart = (alt.Chart(data.dropna(subset=['Millions FCFA']))
             .mark_bar()
             .encode(x=alt.X('Exercice:N', title='Exercice'),
                     xOffset=alt.XOffset('Indicateur:N'),
                     y=alt.Y('Millions FCFA:Q', title='Millions de FCFA'),
                     color=alt.Color('Indicateur:N', title='Indicateur'),
                     tooltip=['Exercice:N', 'Indicateur:N', alt.Tooltip('Millions FCFA:Q', format=',.2f')]))
    st.altair_chart(chart, use_container_width=True)

def render_page(st):
    st.header('V2.8.1 — Données financières validées (Data Engine)')
    st.caption('Lecture PostgreSQL sans écriture · Les valeurs ne sont pas des cotations en temps réel.')
    db_url = st.secrets.get('DATABASE_URL', '')
    if not db_url:
        st.error('Configurer DATABASE_URL dans les secrets de cette application Streamlit (pas dans GitHub).')
        st.info('Il est aussi possible de tester la passerelle avec un export CSV validé.')
    source = st.radio('Source des données', ['PostgreSQL (direct)','CSV validé (test)'], horizontal=True)
    if source.startswith('PostgreSQL'):
        if not db_url:
            return
        if st.button('Actualiser les données validées', type='primary', key='v281_refresh'):
            try:
                valid, excluded = fetch_validated(db_url)
                st.session_state['v281_data'] = (valid, excluded)
            except Exception as exc:
                st.error(f'Lecture PostgreSQL impossible : {exc}')
                return
        result = st.session_state.get('v281_data')
        if result is None:
            st.info('Cliquez sur « Actualiser les données validées ».')
            return
        valid, excluded = result
    else:
        upload = st.file_uploader('Importer brvm_radar_validated_v280.csv', type='csv', key='v281_csv')
        if upload is None:
            return
        try:
            valid, excluded = validate_export(pd.read_csv(upload, encoding='utf-8-sig'))
        except Exception as exc:
            st.error(f'CSV non exploitable : {exc}')
            return
    a,b,c = st.columns(3)
    a.metric('Sociétés', valid['ticker'].nunique() if not valid.empty else 0)
    b.metric('Observations éligibles', len(valid))
    c.metric('Lignes ambiguës exclues', len(excluded))
    if not excluded.empty:
        st.warning('Des doublons par société, exercice et indicateur ont été exclus des calculs.')
        st.dataframe(excluded, hide_index=True, use_container_width=True)
    if valid.empty:
        st.warning('Aucune observation validée exploitable.')
        return
    st.download_button('Exporter les données validées CSV', valid.to_csv(index=False).encode('utf-8-sig'),
                       'brvm_radar_validated_v281.csv', 'text/csv', key='v281_export')
    ticker = st.selectbox('Société', sorted(valid['ticker'].unique()), key='v281_ticker')
    subset = valid.loc[valid['ticker'].eq(ticker)]
    st.caption('Les montants sont en FCFA ; les graphiques sont en millions FCFA. La précision est indiquée ligne par ligne.')
    st.dataframe(subset, hide_index=True, use_container_width=True,
                 column_config={'report_url': st.column_config.LinkColumn('Rapport source')})
    pivot, ratios = financial_view(valid, ticker)
    if not pivot.empty:
        st.subheader('Historique financier (millions FCFA)')
        graphique_financier(st, pivot)
        historique_fr, ratios_fr = tableau_francais(pivot, ratios)
        st.dataframe(historique_fr.round(3), use_container_width=True)
    if not ratios.empty:
        st.subheader('Croissance et rentabilité — ratios indicatifs')
        st.dataframe(tableau_francais(pivot, ratios)[1].round(2), use_container_width=True)
    st.warning('BPA, PER, PBR et valeur intrinsèque non calculés ici : actions en circulation, cours daté et autres données doivent être vérifiés. Les valeurs arrondies ne sont pas exactes au franc près.')
