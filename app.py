import io, re, os
from datetime import datetime, timezone
from urllib.parse import urljoin
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from finance_engine import extract_pdf, tables_excel, ratios, dcf_fcfe, dividend_discount, residual_income
from auto_financials import discover, download_pdf, candidates_from_tables
from structured_financials import extract_structured
from analysis_engine import fundamental_analysis, valuation_scenarios
from valuation_engine import reconstruct_fcfe, run_scenarios, SCENARIOS
from dashboard_engine import dashboard_page, history_from_fundamentals, render_history

BASE='https://www.brvm.org'
MARKET=BASE+'/fr/cours-actions/0'
FIN=BASE+'/fr/type-document/etats-financiers'
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; BRVMRadarResearch/1.0)'}
st.set_page_config(page_title='BRVM RADAR | Marché et analyse BRVM',page_icon='📈',layout='wide')
st.markdown("""<style>
:root {--navy:#102544;--teal:#087f8c;}
.block-container{padding-top:1.7rem;max-width:1380px}
h1,h2,h3{color:#102544!important;letter-spacing:-.025em}
section[data-testid="stSidebar"]{background:#102544}
section[data-testid="stSidebar"] *{color:#f2f6fc!important}
div[data-testid="stMetric"]{background:#f2f7fa;border:1px solid #dfe8ef;padding:16px;border-radius:13px}
div[data-testid="stMetricValue"]{color:#102544}
div.stButton>button[kind="primary"],div.stDownloadButton>button[kind="primary"]{background:#087f8c}
[data-testid="stDataFrame"]{border:1px solid #e4ebf1;border-radius:10px}
</style>""",unsafe_allow_html=True)

def number(x):
    s=str(x).strip().replace('\u202f','').replace('\xa0','').replace(' ','').replace('%','').replace(',','.')
    try:return float(s)
    except:return None

@st.cache_data(ttl=900,show_spinner=False)
def load_market():
    r=requests.get(MARKET,headers=HEADERS,timeout=25);r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    text=soup.get_text(' ',strip=True)
    m=re.search(r'Dernière mise à jour\s*:\s*(.{0,90}?)\s*Symbole',text,re.I)
    updated=m.group(1) if m else 'Date non déterminée — vérifier la source'
    candidates=[]
    for table in soup.find_all('table'):
        headers=[x.get_text(' ',strip=True).lower() for x in table.find_all('th')]
        if any('symbole' in x for x in headers) and any('volume' in x for x in headers):
            for tr in table.find_all('tr'):
                cells=[x.get_text(' ',strip=True) for x in tr.find_all(['td','th'])]
                if len(cells)>=7 and cells[0].upper()!='SYMBOLE':
                    candidates.append({'Symbole':cells[0],'Société':cells[1],'Volume':number(cells[2]),'Cours veille':number(cells[3]),'Ouverture':number(cells[4]),'Clôture':number(cells[5]),'Variation %':number(cells[6])})
    if not candidates:
        # Fallback: pandas HTML tables when BRVM markup differs
        for df in pd.read_html(io.StringIO(r.text)):
            cols=[str(x).lower() for x in df.columns]
            if any('symbole' in x for x in cols) and any('volume' in x for x in cols):
                if len(df.columns)>=7:
                    for v in df.itertuples(index=False,name=None):
                        candidates.append({'Symbole':str(v[0]),'Société':str(v[1]),'Volume':number(v[2]),'Cours veille':number(v[3]),'Ouverture':number(v[4]),'Clôture':number(v[5]),'Variation %':number(v[6])})
                break
    df=pd.DataFrame(candidates)
    if df.empty:raise ValueError('Structure du tableau BRVM non reconnue. Aucune donnée inventée.')
    df=df.drop_duplicates('Symbole').reset_index(drop=True)
    return df,updated

