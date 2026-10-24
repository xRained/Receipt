"""Remember proprietor and trading names without rewriting source records."""
import re
import json
from matching import norm

def suppliers(c):
    rows=[dict(r) for r in c.execute("SELECT s.*,COALESCE(p.business_name,'') AS business_name,COALESCE(p.proprietor,'') AS proprietor FROM suppliers s LEFT JOIN supplier_profiles p ON p.name=s.name ORDER BY s.name")]
    aliases={}
    for link in c.execute('SELECT alias,legal_name FROM supplier_name_links'):aliases.setdefault(norm(link['legal_name']),[]).append(link['alias'])
    for row in rows:
        row['known_payees']=', '.join(aliases.get(norm(row['name']),[]))
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
    links={norm(r['alias']):r['legal_name'] for r in c.execute('SELECT alias,legal_name FROM supplier_name_links')}
    for row in rows:
        legal=links.get(norm(row.get('company')),row.get('company',''))
        row['supplier_key']=norm(legal)
        if norm(legal)!=norm(row.get('company')):row['legal_supplier']=legal
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


def learn_from_allocations(c):
    """Reuse established receipt links as payee aliases, not trading-name guesses."""
    from matching import tin,receipt_numbers
    candidates={}
    query="SELECT p.body AS payment,r.body AS receipt,COALESCE(m.reason,'') AS reason FROM allocations a JOIN records p ON p.id=a.payment JOIN records r ON r.id=a.receipt LEFT JOIN match_audit m ON m.payment=a.payment AND m.receipt=a.receipt"
    for row in c.execute(query):
        p,r=json.loads(row['payment']),json.loads(row['receipt'])
        owner=str(r.get('company','')).strip();payee=str(p.get('company','')).strip()
        if not payee or not re.search(r'\s*-\s*prop(?:rietor)?\.?$',owner,re.I):continue
        if norm(payee)==norm(owner):continue
        pt,rt=tin(p.get('tin')),tin(r.get('tin'))
        if pt and rt and pt!=rt:continue
        manual=any(word in row['reason'].lower() for word in ['manually confirmed','reviewed group'])
        if not (receipt_numbers(p)&receipt_numbers(r) or manual):continue
        candidates.setdefault(norm(payee),{}).setdefault(owner,payee)
    learned=0
    for key,owners in candidates.items():
        if len(owners)!=1:
            learned+=c.execute('DELETE FROM supplier_name_links WHERE alias=?',(key,)).rowcount
            continue
        owner,payee=next(iter(owners.items()))
        existing=c.execute('SELECT legal_name FROM supplier_name_links WHERE alias=?',(key,)).fetchone()
        if existing:continue
        c.execute('INSERT INTO supplier_name_links VALUES(?,?,?)',(key,owner,'Confirmed allocation with shared S.I.# or manual confirmation'));learned+=1
    return learned
