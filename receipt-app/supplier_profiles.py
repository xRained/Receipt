"""Remember proprietor and trading names without rewriting source records."""
import re
from matching import norm

def suppliers(c):
    rows=[dict(r) for r in c.execute("SELECT s.*,COALESCE(p.business_name,'') AS business_name,COALESCE(p.proprietor,'') AS proprietor FROM suppliers s LEFT JOIN supplier_profiles p ON p.name=s.name ORDER BY s.name")]
    for row in rows:
        if not row['proprietor'] and re.search(r'\s*-?\s*prop(?:rietor)?\.?$',row['name'],re.I):row['proprietor']=re.sub(r'\s*-?\s*prop(?:rietor)?\.?$','',row['name'],flags=re.I).strip()
    return rows

def annotate(rows,c):
    profiles=[dict(r) for r in c.execute('SELECT * FROM supplier_profiles')]
    lookup={}
    for p in profiles:
        for name in [p['name'],p['business_name']]:
            if norm(name):lookup.setdefault(norm(name),[]).append(p)
    for row in rows:
        matches=lookup.get(norm(row.get('company')),[])
        businesses={norm(p['business_name']) for p in matches if p['business_name']}
        if len(businesses)==1:
            row['business_name']=matches[0]['business_name'];row['proprietor']=matches[0]['proprietor']
    return rows
