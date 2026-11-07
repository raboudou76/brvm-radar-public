"""BRVM RADAR: historical financial dashboard. No fabricated years."""
import io
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from brvm_sync import fetch_dividends, for_issuer, URL as DIVIDENDS_URL
from brvm_financial_sync import find_reports, sync_financials


def _number(v):
    if pd.isna(v): return None
    if isinstance(v,(int,float)): return float(v)
    s=str(v).strip().replace("\u202f","").replace(" ","").replace("\xa0","").replace(",",".")
    try: return float(s)
    except ValueError: return None

def clean_history(df):
    required={"Année","Résultat net"}
    if not required.issubset(df.columns):
        raise ValueError("Colonnes obligatoires : Année, Résultat net et Chiffre d'affaires (ou PNB).")
    metric="PNB" if "PNB" in df.columns else "Chiffre d'affaires"
    if metric not in df.columns: raise ValueError("Colonne Chiffre d'affaires ou PNB absente.")
    out=df[["Année",metric,"Résultat net"]].copy()
    out["Année"]=pd.to_numeric(out["Année"],errors="coerce")
    for c in [metric,"Résultat net"]: out[c]=out[c].map(_number)
    out=out.dropna(subset=["Année"]).sort_values("Année")
    if out["Année"].duplicated().any():raise ValueError("Une seule observation par exercice est autorisée.")
    out["Année"]=out["Année"].astype(int)
    return out,metric

def _bar_labels(values, unit):
    """Use compact, consistent labels; underlying values remain unchanged."""
    is_millions = "million" in unit.casefold()
    numeric = pd.to_numeric(values, errors="coerce")
    if is_millions and numeric.dropna().abs().max() >= 1000:
        return [f"{v / 1000:,.2f}".replace(",", " ").replace(".", ",") + " Md" if pd.notna(v) else "" for v in numeric]
    return [f"{v:,.0f}".replace(",", " ") if pd.notna(v) else "" for v in numeric]


