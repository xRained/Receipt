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


def remember_from_record(c,body):
    """Learn only explicitly supplied proprietor/trading-name pairs on save."""
    name=str(body.get('company','')).strip()
    business=str(body.get('business_name','')).strip()
    if not business or not re.search(r'\s*-\s*prop(?:rietor)?\.?$',name,re.I):return False
    proprietor=re.sub(r'\s*-\s*prop(?:rietor)?\.?$','',name,flags=re.I).strip()
    old=c.execute('SELECT business_name FROM supplier_profiles WHERE name=?',(name,)).fetchone()
    if old and old['business_name'] and norm(old['business_name'])!=norm(business):
        raise ValueError('This proprietor already has a different company mapping. Review the supplier master before changing it.')
    c.execute('INSERT OR IGNORE INTO suppliers VALUES(?,?,?)',(name,str(body.get('tin','')),str(body.get('address',''))))
    c.execute('INSERT INTO supplier_profiles VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET business_name=excluded.business_name,proprietor=excluded.proprietor',(name,business,proprietor))
    return True


def learn_from_supplier_tins(c):
    """Link proprietor/trading-name masters only when a TIN has one business."""
    from matching import tin
    groups={}
    for row in c.execute('SELECT * FROM suppliers'):
        key=tin(row['tin'])
        if key:groups.setdefault(key,[]).append(dict(row))
    count=0
    for rows in groups.values():
        businesses={norm(r['name']):r['name'] for r in rows if not re.search(r'\bprop(?:rietor)?\.?$',r['name'],re.I)}
        if len(businesses)!=1:continue
        business=next(iter(businesses.values()))
        for row in rows:
            if not re.search(r'\s*-\s*prop(?:rietor)?\.?$',row['name'],re.I):continue
            old=c.execute('SELECT business_name FROM supplier_profiles WHERE name=?',(row['name'],)).fetchone()
            if old and old['business_name']:continue
            proprietor=re.sub(r'\s*-\s*prop(?:rietor)?\.?$','',row['name'],flags=re.I).strip()
            c.execute('INSERT INTO supplier_profiles VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET business_name=excluded.business_name,proprietor=excluded.proprietor',(row['name'],business,proprietor));count+=1
    return count
