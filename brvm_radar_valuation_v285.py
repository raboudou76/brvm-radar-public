"""V2.8.5 — ratios annuels et scénarios conditionnels à partir de données VALIDATED.
Aucune écriture en base. Les valeurs arrondies restent identifiées.
"""
import pandas as pd
from brvm_radar_sync_v284 import get_valuation_prefill


def calculate_annual_metrics(net_income_m, equity_m, prior_equity_m, shares, price=None):
    """Calculs annuels descriptifs, distincts des ratios TTM."""
    if shares <= 0 or net_income_m is None:
        raise ValueError('Nombre d’actions positif et résultat net annuel requis.')
    net_xof = float(net_income_m) * 1_000_000
    eps = net_xof / int(shares)
    out = {'BPA annuel (FCFA/action)': eps}
    if equity_m is not None and float(equity_m) > 0:
        book = float(equity_m) * 1_000_000 / int(shares)
        out['Valeur comptable/action (FCFA)'] = book
        if price is not None and float(price) > 0:
            out['PBR annuel (x)'] = float(price) / book
    if price is not None and float(price) > 0 and eps > 0:
        out['PER annuel (x)'] = float(price) / eps
    if equity_m is not None and prior_equity_m is not None:
        avg = (float(equity_m) + float(prior_equity_m)) / 2
        if avg > 0:
            out['ROE annuel (%)'] = 100 * float(net_income_m) / avg
    return out


def earnings_capitalization(eps, required_return, growth):
    """Scénario simplifié de capitalisation, non DCF et non estimation certifiée."""
    if eps <= 0 or not 0 <= growth < required_return <= 1:
        raise ValueError('BPA positif et taux requis strictement supérieur à la croissance.')
    return eps * (1 + growth) / (required_return - growth)


