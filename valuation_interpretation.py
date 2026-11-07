"""Interprétation pédagogique des ratios selon la grille fournie par l'utilisateur.
Seuils paramétrables, NON validés comme références statistiques BRVM.
"""
import math

DEFAULT_THRESHOLDS = {"PER": (9.0, 11.0), "PBR": (0.7, 1.0), "RVC": (7.0, 10.0), "Cours / VMC": (0.7, 1.0)}

def _positive_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None

def interpret_valuation(indicators, price, thresholds=None):
    """Return 4 consistent readings; no automatic buy/sell recommendation."""
    limits = thresholds or DEFAULT_THRESHOLDS
    per = _positive_number(indicators.get("PER TTM"))
    pbr = _positive_number(indicators.get("PBR"))
    vmc = _positive_number(indicators.get("VMC par action"))
    quote = _positive_number(price)
    metrics = {"PER": per, "PBR": pbr, "RVC": per * pbr if per and pbr else None,
               "Cours / VMC": quote / vmc if quote and vmc else None}
    output = []
    for name, value in metrics.items():
        low, high = limits[name]
        if not 0 < low < high:
            raise ValueError("Les bornes doivent être positives et strictement croissantes : " + name)
        if value is None:
            status = "Non interprétable"
        elif value < low:
            status = "Sous-évalué selon la grille"
        elif value <= high:
            status = "Zone de juste prix selon la grille"
        else:
            status = "Surévalué selon la grille"
        output.append({"Indicateur": name, "Valeur": round(value, 3) if value is not None else None,
                       "Borne basse": low, "Borne haute": high, "Lecture indicative": status})
    return output
