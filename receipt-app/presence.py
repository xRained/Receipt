"""Step one: identify online material receipts already listed in Cash Voucher.

This checks document presence, not settlement balances or aggregate totals.
"""
import io
from difflib import SequenceMatcher
from flask import jsonify,request,send_file
import openpyxl
from matching import norm,receipt_numbers,tin


def online_material(row):
    return row['kind']=='payment' and row.get('collection')=='Material Expense' and norm(row.get('method')) in {'onlinepayment','bank','banktransfer','instapay','pesonet'}


def same_identity(p,r):
    return bool((tin(p.get('tin')) and tin(p.get('tin'))==tin(r.get('tin'))) or (norm(p.get('company')) and norm(p.get('company'))==norm(r.get('company'))))


def compare(payments,vouchers,account='CS-0001',confirmed=(),dismissed=()):
    confirmed=set(confirmed);dismissed=set(dismissed)
    selected=[r for r in vouchers if not account or r.get('code')==account or norm(r.get('account'))==norm(account)]
    selected_ids={r['id'] for r in selected}
    result=[]
    for p in payments:
        candidates=[];outside=[];pn=receipt_numbers(p)
        for r in vouchers:
            pair=(p['id'],r['id'])
            if pair in dismissed:continue
            exact=bool(pn & receipt_numbers(r));manual=pair in confirmed
            identity=same_identity(p,r)
            similarity=0 if exact or manual or identity else SequenceMatcher(None,norm(p.get('company')),norm(r.get('company'))).ratio()
            amount_delta=round(float(r.get('settlement_amount',r['amount']))-float(p['amount']),2)
            amount_close=abs(amount_delta)<=1 or abs(float(r['amount'])-float(p['amount']))<=1
            if not (exact or manual or identity or (similarity>=.65 and amount_close)):continue
            reasons=[]
            if manual:reasons.append('Manually confirmed same receipt')
            if exact:reasons.append('S.I.# already listed in Cash Voucher')
            if identity:reasons.append('Supplier name or TIN matches')
            if not identity:reasons.append('Supplier identity needs review')
            if tin(p.get('tin')) and tin(r.get('tin')) and tin(p.get('tin'))!=tin(r.get('tin')):reasons.append('TIN differs')
            if pn and receipt_numbers(r) and not exact:reasons.append('S.I.# differs from Material Expense')
            if amount_delta:reasons.append('Payment and recorded amount paid differ; presence is checked separately')
            candidate=dict(receipt=r,exact_si=exact,confirmed=manual,amount_difference=amount_delta,
                           reasons=reasons,score=(1000 if manual else 0)+(100 if exact else 0)+(20 if identity else 0)+(10 if amount_close else 0))
            if r['id'] in selected_ids:candidates.append(candidate)
            elif exact or manual:outside.append(candidate)
        candidates.sort(key=lambda c:-c['score']);outside.sort(key=lambda c:-c['score'])
        exact=[c for c in candidates if c['exact_si'] or c['confirmed']]
        status='found' if exact else 'other_account' if outside else 'review' if candidates else 'not_found'
        result.append(dict(payment=p,status=status,candidates=candidates[:12],other_accounts=outside,
                           explanation='S.I.# is present; verify identity notes where flagged.' if exact else 'S.I.# exists under another account.' if outside else 'Possible receipt; confirm before treating it as present.' if candidates else 'No receipt candidate found in the selected Cash Voucher account; this is not proof that no receipt exists.'))
    return result,selected


