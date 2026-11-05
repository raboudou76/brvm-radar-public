import io, re, os
from datetime import datetime, timezone
from urllib.parse import urljoin
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from finance_engine import extract_pdf, tables_excel, ratios, dcf_fcfe, dividend_discount, residual_income

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
st.sidebar.caption('Investment Intelligence · V1.2')
menu=st.sidebar.radio('Navigation',['Vue du marché','Radar court terme','Fiche action','Analyse fondamentale','Valeur intrinsèque','Publications financières','Analyser un PDF','Portefeuille','Méthodologie','Informations légales'])
st.sidebar.link_button('Site officiel BRVM',BASE)
st.sidebar.caption('Bêta publique · Aucun compte ni ordre de bourse')
st.title('◈ BRVM RADAR')
st.caption('Bêta publique · Plateforme indépendante de recherche et d’aide à la décision · Données non garanties en temps réel')
st.info('Données issues de pages publiques BRVM lorsque la connexion fonctionne. Vérifiez toujours la date, le volume et le cours sur la source officielle. Ce service n’est pas affilié à la BRVM.')

if menu in ['Vue du marché','Radar court terme','Fiche action','Portefeuille']:
    try: df,updated=load_market()
    except Exception as exc:
        st.error(f'Connexion BRVM indisponible ou format modifié : {exc}')
        st.info('Réessayez plus tard. Aucun cours de démonstration ne remplace les cours officiels.')
        st.stop()
    st.caption(f'Dernière mise à jour indiquée par la source : {updated} · {len(df)} titres récupérés')

if menu=='Vue du marché':
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
    st.subheader('Analyse fondamentale — saisie financière vérifiée')
    st.caption('Saisissez les montants issus des états financiers contrôlés. Aucune donnée fondamentale n’est inventée ni automatiquement associée à une société.')
    ticker=st.text_input('Société / symbole étudié',value='SMB')
    period=st.text_input('Période et source du rapport',placeholder='Ex. 2025 annuel — BRVM, rapport daté du ...')
    unit=st.selectbox('Unité des montants',['FCFA','milliers FCFA','millions FCFA'])
    sector=st.selectbox('Secteur',['Industrie / services','Banque','Assurance','Autre'])
    with st.form('fundamentals'):
        c1,c2=st.columns(2)
        with c1:
            ca=st.number_input('Chiffre d’affaires / produit net bancaire',value=0.0,format='%.2f')
            net=st.number_input('Résultat net',value=0.0,format='%.2f')
            equity=st.number_input('Capitaux propres',value=0.0,format='%.2f')
        with c2:
            debt=st.number_input('Dette financière',value=0.0,format='%.2f')
            cfo=st.number_input('Flux opérationnel',value=0.0,format='%.2f')
            capex=st.number_input('Investissements (décaissements positifs)',value=0.0,format='%.2f')
            delta_debt=st.number_input('Variation nette de dette (+ si nouvel emprunt)',value=0.0,format='%.2f')
        submitted=st.form_submit_button('Calculer les indicateurs',type='primary')
    if submitted:
        if not period.strip(): st.warning('Renseignez la période et la source pour assurer la traçabilité.')
        vals={'chiffre_affaires':ca if ca!=0 else None,'resultat_net':net,'capitaux_propres':equity if equity!=0 else None,'dette_financiere':debt,'flux_operationnel':cfo,'investissements':capex,'variation_dette':delta_debt}
        rr=ratios(vals)
        def fmt_pct(x):return f'{x*100:.2f} %' if x is not None else 'Non calculable'
        st.metric('Marge nette',fmt_pct(rr['Marge nette']))
        st.metric('ROE',fmt_pct(rr['ROE']))
        st.metric('Dette / fonds propres',fmt_pct(rr['Dette / capitaux propres']))
        st.metric('FCFE indicatif',f"{rr['FCFE (proxy)']:,.2f} {unit}" if rr['FCFE (proxy)'] is not None else 'Non calculable')
        if sector=='Banque': st.warning('Les flux de trésorerie et la dette ne s’interprètent pas comme pour une société industrielle. Privilégiez le ROE, le P/B et le résultat résiduel.')
        st.download_button('Exporter les indicateurs CSV',pd.DataFrame([{'Titre':ticker,'Période / source':period,'Unité':unit,'Secteur':sector,**rr}]).to_csv(index=False,sep=';').encode('utf-8-sig'),'analyse_fondamentale.csv','text/csv')

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
