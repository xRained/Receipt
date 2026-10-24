"""Working modules corresponding to all fourteen original workbook sheets."""
from supplier_profiles import suppliers as supplier_rows
import json
import re
from collections import defaultdict
from flask import jsonify, request
from matching import norm
from reports import collection, money


DEFINITIONS={
 'materials':('Material Expense','quarterly','payment'),
 'costs':('Cost of Sales Expense','quarterly','payment'),
 'operating':('Operating Expense','quarterly','payment'),
 'allowances':('COS_Allowance','quarterly','payment'),
 'cash-controls':('GCashCheck','quarterly','controls'),
 'daily':('Expense Summary','quarterly','daily'),
 'monthly':('SummaryMonth','quarterly','monthly'),
 'supplier-list':('Suppliers List','quarterly','suppliers'),
 'account-list':('Copy of Accounts','quarterly','accounts'),
 'cash-vouchers':('September Cash Voucher','monthly','receipt'),
 'cheque-vouchers':('September Check Voucher','monthly','receipt'),
 'non-receipt':('Non Receipt','monthly','receipt'),
 'suppliers':('Suppliers','monthly','suppliers'),
 'coa':('COA','monthly','accounts'),
}


def filter_module_rows(rows,kind,args):
    """Search displayed data without scanning OCR text or raw workbook evidence."""
    query=str(args.get('q','')).strip().lower()
    compact=norm(query)
    method=norm(args.get('method',''));code=args.get('code','');status=args.get('status','')
    start=args.get('from','');end=args.get('to','')
    try:
        low=float(args['min']) if args.get('min') else None
        high=float(args['max']) if args.get('max') else None
    except ValueError:raise ValueError('Enter valid minimum and maximum amounts')
    result=[]
    for row in rows:
        values=[str(v) for k,v in row.items() if isinstance(v,(str,int,float)) and k not in ['ocr_text','image','id','source']]
        if query and not any(query in v.lower() or (compact and compact in norm(v)) for v in values):continue
        if method and norm(row.get('method',row.get('kind','')))!=method:continue
        if code and row.get('code')!=code:continue
        day=str(row.get('date',row.get('day',row.get('period',''))))
        if start and day<start:continue
        if end and day>end:continue
        amount=row.get('amount',row.get('total'))
        if amount is not None:
            amount=float(amount)/(100 if kind=='controls' else 1)
        if low is not None and (amount is None or amount<low):continue
        if high is not None and (amount is None or amount>high):continue
        remaining=float(row.get('remaining',0));allocated=float(row.get('allocated',0))
        if status=='open' and remaining<=.005:continue
        if status=='closed' and remaining>.005:continue
        if status=='partial' and not (allocated>0 and remaining>.005):continue
        if status=='missing-si' and (row.get('receipt_no') or row.get('linked_receipt_numbers')):continue
        result.append(row)
    return result