def install(app,db,records):
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS presence_links(payment TEXT REFERENCES records(id),receipt TEXT REFERENCES records(id),PRIMARY KEY(payment,receipt));
        CREATE TABLE IF NOT EXISTS presence_dismissals(payment TEXT REFERENCES records(id),receipt TEXT REFERENCES records(id),PRIMARY KEY(payment,receipt));''')

    def data(account):
        with db() as c:
            allrows=records(c)
            ps=[r for r in allrows if online_material(r)]
            rs=[r for r in allrows if r['kind']=='receipt' and r.get('collection')=='September Cash Voucher']
            confirmed=[tuple(r) for r in c.execute('SELECT payment,receipt FROM presence_links')]
            dismissed=[tuple(r) for r in c.execute('SELECT payment,receipt FROM presence_dismissals')]
        rows,selected=compare(ps,rs,account,confirmed,dismissed)
        choices=sorted({(r.get('code',''),r.get('account','')) for r in rs},key=lambda a:a[1])
        return dict(rows=rows,vouchers=selected,accounts=[dict(code=k,title=v) for k,v in choices],
                    account=account,month='2026-09',source_payments='2026 EXPENSES 3rd Quarter.xlsx / Material Expense',
                    source_receipts='9 SEPTEMBER 2026.xlsx / September Cash Voucher',
                    counts={status:sum(r['status']==status for r in rows) for status in ['found','review','not_found','other_account']})

    @app.get('/api/materials-presence')
    def material_presence():return jsonify(data(request.args.get('account','CS-0001')))

    @app.post('/api/materials-presence/decision')
    def decision():
        b=request.get_json() or {}
        with db() as c:
            rows={r['id']:r for r in records(c)};p=rows.get(b.get('payment'));r=rows.get(b.get('receipt'))
            if not p or not r or not online_material(p) or r.get('collection')!='September Cash Voucher':return jsonify(error='Choose an online material payment and a Cash Voucher receipt'),400
            action=b.get('action')
            if action not in ['confirm','dismiss','undo']:return jsonify(error='Choose confirm, dismiss or undo'),400
            for table in ['presence_links','presence_dismissals']:c.execute('DELETE FROM '+table+' WHERE payment=? AND receipt=?',(p['id'],r['id']))
            if action!='undo':c.execute('INSERT INTO '+('presence_links' if action=='confirm' else 'presence_dismissals')+' VALUES(?,?)',(p['id'],r['id']))
        return jsonify(ok=True)

    @app.get('/api/materials-presence/export')
    def export_presence():
        d=data(request.args.get('account','CS-0001'));w=openpyxl.Workbook();w.remove(w.active)
        def safe(value):return "'"+value if isinstance(value,str) and value.startswith(('=','+','-','@')) else value
        for status,title in [('not_found','No candidate found'),('review','Needs review'),('found','SI already listed'),('other_account','SI in another account')]:
            s=w.create_sheet(title);s.append(['Payment date','Payee','Reference','Payment SI','Payment amount','Status','Voucher SI','Voucher supplier','Voucher row','Account','Evidence / warning'])
            for row in d['rows']:
                if row['status']!=status:continue
                p=row['payment'];matches=row['candidates'] or row['other_accounts'] or [None]
                for match in matches:
                    r=match['receipt'] if match else {}
                    values=[p.get('date'),p['company'],p.get('reference'),p.get('receipt_no'),p['amount'],status,r.get('receipt_no'),r.get('company'),r.get('source_row'),r.get('account'),'; '.join(match['reasons']) if match else row['explanation']]
                    s.append(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in values])
            s.freeze_panes='A2';s.auto_filter.ref=s.dimensions
        s=w.create_sheet('Selected Cash Voucher');s.append(['Source row','Date','Supplier','SI','Account code','Account','Gross','Recorded amount paid'])
        for r in d['vouchers']:s.append([safe(v) for v in [r.get('source_row'),r.get('date'),r['company'],r.get('receipt_no'),r.get('code'),r.get('account'),r['amount'],r['settlement_amount']]])
        s=w.create_sheet('Read me');s.append(['Scope','September online Material Expense vs September Cash Voucher; receipt dates are not restricted.']);s.append(['Purpose','Find receipts already listed or not yet found. No aggregate total reconciliation.']);s.append(['Caution','An identical SI number with differing supplier/TIN needs identity review; it is not proof of the same transaction.'])
        buf=io.BytesIO();w.save(buf);buf.seek(0)
        return send_file(buf,download_name='September online materials - receipt checklist.xlsx',as_attachment=True)