@st.cache_data(ttl=1800, show_spinner=False)
def publications():
    """Inventaire indicatif des liens publiés sur la rubrique officielle.

    Les sites tiers, les PDF indirects et les pages chargées uniquement en JS
    ne sont pas couverts par cette extraction HTML.
    """
    r = requests.get(FIN, headers=HEADERS, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    result = []
    seen = set()
    for a in soup.select('a[href]'):
        href = a.get('href', '').strip()
        if not href or href.startswith(('#', 'javascript:', 'mailto:')):
            continue
        link = urljoin(FIN, href)
        if not link.startswith(('https://www.brvm.org/', 'http://www.brvm.org/')):
            continue
        label = ' '.join(a.get_text(' ', strip=True).split())
        context = ' '.join(a.parent.get_text(' ', strip=True).split())[:350] if a.parent else label
        blob = (label + ' ' + context + ' ' + link).lower()
        is_pdf = bool(re.search(r'\.pdf(?:[?#]|$)', link, re.I))
        is_financial = any(word in blob for word in (
            'financier', 'financière', 'bilan', 'rapport', 'résultat',
            'trimestriel', 'semestriel', 'annuel', 'activité', 'activite',
            'publication', 'document', 'attestation'
        ))
        if not (is_pdf or is_financial):
            continue
        if link in seen or link.rstrip('/') == FIN.rstrip('/'):
            continue
        seen.add(link)
        result.append({
            'Publication': label or context[:120] or 'Document sans titre',
            'Contexte': context,
            'Type': 'PDF direct' if is_pdf else 'Page / lien',
            'Lien': link,
        })
    return pd.DataFrame(result, columns=['Publication', 'Contexte', 'Type', 'Lien'])

def score_session(df):
    # This is a partial signal, NOT the historic 100-point score.
    out=df.copy()
    out['Valeur échangée estimée']=out['Clôture']*out['Volume']
    out['Activité /50']=out['Valeur échangée estimée'].rank(pct=True).fillna(0)*50
    out['Séance /50']=out['Variation %'].clip(lower=-7.5,upper=7.5).add(7.5).div(15).mul(50)
    out['Signal séance /100']=(out['Activité /50']+out['Séance /50']).round(1)
    return out.sort_values('Signal séance /100',ascending=False)

st.sidebar.title('◈ BRVM RADAR')
st.sidebar.caption('Investment Intelligence · V1.6.1')
menu=st.sidebar.radio('Navigation',['Dashboard financier','Vue du marché','Radar court terme','Fiche action','Analyse fondamentale','Actualisation T1 / S1 / T3','Valeur intrinsèque','Publications financières','Analyser un PDF','Portefeuille','Méthodologie','Informations légales'])
st.sidebar.link_button('Site officiel BRVM',BASE)
st.sidebar.caption('Bêta publique · Aucun compte ni ordre de bourse')
st.title('◈ BRVM RADAR')
st.caption('Bêta publique · Plateforme indépendante de recherche et d’aide à la décision · Données non garanties en temps réel')
st.info('Données issues de pages publiques BRVM lorsque la connexion fonctionne. Vérifiez toujours la date, le volume et le cours sur la source officielle. Ce service n’est pas affilié à la BRVM.')

if menu in ['Dashboard financier','Vue du marché','Radar court terme','Fiche action','Portefeuille']:
    try: df,updated=load_market()
    except Exception as exc:
        st.error(f'Connexion BRVM indisponible ou format modifié : {exc}')
        st.info('Réessayez plus tard. Aucun cours de démonstration ne remplace les cours officiels.')
        st.stop()
    st.caption(f'Dernière mise à jour indiquée par la source : {updated} · {len(df)} titres récupérés')

if menu=='Dashboard financier':
    dashboard_page()

elif menu=='Vue du marché':
    a,b,c,d=st.columns(4)
    a.metric('Titres disponibles',len(df));b.metric('En hausse',int((df['Variation %']>0).sum()));c.metric('En baisse',int((df['Variation %']<0).sum()));d.metric('Valeur échangée estimée',f"{(df['Clôture']*df['Volume']).sum()/1e9:.2f} Md FCFA")
    q=st.text_input('Rechercher un titre ou une société')
    view=df[df['Symbole'].str.contains(q,case=False,na=False)|df['Société'].str.contains(q,case=False,na=False)] if q else df
    st.dataframe(view,use_container_width=True,hide_index=True)
    st.download_button('Télécharger les cotations CSV',view.to_csv(index=False).encode('utf-8-sig'),'brvm_cotations.csv','text/csv')

elif menu=='Radar court terme':
    st.warning('Signal de séance exploratoire : ce classement n’est PAS le BRVM Short-Term Score complet. Il manque notamment les historiques 5/20 séances, volatilité, catalyseurs et liquidité moyenne.')
    ranked=score_session(df)
    st.subheader('Radar de séance — 100 points (provisoire)')
    st.caption('50 points : rang de valeur échangée estimée · 50 points : variation de séance bornée entre −7,5 % et +7,5 %. Ce score ne prédit pas la performance future.')
    st.dataframe(ranked[['Symbole','Société','Clôture','Variation %','Volume','Valeur échangée estimée','Signal séance /100']],use_container_width=True,hide_index=True)
    st.download_button('Exporter le radar CSV',ranked.to_csv(index=False).encode('utf-8-sig'),'brvm_radar_session.csv','text/csv')

elif menu=='Fiche action':
    symbol=st.selectbox('Action',sorted(df['Symbole'].tolist()))
    row=df[df['Symbole']==symbol].iloc[0]
    st.subheader(row['Société'])
    a,b,c=st.columns(3);a.metric('Cours de clôture',f"{row['Clôture']:,.0f} FCFA");b.metric('Variation séance',f"{row['Variation %']:+.2f}%");c.metric('Volume',f"{row['Volume']:,.0f}")
    st.info('Valorisation intrinsèque, états financiers historiques et score Opportunity : en attente de données vérifiées pour ce titre.')

elif menu=='Publications financières':
    st.subheader('Publications financières officielles')
    st.write('Consultez les états financiers, rapports et communiqués directement sur le site officiel de la BRVM. La pagination permet de retrouver les publications antérieures, notamment SMB.')
    st.link_button('📄 Consulter les rapports financiers BRVM',
                   'https://www.brvm.org/fr/type-document/etats-financiers?page=1',
                   use_container_width=True)
    st.caption('Lien externe : le contenu et les téléchargements sont gérés par la BRVM.')

elif menu=='Actualisation T1 / S1 / T3':
    st.subheader('V1.6 — Indicateurs actualisés sur 12 mois glissants (TTM)')
    st.caption('Les données intermédiaires sont généralement cumulées depuis janvier. Le moteur évite de multiplier les bénéfices trimestriels par quatre.')
    st.link_button('Rapports officiels SMB — BRVM','https://www.brvm.org/fr/rapports-societe-cotes/smb')
    from interim_engine import compute_ttm, extract_interim
    period=st.selectbox('Dernière période disponible',['T3','S1','T1'])
    year=st.number_input('Année du rapport intermédiaire',min_value=2010,max_value=2100,value=2026,step=1)
    uploaded=st.file_uploader('Rapport intermédiaire officiel PDF (facultatif)',type=['pdf'],key='v16_pdf')
    if uploaded:
        unit=st.selectbox('Unité déclarée dans le rapport',['FCFA','millions FCFA'])
        try:
            found=extract_interim(uploaded.getvalue(),period,int(year),unit)
            if found.empty:st.warning('Aucune ligne reconnue avec assez de certitude. Saisis les montants vérifiés dans le rapport ci-dessous.')
            else:
                st.info('Extraction candidate : vérifier les montants et les colonnes avec le PDF avant de les recopier.')
                st.dataframe(found,hide_index=True,use_container_width=True)
        except Exception as exc:st.warning('Lecture PDF non concluante : '+str(exc))
    st.markdown('#### Calcul contrôlé — montants en millions FCFA')
    st.caption('Renseigner les montants publiés, en distinguant exercice annuel N−1, cumul intermédiaire N et cumul intermédiaire N−1.')
    c1,c2,c3=st.columns(3)
    with c1: annual=st.number_input('Résultat net annuel N−1',value=13075.0,step=1.0)
    with c2: current=st.number_input('Résultat net cumul '+str(year),value=8903.818691 if period=='T3' and year==2026 else 0.0,step=1.0)
    with c3: prior=st.number_input('Résultat net cumul '+str(year-1),value=5687.235678 if period=='T3' and year==2026 else 0.0,step=1.0)
    shares=st.number_input('Nombre d’actions vérifié',min_value=1,value=7795200,step=100)
    quote=st.number_input('Cours daté (FCFA/action ; 0 = absent)',min_value=0.0,value=0.0,step=50.0)
    date_quote=st.date_input('Date du cours de référence') if quote>0 else None
    verified=st.checkbox('Je confirme que les trois résultats nets sont cumulés sur les périodes correctes et que les unités sont cohérentes.',key='v16_verified')
    if st.button('Actualiser BPA et PER TTM',key='v16_compute'):
        if not verified:st.error('Vérification préalable des périodes et montants requise.')
        else:
            try:
                r=compute_ttm(annual*1_000_000,current*1_000_000,prior*1_000_000,shares,quote or None)
                a,b,c=st.columns(3)
                a.metric('Résultat net TTM',f"{r['Résultat net TTM (FCFA)']/1_000_000:,.2f} M FCFA")
                b.metric('BPA TTM',f"{r['BPA TTM (FCFA)']:,.2f} FCFA")
                c.metric('PER TTM',f"{r['PER TTM']:.2f}x" if r['PER TTM'] is not None else 'Cours requis')
                if r['Variation période (%)'] is not None:st.metric('Variation du résultat net cumulé',f"{r['Variation période (%)']:+.1f} %")
                st.caption('PER historique TTM = cours daté / BPA TTM ; non applicable si BPA ≤ 0. Les données sont déclarées par l’utilisateur, pas certifiées par le moteur.')
                out=pd.DataFrame([{'Société':'SMB (exemple à adapter)','Période':period,'Année':year,'Cours date':str(date_quote) if date_quote else '',**r}])
                st.download_button('Exporter les indicateurs TTM CSV',out.to_csv(index=False,sep=';').encode('utf-8-sig'),'brvm_v16_ttm.csv','text/csv')
            except Exception as exc:st.error('Calcul impossible : '+str(exc))
    st.warning('La V1.6 ne recalcule pas automatiquement le FCFE/DCF à partir des seuls rapports d’activité : il faut des flux de trésorerie intermédiaires complets et vérifiés.')

elif menu=='Analyser un PDF':
    st.subheader('Extraction des états financiers — laboratoire')
    st.info('Les tableaux extraits sont des candidats à vérifier, pas des données comptables certifiées. Les PDF scannés nécessitent une reconnaissance OCR externe.')
    uploaded=st.file_uploader('Importer un rapport financier PDF (25 Mo, 100 pages maximum)',type=['pdf'])
    if uploaded:
        try:
            overview,extracted=extract_pdf(uploaded.getvalue())
            st.markdown('#### Diagnostic du document')
            st.dataframe(overview,hide_index=True,use_container_width=True)
            st.metric('Tableaux candidats',len(extracted))
            if not extracted:
                st.warning('Aucun tableau lisible reconnu. Vérifiez si le rapport est un scan. Essayez un PDF natif ou une extraction manuelle contrôlée.')
            else:
                st.download_button('📥 Exporter tous les tableaux en Excel',tables_excel(extracted),
                                   file_name='brvm_extraction_a_verifier.xlsx',
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                for i,item in enumerate(extracted[:40]):
                    with st.expander(f"Page {item['page']} · Tableau {i+1} · {item['method']}"):
                        st.dataframe(item['data'],hide_index=True,use_container_width=True)
                        st.download_button('Exporter CSV',item['data'].to_csv(index=False,header=False,sep=';').encode('utf-8-sig'),
                                           file_name=f"tableau_page_{item['page']}_{i+1}.csv",mime='text/csv',key=f'extract_{i}')
                if len(extracted)>40: st.caption('40 premiers tableaux affichés ; export Excel limité à 80 tableaux.')
            st.warning('Contrôlez les signes, unités (FCFA, milliers, millions), années, lignes et colonnes avec le PDF original.')
        except Exception as exc: st.error(f'Extraction impossible : {exc}')

elif menu=='Analyse fondamentale':
    st.subheader('Analyse fondamentale — collecte assistée depuis la BRVM')
    st.caption('Sélectionnez une société : aucun chiffre à saisir pour rechercher les publications. Les chiffres extraits restent soumis à vérification des unités et des périodes.')
    ticker=st.text_input('Symbole ou nom présent dans le titre des publications',value='SMB')
    pages=st.slider('Pages de publications à parcourir',1,8,4)
    if st.button('🔎 Rechercher les rapports officiels',type='primary'):
        try:
            with st.spinner('Recherche sur les pages publiques BRVM…'):
                st.session_state['auto_results']=discover(ticker,pages=pages)
                st.session_state.pop('auto_tables',None)
            st.success(f"{len(st.session_state['auto_results'])} liens candidats détectés. Ce n'est pas une garantie d'exhaustivité.")
        except Exception as exc:
            st.error(f'Recherche impossible : {exc}')
    results=st.session_state.get('auto_results',[])
    if results:
        st.dataframe(pd.DataFrame(results),hide_index=True,use_container_width=True,column_config={'URL':st.column_config.LinkColumn('Ouvrir la publication'),'Page source':st.column_config.LinkColumn('Source')})
        pdfs=[x for x in results if x['PDF']]
        if pdfs:
            chosen=st.selectbox('Choisir un PDF officiel à examiner',range(len(pdfs)),format_func=lambda i:pdfs[i]['Titre'][:110]+' · '+pdfs[i]['URL'].split('/')[-1][:45])
            if st.button('📥 Lire et extraire les tableaux du PDF sélectionné'):
                try:
                    with st.spinner('Téléchargement et lecture du rapport…'):
                        raw=download_pdf(pdfs[chosen]['URL'])
                        overview,tables=extract_pdf(raw)
                        st.session_state['auto_tables']={'source':pdfs[chosen]['URL'],'overview':overview,'tables':tables,'candidates':candidates_from_tables(tables),'structured':extract_structured(raw)}
                    st.success('Lecture terminée : consultez les résultats ci-dessous.')
                except Exception as exc: st.error(f'Extraction impossible : {exc}')
        else:
            st.info('Aucun PDF direct détecté. Ouvrez la publication officielle ; certains téléchargements sont générés dynamiquement.')
    extracted=st.session_state.get('auto_tables')
    if extracted:
        st.caption('Document source : '+extracted['source'])
        st.metric('Tableaux candidats',len(extracted['tables']))
        detailed, indicators, checks = extracted.get('structured',(pd.DataFrame(),pd.DataFrame(),pd.DataFrame()))
        if not indicators.empty:
            st.markdown('### États financiers structurés — extraction expérimentale')
            st.caption('Montants et années détectés depuis la position des textes dans le PDF. Les chiffres ne sont pas certifiés.')
            st.dataframe(indicators,hide_index=True,use_container_width=True)
            st.download_button('📥 Télécharger les indicateurs (CSV)',indicators.to_csv(index=False,sep=';').encode('utf-8-sig'),'brvm_indicateurs_extraits.csv','text/csv',key='structured_csv')
            fundamentals, ratios_table, analysis = fundamental_analysis(indicators)
            if not fundamentals.empty:
                st.markdown('### Analyse fondamentale calculée automatiquement')
                st.caption('Données en millions FCFA. Les ratios sont dérivés uniquement des valeurs extraites, avec renvoi à la page source. Vérifiez les chiffres avant toute décision.')
                st.dataframe(fundamentals,hide_index=True,use_container_width=True)
                st.download_button('Exporter les états financiers normalisés CSV',fundamentals.to_csv(index=False,sep=';').encode('utf-8-sig'),'brvm_etats_normalises.csv','text/csv',key='fundamental_export')
                st.markdown('### Dashboard financier — histogrammes annuels')
                st.caption('Historique limité aux exercices présents dans le rapport extrait. Pour les banques, utiliser le PNB lorsque disponible.')
                hist=history_from_fundamentals(fundamentals)
                if hist.empty or hist["Chiffre d'affaires"].isna().all():
                    st.info('Chiffre d’affaires non disponible dans ce document ; pour les banques, utiliser le dashboard avec un historique PNB.')
                else:
                    render_history(hist,source=extracted['source'])
                st.markdown('#### Ratios fondamentaux')
                st.dataframe(ratios_table,hide_index=True,use_container_width=True)
                st.download_button('Exporter les ratios CSV',ratios_table.to_csv(index=False,sep=';').encode('utf-8-sig'),'brvm_ratios.csv','text/csv',key='ratios_export')
                if analysis['ready']:
                    st.success('Contrôle du bilan réussi pour les périodes détectées. Cela ne certifie pas tous les postes.')
                else:
                    st.error('Contrôle du bilan insuffisant : ratios indicatifs, valorisation suspendue.')
                _, valuation_message=valuation_scenarios(analysis)
                st.info('Valorisation automatique : '+valuation_message)
                st.markdown('### V1.5 — Scénarios de valorisation FCFE (indicatifs)')
                st.caption('Pour sociétés non bancaires uniquement. Les flux de financement sont supposés ne contenir que les emprunts nets et dividendes ; vérifier cette hypothèse dans le rapport complet. Les hypothèses ne sont pas des prévisions.')
                bridge, bridge_error = reconstruct_fcfe(analysis)
                if bridge_error:
                    st.warning('Valorisation non disponible : '+bridge_error)
                else:
                    st.write('Réconciliation indicative des flux (millions FCFA)')
                    bridge_rows=[('Flux opérationnels',bridge['operating']),('Flux investissements (signés)',bridge['investing']),('Flux de financement (signés)',bridge['financing']),('Dividendes versés',bridge['dividends']),('Emprunts nets estimés = financement + dividendes',bridge['net_borrowing_proxy']),('FCFE estimé = opérationnels + investissements + emprunts nets',bridge['fcfe_proxy'])]
                    st.dataframe(pd.DataFrame(bridge_rows,columns=['Poste','Millions FCFA']),hide_index=True,use_container_width=True)
                    st.warning('Le FCFE estimé repose sur une seule année et une hypothèse de réconciliation. Les variations du BFR peuvent le rendre non représentatif. Aucun résultat n’est une recommandation d’achat.')
                    confirmed=st.checkbox('Je confirme avoir vérifié le nombre d’actions en circulation et l’absence d’autres flux de capitaux propres significatifs dans le rapport complet.',key='v15_confirm')
                    shares_text=st.text_input('Nombre d’actions en circulation (obligatoire ; aucune valeur présumée)',value='',key='v15_shares')
                    quote_v15=st.number_input('Cours BRVM de référence (FCFA/action ; 0 = non renseigné)',min_value=0.0,value=0.0,step=50.0,key='v15_quote')
                    with st.expander('Hypothèses des trois scénarios — modifiables'):
                        assumptions={}
                        for name,params in SCENARIOS.items():
                            st.markdown('**'+name+'**')
                            c1,c2,c3=st.columns(3)
                            with c1: growth=st.number_input('Croissance annuelle 5 ans (%)',value=float(params['growth']*100),step=0.5,key='v15_g_'+name)/100
                            with c2: discount=st.number_input('Coût des fonds propres (%)',value=float(params['discount']*100),step=0.5,key='v15_d_'+name)/100
                            with c3: terminal=st.number_input('Croissance terminale (%)',value=float(params['terminal_growth']*100),step=0.5,key='v15_t_'+name)/100
                            assumptions[name]={'growth':growth,'discount':discount,'terminal_growth':terminal}
                    if st.button('Calculer les trois scénarios V1.5',key='v15_run'):
                        if not confirmed:st.error('Confirmation des données de capital et des flux requise.')
                        else:
                            try:
                                shares_v15=int(shares_text.replace(' ','').replace('\u00a0',''))
                                if shares_v15<=0:raise ValueError('Le nombre d’actions doit être positif.')
                                table,_,error=run_scenarios(analysis,shares_v15,quote_v15,assumptions)
                                if error:st.error(error)
                                else:
                                    st.session_state['v15_results']=table
                                    st.session_state['v15_source']=extracted['source']
                            except (ValueError,OverflowError) as exc:st.error('Nombre d’actions ou hypothèses invalides : '+str(exc))
                    if st.session_state.get('v15_source')==extracted['source'] and 'v15_results' in st.session_state:
                        st.dataframe(st.session_state['v15_results'],hide_index=True,use_container_width=True)
                        st.download_button('Exporter les scénarios V1.5 (CSV)',st.session_state['v15_results'].to_csv(index=False,sep=';').encode('utf-8-sig'),'brvm_v15_valorisation.csv','text/csv',key='v15_export')

            if not checks.empty:
                st.markdown('#### Contrôles de cohérence')
                st.dataframe(checks,hide_index=True,use_container_width=True)
            if not detailed.empty:
                with st.expander('Voir les lignes financières détectées et leurs pages'):
                    st.dataframe(detailed,hide_index=True,use_container_width=True)
            st.info('Extraction expérimentale adaptée aux états de synthèse en colonnes côte à côte. Vérifiez chaque montant avec le PDF avant tout calcul de valorisation.')
        else:
            st.warning('Le format de ce rapport ne correspond pas encore à un modèle de tableau structuré reconnu. Aucun chiffre ne sera inventé.')
        st.dataframe(extracted['overview'],hide_index=True,use_container_width=True)
        candidates=extracted['candidates']
        if candidates.empty:
            st.warning('Aucune ligne financière reconnue avec une certitude suffisante. Consultez les tableaux bruts ou essayez un autre rapport. Aucun ratio automatique ne sera affiché.')
        else:
            st.markdown('#### Montants détectés — non certifiés')
            st.dataframe(candidates,hide_index=True,use_container_width=True)
            st.download_button('Exporter les montants candidats CSV',candidates.to_csv(index=False,sep=';').encode('utf-8-sig'),'brvm_montants_a_verifier.csv','text/csv')
        if extracted['tables']:
            st.download_button('Exporter les tableaux du PDF (Excel)',tables_excel(extracted['tables']),'brvm_tableaux_a_verifier.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            for i,item in enumerate(extracted['tables'][:15]):
                with st.expander(f"Page {item['page']} · Tableau {i+1} · {item['method']}"):
                    st.dataframe(item['data'],hide_index=True,use_container_width=True)
        st.caption('Les résultats de valorisation V1.5 restent conditionnés à la vérification du capital, des flux et des hypothèses. Aucune donnée manquante n’est remplacée par zéro.')
    st.link_button('Voir toutes les publications officielles', 'https://www.brvm.org/fr/type-document/etats-financiers?page=1')

elif menu=='Valeur intrinsèque':
    st.subheader('Valorisation intrinsèque — modèles transparents')
    st.warning('Calculateur de scénarios : les valeurs ne sont pas des estimations vérifiées tant que les hypothèses et les états financiers ne le sont pas.')
    method=st.selectbox('Méthode',['DCF des flux aux actionnaires (FCFE)','Dividendes actualisés (Gordon)','Résultat résiduel (banques / capitaux propres)'])
    source=st.text_input('Titre, période et source des données',placeholder='SMB — rapport annuel vérifié, exercice ...')
    quote=st.number_input('Cours de référence (FCFA / action, 0 si inconnu)',min_value=0.0,value=0.0,step=100.0)
    try:
        if method.startswith('DCF'):
            st.caption('Tous les flux sont exprimés en FCFA (pas en milliers ou millions). FCFE = flux disponibles pour les actionnaires après investissements et financement net.')
            fcfe=st.number_input('FCFE de référence (FCFA)',value=0.0,format='%.2f')
            shares=st.number_input('Nombre d’actions',min_value=1,value=1000000,step=1000)
            growth=st.number_input('Croissance annuelle des flux (%)',value=3.0,step=0.5)/100
            discount=st.number_input('Coût des fonds propres (%)',value=15.0,step=0.5)/100
            terminal=st.number_input('Croissance terminale (%)',value=2.0,step=0.5)/100
            years=st.slider('Horizon explicite (années)',3,10,5)
            if st.button('Calculer la valorisation',type='primary'):
                if fcfe<=0: st.error('Le FCFE doit être positif pour ce modèle simplifié. Utilisez un autre modèle ou une analyse de scénarios adaptée.')
                else:
                    result=dcf_fcfe(fcfe,growth,discount,terminal,shares,years)
                    st.session_state['intrinsic_result']=(method,result['value_per_share'],source,quote)
                    st.caption(f"Part de la valeur terminale : {result['terminal_share']*100:.1f} % (sensibilité potentiellement élevée).")
        elif method.startswith('Dividendes'):
            div=st.number_input('Dernier dividende par action (FCFA)',min_value=0.0,value=0.0)
            growth=st.number_input('Croissance pérenne du dividende (%)',value=2.0)/100
            cost=st.number_input('Coût des fonds propres (%)',value=15.0)/100
            if st.button('Calculer la valorisation',type='primary'):
                st.session_state['intrinsic_result']=(method,dividend_discount(div,growth,cost),source,quote)
        else:
            bv=st.number_input('Capitaux propres par action (FCFA)',min_value=0.0,value=0.0)
            roe=st.number_input('ROE durable (%)',value=12.0)/100
            cost=st.number_input('Coût des fonds propres (%)',value=15.0)/100
            growth=st.number_input('Croissance des résultats résiduels (%)',value=2.0)/100
            if st.button('Calculer la valorisation',type='primary'):
                st.session_state['intrinsic_result']=(method,residual_income(bv,roe,cost,growth),source,quote)
        result=st.session_state.get('intrinsic_result')
        if result and result[0]==method:
            value=result[1]
            st.metric('Valeur intrinsèque modélisée',f'{value:,.0f} FCFA / action')
            if result[3]>0 and value>0:st.metric('Décote / prime par rapport au cours',f'{(value/result[3]-1)*100:+.1f} %')
            st.markdown('#### Prix d’achat selon la marge de sécurité')
            prices=pd.DataFrame([{'Marge de sécurité':f'{m} %','Prix maximum FCFA':round(value*(1-m/100),2)} for m in (10,20,30)])
            st.dataframe(prices,hide_index=True,use_container_width=True)
            st.download_button('Exporter la valorisation CSV',prices.to_csv(index=False,sep=';').encode('utf-8-sig'),'valorisation_scenarios.csv','text/csv')
            if not result[2].strip():st.warning('La période et la source ne sont pas documentées. Résultat non vérifiable.')
    except ValueError as exc:st.error(str(exc))

elif menu=='Portefeuille':
    st.subheader('Simulateur de portefeuille (session locale)')
    st.caption('Les positions ne sont pas enregistrées après fermeture de la session. Aucune transaction réelle.')
    if 'positions' not in st.session_state:st.session_state.positions=[]
    with st.form('position'):
        sym=st.selectbox('Titre',sorted(df['Symbole'].tolist()))
        qty=st.number_input('Quantité',min_value=1,value=10,step=1)
        cost=st.number_input('Prix de revient par action (FCFA)',min_value=1.,value=1000.,step=100.)
        if st.form_submit_button('Ajouter une position'):
            st.session_state.positions.append({'Symbole':sym,'Quantité':qty,'Prix de revient':cost})
    if st.session_state.positions:
        p=pd.DataFrame(st.session_state.positions).merge(df[['Symbole','Clôture']],on='Symbole',how='left')
        p['Coût']=p['Quantité']*p['Prix de revient'];p['Valeur']=p['Quantité']*p['Clôture'];p['P/L']=p['Valeur']-p['Coût']
        st.dataframe(p,hide_index=True,use_container_width=True)
        st.metric('Plus-value / moins-value latente hors frais',f"{p['P/L'].sum():,.0f} FCFA")
        st.download_button(
            '📥 Exporter le portefeuille CSV',
            data=p.to_csv(index=False, sep=';').encode('utf-8-sig'),
            file_name='BRVM_RADAR_Portefeuille.csv',
            mime='text/csv',
            use_container_width=True,
        )
        if st.button('Effacer le portefeuille'):st.session_state.positions=[];st.rerun()

elif menu=='Informations légales':
    st.subheader('Informations légales et confidentialité')
    st.markdown('''**Statut** : outil indépendant de recherche, non affilié à la BRVM. **Aucun conseil personnalisé ni passage d’ordre**. Les données de marché peuvent être différées, incomplètes ou indisponibles. Vérifiez les informations officielles avant toute décision.\n\n**Confidentialité** : n’envoyez pas de données personnelles ou financières confidentielles. Les PDF sont traités en mémoire pendant la session, sans base documentaire persistante dans ce prototype. L’hébergeur peut conserver des journaux techniques selon sa politique. Le portefeuille de démonstration est limité à la session en cours.\n\n**Avant lancement commercial** : confirmer les droits de réutilisation des données BRVM, définir l’éditeur responsable, l’adresse de contact, les conditions d’utilisation, la politique de confidentialité et les obligations légales applicables.''')

elif menu=='Méthodologie':
    st.markdown('''### Objectif final du Short-Term Score /100
- Momentum multi-horizon : 30 points
- Liquidité moyenne en valeur : 20 points
- Accélération récente : 20 points
- Tendance : 15 points
- Valorisation : 5 points
- Risque de retournement : 10 points

**Non disponible dans ce MVP** : séries historiques suffisamment complètes pour calculer ce score, normalisation automatisée de tous les bilans, DCF/valorisation universelle, alertes persistantes et exécution d’ordres.

Les documents financiers rectificatifs doivent prévaloir sur les versions précédentes après vérification. Les banques et assurances nécessitent des règles comptables adaptées.

**Sécurité** : n’insérez aucun identifiant bancaire ni mot de passe de courtage. L’outil ne passe aucun ordre.''')

st.divider()
st.caption('BRVM RADAR · Bêta publique · Non affilié à la BRVM · Pas de recommandation personnalisée · Aucun ordre de bourse')
