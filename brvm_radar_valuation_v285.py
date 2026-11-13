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
    st.markdown('### V2.8.5 — Ratios annuels et scénarios de valorisation')
    st.caption('Données annuelles VALIDATED uniquement. Le BPA et le PER annuels ne remplacent pas le BPA/PER TTM. Aucune donnée de marché n’est inventée.')
    if st.button('Charger les références annuelles V2.8.5', key='v285_load'):
        st.session_state['v285_reference'] = get_valuation_prefill(st, ticker)
        st.session_state['v285_ticker'] = ticker
    ref = st.session_state.get('v285_reference') if st.session_state.get('v285_ticker') == ticker else None
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
    shares = st.number_input('Nombre d’actions en circulation — saisir et vérifier', min_value=0, value=0, step=100, key=f'v285_shares_{ticker}')
    shares_source = st.text_input('Source du nombre d’actions (obligatoire)', key=f'v285_shares_source_{ticker}')
    price = st.number_input('Cours de référence (FCFA/action) — facultatif', min_value=0.0, value=0.0, step=50.0, key=f'v285_price_{ticker}')
    price_date = st.date_input('Date du cours de référence', value=None, key=f'v285_price_date_{ticker}') if price > 0 else None
    price_source = st.text_input('Source du cours', key=f'v285_price_source_{ticker}') if price > 0 else ''
    confirmed = st.checkbox('Je confirme le nombre d’actions, sa source et, le cas échéant, le cours daté et sa source.', key=f'v285_confirm_{ticker}')
    if not (shares > 0 and shares_source.strip() and confirmed):
        st.info('Renseigner et confirmer le nombre d’actions ainsi que sa source pour activer les calculs.')
        return
    if price > 0 and (price_date is None or not price_source.strip()):
        st.warning('Cours sans date ou sans source : PER et PBR désactivés.')
        price = 0
    try:
        metrics = calculate_annual_metrics(ref['annual'], ref.get('equity'), ref.get('prior_equity'), shares, price or None)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.dataframe(pd.DataFrame([{'Indicateur': k, 'Valeur': round(v, 4)} for k,v in metrics.items()]), hide_index=True, use_container_width=True)
    st.caption('PER annuel : cours / BPA annuel. PBR : cours / valeur comptable par action. ROE : résultat net / capitaux propres moyens. Comparer uniquement avec des sociétés du même secteur.')
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
                            'Cours': price if price > 0 else None, 'Date cours': str(price_date) if price_date else None,
                            'Source cours': price_source, 'Précision résultat net': ref['precision'].get('Résultat net'), **metrics}])
    st.download_button('Exporter les ratios annuels (CSV)', export.to_csv(index=False, sep=';').encode('utf-8-sig'), f'ratios_annuels_{ticker}_v285.csv', 'text/csv', key=f'v285_export_{ticker}')