def render_annual_valuation(st, ticker):
    st.markdown('### V2.8.6.5 — Sources officielles et ratios annuels')
    st.caption('Données annuelles VALIDATED uniquement. Le BPA et le PER annuels ne remplacent pas le BPA/PER TTM. Aucune donnée de marché n’est inventée.')
    if st.button('Charger les références annuelles V2.8.5', key='v285_load'):
        st.session_state['v285_reference'] = get_valuation_prefill(st, ticker)
        st.session_state['v285_ticker'] = ticker
    ref = st.session_state.get('v285_reference') if st.session_state.get('v285_ticker') == ticker else None
    from brvm_market_v286 import get_official_market_price, extract_shares_from_issuer_pdf, _fetch, OfficialSourceError
    st.markdown('#### V2.8.6 — Sources officielles automatiques')
    st.caption('Le cours est extrait du dernier BOC PDF accessible. Le nombre d’actions doit être identifié dans un rapport officiel de l’émetteur ; le volume échangé n’est jamais utilisé.')
    if st.button('Actualiser le dernier BOC officiel', key=f'v286_boc_{ticker}'):
        try:
            st.session_state[f'v286_price_{ticker}'] = get_official_market_price(ticker)
        except Exception as exc:
            st.session_state.pop(f'v286_price_{ticker}',None)
            st.warning(f'Extraction automatique du cours indisponible : {exc}')
    market=st.session_state.get(f'v286_price_{ticker}')
    price=None
    if market:
        st.success(f"Clôture {ticker} : {market['price_xof']:,} FCFA — séance du {market['date']} — page PDF {market['pdf_page']}")
        st.link_button('Consulter le BOC officiel',market['url'])
        price=market['price_xof']
    default_reports={'SMBC':'https://www.brvm.org/sites/default/files/20260512_-_etats_financiers_et_projet_daffectation_du_resultat_-_exercice_2025_-_smb_ci.pdf', 'BOAB':'https://www.brvm.org/sites/default/files/20260415_-_etats_financiers_-_exercice_2025_-_boa_bn.pdf'}
    issuer_url=st.text_input('Rapport officiel pour recherche automatique du nombre d’actions',value=default_reports.get(ticker,''),key=f'v286_issuer_{ticker}')
    if st.button('Extraire le nombre d’actions du rapport officiel',key=f'v286_shares_btn_{ticker}'):
        try:
            if not issuer_url.lower().endswith('.pdf'):raise OfficialSourceError('URL PDF officielle requise.')
            result=extract_shares_from_issuer_pdf(_fetch(issuer_url))
            result['url']=issuer_url
            st.session_state[f'v286_shares_{ticker}']=result
        except Exception as exc:
            st.session_state.pop(f'v286_shares_{ticker}',None)
            st.warning(f'Nombre d’actions non confirmé : {exc}')
    st.markdown('#### V2.8.6.5 — Actions publiées sur la fiche BRVM')
    default_profiles = {'SMBC': 'https://www.brvm.org/fr/emetteurs/societes-cotees/societe-multinationale-de-bitume-de-cote-divoire-smb'}
    profile_url = st.text_input('Fiche officielle BRVM de la société', value=default_profiles.get(ticker, ''), key=f'v2865_profile_{ticker}')
    if st.button('Extraire les actions de la fiche BRVM', key=f'v2865_extract_{ticker}'):
        try:
            from brvm_issuer_v2865 import get_official_shares
            result = get_official_shares(ticker, profile_url)
            st.session_state[f'v286_shares_{ticker}'] = result
            st.session_state[f'v286_confirm_{ticker}'] = False
        except Exception as exc:
            st.session_state.pop(f'v286_shares_{ticker}', None)
            st.warning(f'Extraction de la fiche BRVM impossible : {exc}')
    if not ref:
        st.info('Clique sur « Charger les références annuelles V2.8.5 » pour consulter les chiffres validés de cette société.')
        return
    st.write(f"**{ticker} — exercice {ref['year']}**")
    st.dataframe(pd.DataFrame([
        {'Référence': 'Résultat net annuel', 'Montant (millions FCFA)': ref.get('annual'), 'Précision': ref['precision'].get('Résultat net')},
        {'Référence': 'Capitaux propres', 'Montant (millions FCFA)': ref.get('equity'), 'Précision': ref['precision'].get('Capitaux propres')},
        {'Référence': 'Capitaux propres N-1', 'Montant (millions FCFA)': ref.get('prior_equity'), 'Précision': ref['precision'].get('Capitaux propres N-1')},
    ]), hide_index=True, use_container_width=True)
    if ref.get('annual') is None:
        st.warning('Résultat net annuel validé absent : calcul impossible.')
        return
    if any(v == 'ROUNDED_MILLION' for v in ref['precision'].values()):
        st.warning('Au moins un montant est arrondi au million FCFA. Les ratios calculés sont approximatifs.')
    if any(v == 'EXACT_OR_UNSPECIFIED' for v in ref['precision'].values()):
        st.info('Précision exacte non attestée pour certains montants : vérifier la documentation.')

    shares_ref=st.session_state.get(f'v286_shares_{ticker}')
    if shares_ref:
        shares=shares_ref['shares']
        shares_source=f"{shares_ref['url']} — {('page ' + str(shares_ref['pdf_page'])) if shares_ref.get('pdf_page') else ('référence ' + shares_ref.get('reference_date','non précisée'))}"
        st.success(f"Nombre d’actions identifié : {shares:,} — {('page PDF ' + str(shares_ref['pdf_page'])) if shares_ref.get('pdf_page') else ('fiche BRVM au ' + shares_ref.get('reference_date','date inconnue'))}")
        if shares_ref.get('validation_status') == 'OFFICIAL_HISTORICAL':
            st.warning('Donnée officielle historique : vérifier les opérations sur capital depuis cette date avant de confirmer son actualité.')
        st.caption(f"Justificatif extrait : {shares_ref['evidence']}")
    else:
        st.info('Nombre d’actions indisponible : BPA, PER et PBR suspendus. Fournir une URL officielle de rapport pour extraction automatique, sans saisie de montant.')
        return
    if not market:
        st.info('Cours officiel indisponible : calcul du BPA et du ROE possible, PER et PBR suspendus.')
    confirmed=st.checkbox('J’ai vérifié les opérations sur capital depuis la date de référence et confirmé le nombre d’actions applicable.',key=f'v286_confirm_{ticker}')
    if not confirmed:
        st.info('Confirmer le justificatif du nombre d’actions pour activer les calculs.')
        return
    if market and shares_ref:
        if st.button('Reporter le cours et les actions dans la valorisation', key=f'v286_apply_{ticker}'):
            st.session_state['v286_apply_pending'] = ticker
            st.rerun()
    price_date=market['date'] if market else None
    price_source=market['url'] if market else ''
    try:
        metrics = calculate_annual_metrics(ref['annual'], ref.get('equity'), ref.get('prior_equity'), shares, price or None)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.dataframe(pd.DataFrame([{'Indicateur': k, 'Valeur': round(v, 4)} for k,v in metrics.items()]), hide_index=True, use_container_width=True)
    st.caption('PER annuel : cours / BPA annuel. PBR : cours / valeur comptable par action. ROE : résultat net / capitaux propres moyens. Comparer uniquement avec des sociétés du même secteur.')
    from brvm_scoring_v286 import preliminary_score
    prior_net=ref.get('previous')
    growth=100*(ref['annual']/prior_net-1) if prior_net and prior_net>0 else None
    equity_growth=100*(ref['equity']/ref['prior_equity']-1) if ref.get('equity') and ref.get('prior_equity') else None
    preliminary=preliminary_score(roe=metrics.get('ROE annuel (%)'),net_growth=growth,per=metrics.get('PER annuel (x)'),pbr=metrics.get('PBR annuel (x)'),equity_growth=equity_growth)
    st.markdown('#### Scoring financier exploratoire V2.8.6')
    st.dataframe(pd.DataFrame(preliminary['details']),hide_index=True,use_container_width=True)
    if preliminary['score_100'] is None:
        st.info(f"Score incomplet : {preliminary['points_observed']} points observés sur {preliminary['maximum_observed']} possibles. Aucune note /100 attribuée.")
    else:
        st.metric('Score exploratoire /100',preliminary['score_100'])
    st.caption('Barème expérimental non calibré par secteur : ne pas utiliser comme recommandation ou BRVM Opportunity Score définitif.')
    st.markdown('**Scénario facultatif de capitalisation des bénéfices**')
    st.caption('Modèle simplifié de bénéfice perpétuel croissant, non assimilable à une valorisation DCF complète. Les hypothèses ne sont pas fournies par PostgreSQL.')
    with st.expander('Saisir les hypothèses et calculer une valeur indicative'):
        required = st.number_input('Rendement annuel exigé (%)', min_value=0.0, max_value=100.0, value=0.0, step=0.5, key=f'v285_required_{ticker}')
        growth = st.number_input('Croissance perpétuelle supposée (%)', min_value=0.0, max_value=100.0, value=0.0, step=0.5, key=f'v285_growth_{ticker}')
        assumption_source = st.text_area('Justification des hypothèses', key=f'v285_assumptions_{ticker}')
        if st.button('Calculer le scénario indicatif', key=f'v285_calculate_{ticker}'):
            if not assumption_source.strip():
                st.error('Documenter la justification des hypothèses avant le calcul.')
            else:
                try:
                    result = earnings_capitalization(metrics['BPA annuel (FCFA/action)'], required/100, growth/100)
                    st.metric('Valeur indicative par action (FCFA)', f'{result:,.2f}')
                    st.warning('Scénario très sensible aux hypothèses. Ce résultat ne constitue ni une valeur intrinsèque certifiée ni une recommandation d’investissement.')
                except ValueError as exc:
                    st.error(str(exc))
    export = pd.DataFrame([{'Société': ticker, 'Exercice': ref['year'], 'Actions': shares, 'Source actions': shares_source,
                            'Cours': price if price is not None and price > 0 else None, 'Date cours': str(price_date) if price_date else None,
                            'Source cours': price_source, 'Précision résultat net': ref['precision'].get('Résultat net'), **metrics}])
    st.download_button('Exporter les ratios annuels (CSV)', export.to_csv(index=False, sep=';').encode('utf-8-sig'), f'ratios_annuels_{ticker}_v285.csv', 'text/csv', key=f'v285_export_{ticker}')
