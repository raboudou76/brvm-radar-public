"""Unified BRVM dashboard. Source-backed data only, no demo figures."""
import unicodedata
import pandas as pd
import streamlit as st
from brvm_sync import for_issuer, URL as DIV_URL
from dashboard_engine import (cached_dividend_sync, cached_financial_reports,
                              cached_financial_history, render_history,
                              render_dividend_history)


def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or '').casefold())
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c) and c.isalnum() or c.isspace()).split())


def issuer_options(market):
    """Use live market list, not hard-coded/demo issuers."""
    if market is None or market.empty:
        return []
    if not {'Symbole', 'Société'}.issubset(market.columns):
        return []
    options=[]
    for _, row in market[['Symbole','Société']].dropna().drop_duplicates().iterrows():
        symbol, name = str(row['Symbole']).strip(), str(row['Société']).strip()
        if symbol and name:
            options.append((symbol,name))
    return sorted(options, key=lambda x:x[0])


def match_dividend_issuer(records, symbol, name):
    """Exact normalized symbol/name matching only; avoid wrong issuer assignments."""
    if records is None or records.empty or 'Société' not in records:
        return None
    choices = [str(x) for x in records['Société'].dropna().unique()]
    aliases = [symbol, name]
    if normalize(symbol) in ("smb", "smbc") or "multinationale de bitumes" in normalize(name):
        aliases.extend(["SMB", "SMB CI"])
    for key in aliases:
        matched = [x for x in choices if normalize(x) == normalize(key)]
        if len(matched)==1:
            return matched[0]
    # BRVM may append a country suffix to a symbol; only accept unique explicit prefix.
    sym=normalize(symbol)
    matched=[x for x in choices if normalize(x).split(' ')[0] == sym]
    return matched[0] if len(matched)==1 else None


def _find_reports(symbol, name, pages):
    # Search by exchange symbol, then by official name if needed.
    found=cached_financial_reports(symbol, pages)
    if normalize(name)!=normalize(symbol):
        more=cached_financial_reports(name, pages)
        found=list({r['URL']:r for r in (found+more)}.values())
    return found


def unified_dashboard_page(market):
    st.subheader('Dashboard financier — synchronisation unifiée BRVM')
    st.caption('Une société, un bouton : données financières et dividendes. Aucun jeu SMB intégré ni donnée de démonstration SGBCI.')
    options=issuer_options(market)
    if not options:
        st.warning('La liste des sociétés cotées est indisponible. Réessayez lorsque les cours BRVM sont accessibles.')
        return
    symbols=[x[0] for x in options]
    selected=st.selectbox('Choisir une société cotée', options,
                          format_func=lambda x:f'{x[0]} — {x[1]}',
                          key='unified_issuer')
    symbol,name=selected
    with st.expander('Paramètres de synchronisation', expanded=False):
        financial_pages=st.slider('Pages de publications financières',1,8,5,key='unified_fin_pages')
        dividend_pages=st.slider('Pages des annonces de dividendes',1,30,12,key='unified_div_pages')
        max_reports=st.slider('Rapports annuels PDF à examiner',1,8,5,key='unified_reports')
    if st.button('Synchroniser les données BRVM',type='primary',key='unified_sync'):
        # Do not clear all caches on each rerun: refresh only when user clicks.
        cached_financial_reports.clear()
        cached_financial_history.clear()
        cached_dividend_sync.clear()
        reports=[]; history=pd.DataFrame(); detail=pd.DataFrame(); errors=[]
        financial_timestamp=None; dividend_timestamp=None
        dividend_records=pd.DataFrame(); div_error=None; fin_error=None
        with st.spinner(f'Synchronisation BRVM pour {symbol}...'):
            try:
                reports=_find_reports(symbol,name,financial_pages)
                selected_reports=reports[:max_reports]
                if selected_reports:
                    history,detail,errors,financial_timestamp=cached_financial_history(
                        tuple((r['URL'],r['Titre']) for r in selected_reports))
            except Exception as exc:
                fin_error=f'{type(exc).__name__} : {exc}'
            try:
                dividend_records,dividend_timestamp=cached_dividend_sync(dividend_pages)
            except Exception as exc:
                div_error=f'{type(exc).__name__} : {exc}'
        st.session_state['unified_result']={
            'symbol':symbol,'name':name,'history':history,'detail':detail,'errors':errors,
            'reports':reports,'financial_timestamp':financial_timestamp,
            'dividend_records':dividend_records,'dividend_timestamp':dividend_timestamp,
            'div_error':div_error,'fin_error':fin_error}
    result=st.session_state.get('unified_result')
    if not result or (result['symbol'],result['name']) != selected:
        st.info('Sélectionnez une société puis cliquez sur « Synchroniser les données BRVM ».')
        return
    st.caption(f"Dernière extraction financière : {result['financial_timestamp'] or 'indisponible'} · Dernière consultation dividendes : {result['dividend_timestamp'] or 'indisponible'}")
    st.markdown('### Chiffre d’affaires / PNB, résultat net et croissance')
    if result['fin_error']:
        st.warning('Recherche financière indisponible : '+result['fin_error'])
    history=result['history']
    if not history.empty and (history["Chiffre d'affaires"].notna().any() or history['Résultat net'].notna().any()):
        render_history(history, source='Rapports annuels BRVM (montants candidats à vérifier dans les sources)')
    else:
        st.info('Aucune donnée financière annuelle vérifiable extraite pour ce titre. Les histogrammes ne sont pas simulés.')
    if not result['detail'].empty:
        with st.expander('Traçabilité des montants financiers'):
            st.dataframe(result['detail'],hide_index=True,use_container_width=True)
    if not result['reports'] and not result['fin_error']:
        st.warning('Aucun rapport PDF annuel trouvé sur les pages BRVM explorées. Essayez davantage de pages ; les anciennes publications peuvent ne pas être indexées.')
    if result['reports']:
        with st.expander('Publications financières identifiées'):
            st.dataframe(pd.DataFrame(result['reports'])[['Titre','URL']],hide_index=True,use_container_width=True)
    for err in result['errors'][:8]:
        st.caption('Rapport non exploité : '+err)
    st.markdown('### Dividendes nets — cinq derniers exercices disponibles')
    if result['div_error']:
        st.warning('Annonces de dividendes indisponibles : '+result['div_error'])
    else:
        matched=match_dividend_issuer(result['dividend_records'],symbol,name)
        if matched:
            selected_div=for_issuer(result['dividend_records'],matched)
            if normalize(symbol) in ('smb','smbc') or normalize(matched) in ('smb','smb ci'):
                st.info('SMB 2025 : dividende net personne physique retenu à 704 FCFA/action ; montant BRVM publié conservé séparément.')
            else:
                st.caption('Montants nets BRVM tels que publiés ; le net fiscal individuel peut différer. Aucun taux fiscal universel supposé.')
            render_dividend_history(selected_div)
            st.download_button('Exporter les dividendes CSV',selected_div.to_csv(index=False,sep=';').encode('utf-8-sig'),
                               f'brvm_dividendes_{symbol}.csv','text/csv',key='unified_export_div')
        else:
            st.info('Aucune correspondance certaine entre ce titre et les annonces BRVM consultées. Aucun dividende attribué par approximation.')
    st.caption(f'Sources : publications financières BRVM et {DIV_URL}. Les années manquantes restent vides. La récupération de tous les rapports historiques et du PNB bancaire reste dépendante des formats publiés.')
