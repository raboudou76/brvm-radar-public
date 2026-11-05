import io, re, os
from datetime import datetime, timezone
from urllib.parse import urljoin
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

BASE='https://www.brvm.org'
MARKET=BASE+'/fr/cours-actions/0'
FIN=BASE+'/fr/type-document/etats-financiers'
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; BRVMRadarResearch/1.0)'}
st.set_page_config(page_title='BRVM RADAR | Marché et analyse BRVM',page_icon='📈',layout='wide')
st.markdown('<style>.block-container{padding-top:1.5rem}h1{color:#102544}div[data-testid="stMetric"]{background:#f3f6fc;padding:12px;border-radius:10px}</style>',unsafe_allow_html=True)

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
st.sidebar.caption('Investment Intelligence · Web MVP')
menu=st.sidebar.radio('Navigation',['Vue du marché','Radar court terme','Fiche action','Publications financières','Analyser un PDF','Portefeuille','Méthodologie','Informations légales'])
st.sidebar.link_button('Site officiel BRVM',BASE)
st.sidebar.caption('Bêta publique · Aucun compte ni ordre de bourse')
st.title('BRVM RADAR')
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
    st.subheader('Publications financières BRVM')
    st.caption('Inventaire indicatif des liens accessibles dans le HTML de la rubrique BRVM ; couverture non exhaustive.')
    if st.button('Actualiser les publications'):
        publications.clear()
    try:
        pubs = publications()
        q = st.text_input('Rechercher société, symbole ou rapport (ex. SMB, SMBC, T3)')
        if q:
            match = pubs[['Publication', 'Contexte', 'Lien']].fillna('').apply(
                lambda col: col.str.contains(q, case=False, regex=False)
            ).any(axis=1)
            pubs = pubs.loc[match]
        st.caption(f'{len(pubs)} lien(s) correspondant(s) dans la page consultée')
        if pubs.empty:
            st.warning('Aucun document trouvé dans cet inventaire. Cela ne signifie pas que le rapport est inexistant.')
        else:
            st.dataframe(pubs[['Publication', 'Type', 'Lien']],
                         column_config={'Lien': st.column_config.LinkColumn('Ouvrir le document / la page')},
                         use_container_width=True, hide_index=True)
            st.download_button('📥 Exporter l’inventaire CSV',
                               pubs.to_csv(index=False, sep=';').encode('utf-8-sig'),
                               'brvm_publications.csv', 'text/csv')
        st.info('Un lien de type « Page / lien » ne garantit pas un téléchargement PDF direct. Vérifier le document sur la source.')
    except Exception as exc:
        st.error(f'Erreur de récupération : {exc}')
    st.link_button('Consulter la rubrique officielle', FIN)

elif menu=='Analyser un PDF':
    st.subheader('Prélecture et extraction expérimentale des tableaux PDF')
    uploaded = st.file_uploader('Importer un rapport financier PDF', type=['pdf'])
    if uploaded:
        if uploaded.size > 15 * 1024 * 1024:
            st.error('PDF trop volumineux : limite de 15 Mo pour la bêta publique.')
            st.stop()
        try:
            import fitz
            doc = fitz.open(stream=uploaded.getvalue(), filetype='pdf')
            rows, extracted = [], []
            for i, page in enumerate(doc):
                txt = page.get_text('text')
                low = txt.lower()
                rows.append({
                    'Page': i + 1,
                    'Bilan': ('bilan' in low or 'total actif' in low),
                    'Compte de résultat': ('compte de résultat' in low or 'compte de resultat' in low),
                    'Flux de trésorerie': ('flux de trésorerie' in low or 'flux de tresorerie' in low),
                    'Caractères': len(txt),
                })
                # PyMuPDF reconnaît certaines grilles textuelles ; pas les scans sans OCR.
                try:
                    tables = page.find_tables()
                    for j, table in enumerate(tables.tables, start=1):
                        data = table.extract()
                        if data and len(data) > 1:
                            extracted.append((i + 1, j, pd.DataFrame(data)))
                except (AttributeError, ValueError, RuntimeError):
                    pass
            doc.close()
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            st.caption(f'{len(extracted)} tableau(x) candidat(s) détecté(s), sans certification des chiffres.')
            if not extracted:
                st.warning('Aucun tableau structuré reconnu. Le PDF peut être scanné ou utiliser une mise en page non prise en charge.')
            else:
                for page_num, table_num, frame in extracted[:30]:
                    with st.expander(f'Page {page_num} · Tableau {table_num} ({len(frame)} lignes)'):
                        st.dataframe(frame, hide_index=True, use_container_width=True)
                        st.download_button(
                            '📥 Télécharger ce tableau CSV',
                            frame.to_csv(index=False, header=False, sep=';').encode('utf-8-sig'),
                            file_name=f'brvm_pdf_page_{page_num}_tableau_{table_num}.csv',
                            mime='text/csv',
                            key=f'pdf_{page_num}_{table_num}',
                        )
                if len(extracted) > 30:
                    st.info('Seuls les 30 premiers tableaux sont affichés.')
            st.warning('Extraction expérimentale : contrôler les années, unités, colonnes et montants sur le PDF original avant toute valorisation.')
        except Exception as exc:
            st.error(f'Impossible de lire le PDF : {exc}')

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
