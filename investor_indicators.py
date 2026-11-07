"""Investor indicators; input values are explicitly sourced/validated by the user."""
import math

def compute_indicators(price=None, shares=None, earnings_ttm=None, equity=None,
                       dividend_gross=None, dividend_net=None, earnings_annual=None,
                       earnings_previous=None, equity_previous=None):
    def positive(x): return x is not None and math.isfinite(float(x)) and float(x)>0
    def finite(x): return x is not None and math.isfinite(float(x))
    if not positive(shares): raise ValueError('Le nombre d’actions doit être positif.')
    n=float(shares)
    out={}
    out['BPA TTM']=float(earnings_ttm)/n if finite(earnings_ttm) else None
    out['PER TTM']=float(price)/out['BPA TTM'] if positive(price) and positive(out['BPA TTM']) else None
    out['VMC par action']=float(equity)/n if finite(equity) else None
    out['PBR']=float(price)/out['VMC par action'] if positive(price) and positive(out['VMC par action']) else None
    out['Rendement dividende brut (%)']=100*float(dividend_gross)/float(price) if positive(price) and finite(dividend_gross) and float(dividend_gross)>=0 else None
    out['Rendement dividende net (%)']=100*float(dividend_net)/float(price) if positive(price) and finite(dividend_net) and float(dividend_net)>=0 else None
    out['Taux de distribution (%)']=100*float(dividend_gross)*n/float(earnings_annual) if finite(dividend_gross) and positive(earnings_annual) else None
    out['ROE (%)']=100*float(earnings_annual)/((float(equity)+float(equity_previous))/2) if finite(earnings_annual) and positive(equity) and positive(equity_previous) else None
    out['Croissance bénéfice (%)']=100*(float(earnings_annual)/float(earnings_previous)-1) if finite(earnings_annual) and positive(earnings_previous) else None
    return out
