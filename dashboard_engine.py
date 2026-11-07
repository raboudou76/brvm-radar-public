"""BRVM RADAR: historical financial dashboard. No fabricated years."""
import io
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

DEMO_SGBCI = pd.DataFrame([
    {"Année":2020,"PNB":164062,"Résultat net":48435},
    {"Année":2024,"PNB":263207,"Résultat net":101228},
])

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
    if "Année" not in df.columns or "Dividende brut" not in df.columns:
        st.info("Historique des dividendes indisponible : fournir Année et Dividende brut.")
        return
    data=df.copy()
    data["Année"]=pd.to_numeric(data["Année"],errors="coerce")
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
    st.dataframe(data[["Année","Dividende brut","Dividende net"]],hide_index=True,use_container_width=True)


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

def dashboard_page():
    st.subheader("Dashboard financier — histogrammes et tendances")
    st.info("Les données de démonstration SGBCI proviennent de l'étude fournie et ne sont pas des cours ou comptes actualisés.")
    choice=st.radio("Source des données",["Exemple SGBCI (2020 et 2024)","Importer un historique CSV"],horizontal=True)
    if choice.startswith("Exemple"):
        render_history(DEMO_SGBCI,"Étude SGBCI fournie — exercices 2020 et 2024")
    else:
        st.caption("CSV séparé par ; ou , avec colonnes Année, Résultat net, Chiffre d'affaires (ou PNB), montants en millions FCFA. Colonnes facultatives : Dividende brut, Dividende net ou IRVM (%), en FCFA/action.")
        uploaded=st.file_uploader("Historique financier CSV",type=["csv"],key="dashboard_csv")
        if uploaded:
            try:
                raw=uploaded.getvalue()
                df=pd.read_csv(io.BytesIO(raw),sep=None,engine="python",encoding="utf-8-sig")
                render_history(df,f"Fichier importé : {uploaded.name}")
            except Exception as exc:st.error(f"Historique non exploitable : {exc}")
