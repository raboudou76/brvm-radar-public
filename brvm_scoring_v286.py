"""V2.8.6 preliminary score; incomplete data must not be misrepresented as a /100 score."""
def preliminary_score(roe=None, net_growth=None, per=None, pbr=None, equity_growth=None):
    # Transparent thresholds are provisional and require sector calibration.
    components={
        'Rentabilité ROE':(roe,30,lambda x: 30 if x>=20 else 22 if x>=12 else 12 if x>=6 else 0),
        'Croissance résultat net':(net_growth,25,lambda x:25 if x>=15 else 18 if x>=5 else 10 if x>=0 else 0),
        'Valorisation PER':(per,20,lambda x:20 if 0<x<=10 else 14 if x<=15 else 7 if x<=25 else 0),
        'Valorisation PBR':(pbr,5,lambda x:5 if 0<x<=1.5 else 3 if x<=3 else 0),
        'Evolution capitaux propres':(equity_growth,20,lambda x:20 if x>=10 else 13 if x>=0 else 0),
    }
    details=[];earned=0;covered=0
    for name,(value,weight,fn) in components.items():
        pts=fn(float(value)) if value is not None else None
        if pts is not None:earned+=pts;covered+=weight
        details.append({'Dimension':name,'Points':pts,'Maximum':weight,'Donnée disponible':value is not None})
    return {'points_observed':earned,'maximum_observed':covered,'coverage_pct':covered,'score_100':earned if covered==100 else None,'details':details,'status':'COMPLET' if covered==100 else 'INCOMPLET'}
