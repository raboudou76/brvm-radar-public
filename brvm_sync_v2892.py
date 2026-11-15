"""V2.8.9.1 — non-destructive BRVM quote bridge and dividend candidate audit."""
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from brvm_sync_v289 import discover_dividend_documents, DIVIDEND_PAGE


def _positive(x):
    try:
        v=float(x)
        return v if pd.notna(v) and v>0 else None
    except (ValueError, TypeError):
        return None


def sync_quotes(load_market):
    """Fetch official table, update positive per-issuer session snapshots only.

    Dates in free-text BRVM page are kept as-is, not falsely interpreted as
    a timestamp. An already documented snapshot is not overwritten if its
    source date differs: user must confirm the change in the audit panel.
    """
    df, source_date=load_market()
    required={'Symbole','Clôture'}
    if not required.issubset(df.columns):
        raise ValueError('Table BRVM incomplète')
    rows=[]
    for _, r in df.iterrows():
        symbol=str(r['Symbole']).strip().upper()
        price=_positive(r['Clôture'])
        if not symbol:
            continue
        key=f'v2891_quote_{symbol}'
        old=st.session_state.get(key)
        status='Cours absent'
        if price is not None:
            new={'price':price,'source_date':str(source_date),
                 'url':'https://www.brvm.org/fr/cours-actions/0',
                 'synced_at':datetime.now(timezone.utc).isoformat()}
            if not old:
                st.session_state[key]=new
                status='Référence créée'
            elif old['source_date']==new['source_date']:
                st.session_state[key]=new
                status='Référence actualisée'
            else:
                # Without a parsed trading date, never infer newer from HTML text.
                status='Date différente — contrôle requis'
                st.session_state[f'v2891_pending_{symbol}']=new
        rows.append({'Symbole':symbol,'Société':str(r.get('Société','')),
                     'Cours lu':price,'Date source':str(source_date),'Statut':status,
                     'Cours actif':st.session_state.get(key,{}).get('price'),
                     'Source':'https://www.brvm.org/fr/cours-actions/0'})
    return pd.DataFrame(rows)


def quote_for(symbol):
    return st.session_state.get(f'v2891_quote_{str(symbol).upper()}')


def render_sync_panel(load_market):
    st.subheader('V2.8.9.2 — Synchronisation contrôlée')
    st.caption('Les cours officiels positifs sont mis en cache par émetteur. Les changements de date non comparables nécessitent une validation. Aucun capital, dividende ou état financier n’est modifié.')
    st.markdown('#### 1. Cours BRVM — audit et transfert contrôlé')
    try:
        quotes=sync_quotes(load_market)
        c1,c2,c3=st.columns(3)
        c1.metric('Émetteurs',len(quotes))
        c2.metric('Cours positifs',int(quotes['Cours lu'].notna().sum()))
        c3.metric('Cours absents',int(quotes['Cours lu'].isna().sum()))
        st.dataframe(quotes,hide_index=True,use_container_width=True)
        st.download_button('Exporter les cours audités (CSV)',quotes.to_csv(index=False,sep=';').encode('utf-8-sig'),
                           'brvm_v2891_cours_audites.csv','text/csv')
        pending=[s for s in quotes['Symbole'] if f'v2891_pending_{s}' in st.session_state]
        if pending:
            st.warning('Des dates de cotation différentes ont été rencontrées. Contrôler la source avant de remplacer les cours actifs.')
            selected=st.selectbox('Référence à examiner',pending)
            st.write('Active :',quote_for(selected))
            st.write('Candidate :',st.session_state[f'v2891_pending_{selected}'])
            if st.button('Confirmer la nouvelle référence pour cette société'):
                st.session_state[f'v2891_quote_{selected}']=st.session_state.pop(f'v2891_pending_{selected}')
                st.rerun()
    except Exception as exc:
        st.warning(f'Collecte indisponible : {exc}. Les références déjà mémorisées ne sont pas effacées.')
    st.markdown('#### 2. Avis de dividendes — inventaire documentaire')
    try:
        docs=discover_dividend_documents()
        df=pd.DataFrame(docs)
        if not df.empty:
            df['Type']=df['URL officielle'].str.contains(r'\.pdf(?:[?#]|$)',case=False,regex=True).map({True:'PDF candidat',False:'Navigation / page'})
            df['Statut extraction']='Non lu — brut/net non qualifié'
            st.metric('Avis PDF candidats',int((df['Type']=='PDF candidat').sum()))
            st.dataframe(df,hide_index=True,use_container_width=True,
                         column_config={'URL officielle':st.column_config.LinkColumn('URL officielle')})
            st.download_button('Exporter le catalogue des avis (CSV)',df.to_csv(index=False,sep=';').encode('utf-8-sig'),
                               'brvm_v2891_dividendes_candidats.csv','text/csv')
        else:
            st.info('Aucun document détecté.')
    except Exception as exc:
        st.warning(f'Catalogue indisponible : {exc}')
    st.link_button('Consulter les avis officiels BRVM',DIVIDEND_PAGE)
    from brvm_dividends_v2892 import render_dividend_pdf_audit
    render_dividend_pdf_audit()
    st.markdown('#### 3. Capital social — références protégées')
    st.info('La synchronisation des opérations sur capital reste en attente de justificatifs vérifiés. Les nombres d’actions BOAB et SMB restent inchangés.')