def install(app,db,records,cents):
    @app.get('/api/modules')
    def module_list():
        return jsonify(modules=[dict(id=k,name=v[0],workbook=v[1],type=v[2]) for k,v in DEFINITIONS.items()])

    @app.get('/api/modules/<slug>')
    def module_data(slug):
        if slug not in DEFINITIONS:return jsonify(error='Unknown module'),404
        name,workbook,kind=DEFINITIONS[slug]
        month=request.args.get('month','')
        with db() as c:
            scope=c.execute("SELECT value FROM workspace_settings WHERE key='scope_month'").fetchone()
            scope=scope['value'] if scope else None
            rs=records(c)
            if kind=='suppliers':rows=supplier_rows(c)
            elif kind=='accounts':rows=[dict(r) for r in c.execute('SELECT * FROM accounts ORDER BY code')]
            elif kind=='controls':rows=[dict(r) for r in c.execute('SELECT * FROM controls ORDER BY day')]
            elif kind=='payment':rows=[r for r in rs if r['kind']=='payment' and collection(r)==name]
            elif kind=='receipt':
                def register(row):
                    name=row.get('collection','').lower()
                    if name=='non receipt' or row.get('treatment')=='no_receipt':return 'non-receipt'
                    if 'cash voucher' in name:return 'cash-vouchers'
                    if 'check v' in name or 'cheque v' in name:return 'cheque-vouchers'
                    return 'cheque-vouchers' if row.get('method','').lower() in ['cheque','check'] else 'cash-vouchers'
                rows=[r for r in rs if r['kind']=='receipt' and register(r)==slug]
            else:
                groups=defaultdict(lambda:dict(materials=0,costs=0,operating=0,allowances=0,principal=0,fees=0,total=0,cash=0,gcash=0,cheque=0,bank=0,personal=0))
                for r in rs:
                    if r['kind']!='payment':continue
                    key=r.get('date','') or 'Date missing'
                    if kind=='monthly' and key!='Date missing':key=key[:7]
                    g=groups[key];g['personal']+=cents(r.get('personal_amount'));principal=cents(r['amount']);fee=cents(r.get('fee'));total=principal+fee
                    if r.get('personal') or r.get('treatment')=='personal':g['personal']+=total;continue
                    category=next(k for k in ['materials','costs','operating','allowances'] if DEFINITIONS[k][0]==collection(r))
                    g[category]+=total;g['principal']+=principal;g['fees']+=fee;g['total']+=total
                    method=r.get('method','').lower();g['gcash' if method=='gcash' else 'cash' if method=='cash' else 'cheque' if method in ['cheque','check'] else 'bank']+=total
                rows=[dict(period=key,**{k:v/100 for k,v in g.items()},basis='Payment detail; control totals not added') for key,g in sorted(groups.items())]
                if kind=='monthly' and not scope:
                    import calendar
                    template=c.execute("SELECT snapshot FROM templates WHERE kind='quarterly'").fetchone()
                    if template:
                        snapshot=json.loads(template['snapshot'])
                        for sheet in snapshot['sheets']:
                            if sheet['name']!='SummaryMonth':continue
                            for source in sheet['rows']:
                                v=source['values'];label=v.get('A')
                                if label not in list(calendar.month_name)[1:]:continue
                                year='2026'
                                period=f'{year}-{list(calendar.month_name).index(label):02d}'
                                if period in groups:continue
                                mapping={'materials':'B','costs':'C','operating':'D','allowances':'E','cash':'F','cheque':'G','gcash':'H','total':'I'}
                                historic={k:money(v.get(col)) if isinstance(v.get(col),(int,float)) else 0 for k,col in mapping.items()}
                                rows.append(dict(period=period,**historic,bank=None,personal=None,basis='Historical source snapshot; supporting detail not supplied'))
                        rows.sort(key=lambda r:r['period'])
        if month and kind in ['payment','receipt','controls','daily','monthly']:
            rows=[r for r in rows if (r.get('receipt_month')==month if kind=='receipt' else str(r.get('date',r.get('day',r.get('period','')))).startswith(month))]
        total_rows=len(rows)
        try:rows=filter_module_rows(rows,kind,request.args)
        except ValueError as e:return jsonify(error=str(e)),400
        return jsonify(id=slug,name=('Cash Voucher' if slug=='cash-vouchers' else 'Check Voucher' if slug=='cheque-vouchers' else name),workbook=workbook,type=kind,rows=rows,total_rows=total_rows,
                       note='Supplier and COA modules share one master across both workbooks. Historical transaction details are preserved when a master is edited. Summaries derive from payment detail; cash-control figures are separate evidence.')

    @app.post('/api/master/supplier')
    def save_supplier():
        b=request.get_json() or {};name=str(b.get('name','')).strip();original=str(b.get('original','')).strip()
        if not name:return jsonify(error='Supplier name is required'),400
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if original and not c.execute('SELECT 1 FROM suppliers WHERE name=?',(original,)).fetchone():return jsonify(error='Supplier no longer exists'),409
            others=c.execute('SELECT name FROM suppliers WHERE name<>?',(original,)).fetchall()
            if any(norm(r['name'])==norm(name) for r in others):return jsonify(error='This supplier already exists; edit the existing master'),409
            if original:c.execute('DELETE FROM suppliers WHERE name=?',(original,))
            c.execute('INSERT INTO suppliers VALUES(?,?,?)',(name,str(b.get('tin','')).strip(),str(b.get('address','')).strip()))
            if original and original!=name:c.execute('UPDATE supplier_profiles SET name=? WHERE name=?',(name,original))
            if 'business_name' in b or 'proprietor' in b:
                c.execute('INSERT INTO supplier_profiles VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET business_name=excluded.business_name,proprietor=excluded.proprietor',(name,str(b.get('business_name','')).strip(),str(b.get('proprietor','')).strip()))
        return jsonify(ok=True)

    @app.post('/api/master/account')
    def save_account():
        b=request.get_json() or {};code=str(b.get('code','')).strip().upper();title=str(b.get('title','')).strip()
        if not re.fullmatch(r'[A-Z]+-\d{4}',code) or not title:return jsonify(error='Enter an account code such as CS-0001 and an account title'),400
        with db() as c:
            exists=c.execute('SELECT 1 FROM accounts WHERE code=?',(code,)).fetchone()
            if exists and not b.get('editing'):return jsonify(error='Account code already exists; edit it instead'),409
            c.execute('INSERT INTO accounts VALUES(?,?) ON CONFLICT(code) DO UPDATE SET title=excluded.title',(code,title))
        return jsonify(ok=True)
