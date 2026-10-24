"""Step one: identify online material receipts already listed in Cash Voucher.

This checks document presence, not settlement balances or aggregate totals.
"""
import io
from difflib import SequenceMatcher
from flask import jsonify,request,send_file
import openpyxl
from matching import norm,receipt_numbers,tin
from materials import material_payment,cash_voucher


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
            amount_delta=round(float(r.get('settlement_amount',r['amount']))-float(p['amount']),2)
            amount_close=abs(amount_delta)<=1 or abs(float(r['amount'])-float(p['amount']))<=1
            similarity=SequenceMatcher(None,norm(p.get('company')),norm(r.get('company'))).ratio() if amount_close and not (exact or manual or identity) else 0
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
        if 'match_kind' not in [r['name'] for r in c.execute('PRAGMA table_info(presence_links)')]:c.execute("ALTER TABLE presence_links ADD COLUMN match_kind TEXT NOT NULL DEFAULT 'manual'")

    def data(account,month=None,method=None,payment_month=None):
        with db() as c:
            allrows=records(c)
            scope=c.execute("SELECT value FROM workspace_settings WHERE key='scope_month'").fetchone()
            month=month or (scope['value'] if scope else '2026-09')
            ps=[r for r in allrows if material_payment(r) and (not payment_month or r.get('date','').startswith(payment_month)) and (not method or method=='all' or (online_material(r) if method=='online' else norm(r.get('method'))==norm(method)))]
            rs=[r for r in allrows if cash_voucher(r) and (r.get('receipt_month') or month)==month]
            confirmed=[tuple(r) for r in c.execute('SELECT payment,receipt FROM presence_links UNION SELECT payment,receipt FROM allocations')]
            automatic={(r['payment'],r['receipt']) for r in c.execute("SELECT payment,receipt FROM presence_links WHERE match_kind='automatic'")}
            dismissed=[tuple(r) for r in c.execute('SELECT payment,receipt FROM presence_dismissals')]
        rows,selected=compare(ps,rs,account,confirmed,dismissed)
        for row in rows:
            for candidate in row['candidates']+row['other_accounts']:
                if (row['payment']['id'],candidate['receipt']['id']) in automatic:
                    candidate['confirmed']=False;candidate['automatic']=True
                    candidate['reasons']=[reason for reason in candidate['reasons'] if reason!='Manually confirmed same receipt']
                    candidate['reasons'].insert(0,'Automatically confirmed: unique company/TIN and exact company amount; S.I.# filled from receipt')
        for row in rows:
            row['payment']['matched_receipt_numbers']=', '.join(dict.fromkeys(c['receipt'].get('receipt_no','') for c in row['candidates']+row['other_accounts'] if c.get('automatic') or c.get('confirmed')))
        choices=sorted({(r.get('code',''),r.get('account','')) for r in rs},key=lambda a:a[1])
        if not any(code=='CS-0001' for code,title in choices):choices.insert(0,('CS-0001','Materials'))
        return dict(rows=rows,vouchers=selected,accounts=[dict(code=k,title=v) for k,v in choices],
                    account=account,month=month,source_payments='Material Expense - all payment modes',
                    source_receipts=month+' Cash Voucher collection',
                    counts={status:sum(r['status']==status for r in rows) for status in ['found','review','not_found','other_account']})

    @app.get('/api/materials-presence')
    def material_presence():return jsonify(data(request.args.get('account','CS-0001'),request.args.get('month'),request.args.get('method'),request.args.get('payment_month')))

    @app.post('/api/materials-presence/decision')
    def decision():
        b=request.get_json() or {}
        with db() as c:
            rows={r['id']:r for r in records(c)};p=rows.get(b.get('payment'));r=rows.get(b.get('receipt'))
            if not p or not r or not material_payment(p) or not cash_voucher(r):return jsonify(error='Choose a Material Expense payment and a Cash Voucher receipt'),400
            action=b.get('action')
            if action not in ['confirm','dismiss','undo']:return jsonify(error='Choose confirm, dismiss or undo'),400
            for table in ['presence_links','presence_dismissals']:c.execute('DELETE FROM '+table+' WHERE payment=? AND receipt=?',(p['id'],r['id']))
            if action!='undo':c.execute('INSERT INTO '+('presence_links' if action=='confirm' else 'presence_dismissals')+'(payment,receipt) VALUES(?,?)',(p['id'],r['id']))
        return jsonify(ok=True)

    @app.get('/api/materials-presence/export')
    def export_presence():
        d=data(request.args.get('account','CS-0001'),request.args.get('month'),request.args.get('method'),request.args.get('payment_month'));w=openpyxl.Workbook();w.remove(w.active)
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
        s=w.create_sheet('Read me');s.append(['Scope','Material Expense vs '+d['month']+' Cash Voucher collection; receipt dates are not restricted.']);s.append(['Purpose','Find receipts already listed or not yet found. No aggregate total reconciliation.']);s.append(['Caution','An identical SI number with differing supplier/TIN needs identity review; it is not proof of the same transaction.'])
        buf=io.BytesIO();w.save(buf);buf.seek(0)
        return send_file(buf,download_name=d['month']+' materials - receipt checklist.xlsx',as_attachment=True)