def _labeled_histogram(data, column, unit):
    """Plotly histogram with permanent labels above each annual bar."""
    labels = _bar_labels(data[column], unit)
    years = data["Année"].astype(str)
    fig = go.Figure(go.Bar(
        x=years,
        y=data[column],
        text=labels,
        textposition="outside",
        textfont=dict(size=13),
        cliponaxis=False,
        customdata=labels,
        hovertemplate="Exercice %{x}<br>Valeur : %{customdata}<extra></extra>",
        marker_color="#1677A8",
    ))
    positive = pd.to_numeric(data[column], errors="coerce").dropna()
    max_value = positive.max() if not positive.empty else 0
    min_value = positive.min() if not positive.empty else 0
    if max_value > 0 and min_value >= 0:
        fig.update_yaxes(range=[0, max_value * 1.20])
    fig.update_layout(
        height=360,
        margin=dict(l=12, r=16, t=42, b=16),
        xaxis_title="Exercice",
        yaxis_title=unit,
        showlegend=False,
        xaxis=dict(type="category"),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_dividend_history(df, unit="FCFA/action", default_tax=12.0):
    """Five-year dividend history; gross is used for payout, net for investor cash yield."""
    if "Année" not in df.columns or not ({"Dividende brut", "Dividende net"} & set(df.columns)):
        st.info("Historique indisponible : fournir Année et Dividende net ou Dividende brut.")
        return
    data=df.copy()
    data["Année"]=pd.to_numeric(data["Année"],errors="coerce")
    if "Dividende brut" not in data.columns:
        data["Dividende brut"]=float("nan")
    data["Dividende brut"]=data["Dividende brut"].map(_number)
    if "Dividende net" in data.columns:
        data["Dividende net"]=data["Dividende net"].map(_number)
    elif "IRVM (%)" in data.columns:
        data["IRVM (%)"]=data["IRVM (%)"].map(_number)
        data["Dividende net"]=data["Dividende brut"]*(1-data["IRVM (%)"]/100)
    else:
        st.warning("Dividende net non publié et IRVM historique non renseigné : estimation au taux sélectionné, à vérifier pour chaque exercice.")
        data["Dividende net"]=data["Dividende brut"]*(1-default_tax/100)
    data=data.dropna(subset=["Année"]).sort_values("Année").tail(5)
    data["Année"]=data["Année"].astype(int)
    st.markdown("#### Dividendes nets par action — cinq derniers exercices disponibles")
    _labeled_histogram(data,"Dividende net",unit)
    st.caption("Le dividende net correspond au profil fiscal sélectionné ou au montant publié, selon la source. Le taux de distribution utilise exclusivement le dividende brut.")
    st.dataframe(data[[c for c in ["Année","Dividende brut","Dividende net","Statut","Source"] if c in data.columns]],hide_index=True,use_container_width=True)


def render_history(df,source="Source non précisée", unit="millions FCFA"):
    data,metric=clean_history(df)
    data=data.tail(5).copy()
    st.caption(f"Source : {source} · Unité : {unit} · Cinq derniers exercices disponibles ; années absentes non interpolées")
    if data.empty: st.warning("Aucun exercice exploitable."); return
    valid=data.dropna(subset=[metric])
    if not valid.empty:
        latest=valid.iloc[-1]
        st.metric(f"{metric} — {int(latest['Année'])}",f"{latest[metric]:,.0f} M FCFA".replace(","," "))
    st.markdown(f"#### {metric} — histogramme annuel")
    _labeled_histogram(data, metric, unit)
    st.markdown("#### Résultat net — histogramme annuel")
    _labeled_histogram(data, "Résultat net", unit)
    st.markdown("#### Croissance et rentabilité")
    enriched=data.copy()
    enriched["Croissance activité (%)"]=enriched[metric].pct_change(fill_method=None)*100
    enriched["Croissance RN (%)"]=enriched["Résultat net"].pct_change(fill_method=None)*100
    # Do not present multi-year interval growth as YoY.
    gaps=enriched["Année"].diff()
    enriched.loc[gaps!=1,["Croissance activité (%)","Croissance RN (%)"]]=float('nan')
    enriched["Marge nette (%)"]=enriched["Résultat net"]/enriched[metric].replace(0,float('nan'))*100
    st.dataframe(enriched,hide_index=True,use_container_width=True)
    if "Dividende brut" in df.columns:
        render_dividend_history(df)
    st.download_button("Exporter le dashboard CSV",enriched.to_csv(index=False,sep=";").encode("utf-8-sig"),"brvm_dashboard_historique.csv","text/csv")

def history_from_fundamentals(fundamentals,bank=False):
    """Convert the V1.4 table into two annual observations, without guessing."""
    if fundamentals is None or fundamentals.empty:return pd.DataFrame()
    years=[c for c in fundamentals.columns if str(c).isdigit() and len(str(c))==4]
    if not years:return pd.DataFrame()
    labels=fundamentals["Indicateur"].astype(str).str.casefold()
    name="PNB" if bank else "Chiffre d'affaires"
    rows=[]
    for year in years:
        row={"Année":int(year)}
        for label,matcher in [(name,"produit net bancaire" if bank else "chiffre d’affaires"),("Résultat net","résultat net")]:
            mask=labels.str.contains(matcher,regex=False)
            row[label]=_number(fundamentals.loc[mask,year].iloc[0]) if mask.any() else None
        rows.append(row)
    return pd.DataFrame(rows)

@st.cache_data(ttl=6*3600, show_spinner=False)
def cached_dividend_sync(max_pages):
    return fetch_dividends(max_pages=max_pages)

def render_live_dividends(key="dashboard"):
    st.markdown("### Synchronisation des dividendes — BRVM")
    st.caption("Lecture des annonces publiques BRVM (cache de 6 h). La couverture dépend des pages accessibles ; les exercices manquants restent vides.")
    pages = st.slider("Pages BRVM à consulter", 1, 30, 12, key=f"{key}_pages")
    if st.button("Synchroniser les annonces BRVM", key=f"{key}_sync"):
        cached_dividend_sync.clear()
    try:
        records, synced_at = cached_dividend_sync(pages)
    except Exception as exc:
        st.warning(f"Synchronisation BRVM indisponible : {exc}. Les données intégrées et l'import CSV restent utilisables.")
        return
    st.caption(f"Dernière consultation : {synced_at} · {len(records)} annonces extraites · Source : {DIVIDENDS_URL}")
    issuers = sorted(records["Société"].dropna().unique())
    index = issuers.index("SMB") if "SMB" in issuers else 0
    issuer = st.selectbox("Société ayant une annonce accessible", issuers, index=index, key=f"{key}_issuer")
    selected = for_issuer(records, issuer)
    if issuer == "SMB":
        st.info("SMB 2025 : 704 FCFA nets pour personne physique (référence utilisateur), contre 800 FCFA dans la colonne net de la BRVM. Les deux valeurs sont conservées pour traçabilité.")
    else:
        st.warning("Les montants BRVM sont présentés comme publiés ; le net réellement perçu par une personne physique peut différer. Aucune conversion fiscale automatique non justifiée.")
    render_dividend_history(selected)
    st.download_button("Exporter les annonces BRVM CSV", selected.to_csv(index=False,sep=";").encode("utf-8-sig"), f"dividendes_brvm_{issuer.replace(' ','_')}.csv", "text/csv", key=f"{key}_download")


@st.cache_data(ttl=6*3600, show_spinner=False)
def cached_financial_reports(issuer, pages):
    return find_reports(issuer, pages=pages)

@st.cache_data(ttl=6*3600, show_spinner=False)
def cached_financial_history(report_urls):
    # Tuples are stable cache keys; reconstruct the report dictionaries.
    reports = [{'URL': url, 'Titre': title} for url, title in report_urls]
    return sync_financials(reports, max_reports=len(reports))

def dashboard_page():
    st.subheader("Dashboard financier — histogrammes et tendances")
    st.caption("Données issues des publications officielles BRVM ; aucun jeu de démonstration ou référence financière préchargée.")
    choice = st.radio("Source", ["Publications financières BRVM (automatique)", "Importer un historique CSV"], horizontal=True)
    if choice.startswith("Publications"):
        issuer = st.text_input("Nom ou symbole de la société", value="SMB", help="Exemples : SMB, SONATEL, SGBCI. Utiliser le nom employé dans les publications BRVM.")
        pages = st.slider("Pages de publications BRVM à explorer", 1, 8, 5)
        if st.button("Rechercher et actualiser les publications", key="fin_search"):
            cached_financial_reports.clear()
            cached_financial_history.clear()
        if len(issuer.strip()) >= 2:
            try:
                reports = cached_financial_reports(issuer.strip(), pages)
            except Exception as exc:
                st.warning(f"Recherche BRVM indisponible : {type(exc).__name__} — {exc}")
                reports = []
            if reports:
                st.caption(f"{len(reports)} document(s) PDF annuel(s) candidat(s) trouvé(s). Les rapports intermédiaires sont exclus.")
                max_reports = min(len(reports), 6)
                count = st.slider("Nombre de rapports à analyser", 1, max_reports, min(4, max_reports))
                selected = reports[:count]
                st.dataframe(pd.DataFrame(selected)[["Titre", "URL"]], hide_index=True, use_container_width=True)
                with st.spinner("Chargement automatique des données financières BRVM..."):
                    history, detail, errors, synced = cached_financial_history(tuple((r['URL'],r['Titre']) for r in selected))
                st.session_state['brvm_fin_history'] = (issuer.strip(), history, detail, errors, synced)
            else:
                st.info("Aucun PDF annuel identifié dans les pages consultées. Essayez la dénomination complète ou davantage de pages.")
        current = st.session_state.get('brvm_fin_history')
        if current and current[0].casefold() == issuer.strip().casefold():
            _, history, detail, errors, synced = current
            st.caption(f"Dernière extraction : {synced} · Les montants sont des candidats extraits automatiquement, à contrôler dans les PDF sources.")
            if not history.empty:
                if history["Chiffre d'affaires"].notna().any() or history['Résultat net'].notna().any():
                    render_history(history, source="Publications BRVM — voir les URL des rapports ci-dessous")
                else:
                    st.warning("Aucun chiffre d'affaires ou résultat net exploitable.")
            else:
                st.warning("Les documents trouvés ne correspondent pas au format reconnu par l'extracteur. Aucun montant n'est inventé.")
            if not detail.empty:
                st.markdown("#### Traçabilité des montants et contrôle des sources")
                st.dataframe(detail, hide_index=True, use_container_width=True)
                st.download_button("Exporter les montants sourcés CSV", detail.to_csv(index=False,sep=';').encode('utf-8-sig'), "brvm_extraction_financiere.csv", "text/csv", key="fin_detail_export")
            for error in errors:
                st.caption("Rapport non exploité : " + error)
            st.info("Les banques nécessitent un extracteur PNB spécifique ; un PNB absent ne sera jamais remplacé par un chiffre d'affaires fictif. Les exercices manquants restent vides.")
    else:
        st.caption("CSV avec Année, Résultat net et Chiffre d'affaires (ou PNB), en millions FCFA. Dividende brut et Dividende net facultatifs, en FCFA/action.")
        uploaded = st.file_uploader("Historique financier CSV", type=["csv"], key="dashboard_csv")
        if uploaded:
            try:
                df = pd.read_csv(io.BytesIO(uploaded.getvalue()), sep=None, engine="python", encoding="utf-8-sig")
                render_history(df, f"Fichier importé : {uploaded.name}")
            except Exception as exc:
                st.error(f"Historique non exploitable : {exc}")
    st.divider()
    render_live_dividends(key="dashboard")
