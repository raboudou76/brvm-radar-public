"""BRVM RADAR: historical financial dashboard. No fabricated years."""
import io
import pandas as pd
import streamlit as st

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

def render_history(df,source="Source non précisée", unit="millions FCFA"):
    data,metric=clean_history(df)
    st.caption(f"Source : {source} · Unité : {unit} · Années absentes non interpolées")
    if data.empty: st.warning("Aucun exercice exploitable."); return
    valid=data.dropna(subset=[metric])
    if not valid.empty:
        latest=valid.iloc[-1]
        st.metric(f"{metric} — {int(latest['Année'])}",f"{latest[metric]:,.0f} M FCFA".replace(","," "))
    st.markdown(f"#### {metric} — histogramme annuel")
    st.bar_chart(data.set_index("Année")[[metric]],x_label="Exercice",y_label=unit,use_container_width=True)
    st.markdown("#### Résultat net — histogramme annuel")
    st.bar_chart(data.set_index("Année")[["Résultat net"]],x_label="Exercice",y_label=unit,use_container_width=True)
    st.markdown("#### Croissance et rentabilité")
    enriched=data.copy()
    enriched["Croissance activité (%)"]=enriched[metric].pct_change(fill_method=None)*100
    enriched["Croissance RN (%)"]=enriched["Résultat net"].pct_change(fill_method=None)*100
    # Do not present multi-year interval growth as YoY.
    gaps=enriched["Année"].diff()
    enriched.loc[gaps!=1,["Croissance activité (%)","Croissance RN (%)"]]=float('nan')
    enriched["Marge nette (%)"]=enriched["Résultat net"]/enriched[metric].replace(0,float('nan'))*100
    st.dataframe(enriched,hide_index=True,use_container_width=True)
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
        st.caption("CSV séparé par ; ou , avec colonnes Année, Résultat net, Chiffre d'affaires (ou PNB), montants en millions FCFA.")
        uploaded=st.file_uploader("Historique financier CSV",type=["csv"],key="dashboard_csv")
        if uploaded:
            try:
                raw=uploaded.getvalue()
                df=pd.read_csv(io.BytesIO(raw),sep=None,engine="python",encoding="utf-8-sig")
                render_history(df,f"Fichier importé : {uploaded.name}")
            except Exception as exc:st.error(f"Historique non exploitable : {exc}")
