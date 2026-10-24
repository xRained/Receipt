"""Local OCR text interpretation and duplicate identification, without guessing tax."""
import re
from datetime import datetime
from matching import norm, number, tin, receipt_numbers, same_supplier


def extract(text, mode='auto', suppliers=(), history=()):
    text=str(text or '').replace('\r','')
    payment=bool(re.search(r'gcash|instapay|pesonet|sent to|transfer successful|transaction successful',text,re.I))
    kind=('payment' if payment else 'receipt') if mode=='auto' else mode
    if kind not in ('payment','receipt'):raise ValueError('Choose payment, receipt or automatic detection')
    draft=dict(kind=kind,date='',company='',reference='',method='GCash' if re.search('gcash',text,re.I) else 'Bank' if payment else 'Cash',
               receipt_no='',tin='',address='',amount='',fee=0,withholding=0,remarks='',code='',account='',project='',category='',treatment='business')
    if kind=='payment':
        draft['method']='GCash' if re.search(r'gcash',text,re.I) else 'Cheque' if re.search(r'\b(?:cheque|check)\s*(?:no\.?|number|#|payment)',text,re.I) else 'Cash' if re.search(r'\bcash\s+(?:payment|paid)',text,re.I) else 'Online Payment'
    def find(field,patterns):
        for pattern in patterns:
            match=re.search(pattern,text,re.I|re.M)
            if match:
                draft[field]=match.group(1).strip();return
    find('reference',[r'(?:reference|ref\.?|transaction)(?:\s*(?:number|no\.?|id|#))?\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{5,})',r'(?:cheque|check)\s*(?:no\.?|number|#)\s*[:#]?\s*([A-Z0-9-]{3,})'])
    find('receipt_no',[r'(?:sales\s+invoice|service\s+invoice|invoice|receipt|S\.?I\.?)\s*(?:no\.?|number|#)\s*[:#]?\s*([A-Z0-9-]+)'])
    find('tin',[r'\b(\d{3}[- ]\d{3}[- ]\d{3}(?:[- ]\d{3})?)\b'])
    amount=r'(?:PHP|P|₱)?\s*([0-9][0-9,]*(?:\.\d{2})?)(?![\d.])'
    patterns=([r'^\s*amount\s*(?:sent|transferred)?\s*[:\n]?\s*'+amount,r'^\s*(?:PHP|₱)\s*([0-9][0-9,]*\.\d{2})\s*$'] if kind=='payment' else [r'(?:grand\s+total|total\s+(?:amount|sales)|amount\s+due)\s*[:\n]?\s*'+amount])
    find('amount',patterns+[r'^\s*total\s*[:\n]?\s*'+amount])
    if draft['amount']:draft['amount']=draft['amount'].replace(',','')
    for field,label in [('fee',r'(?:transfer\s+fee|service\s+(?:fee|charge)|fee)'),('withholding',r'(?:withholding(?:\s+tax)?|EWT)')]:
        find(field,[label+r'\s*[:\n]?\s*'+amount])
        if isinstance(draft[field],str):draft[field]=draft[field].replace(',','')
    match=re.search(r'\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b',text)
    if match:
        try:draft['date']=datetime(*map(int,match.groups())).date().isoformat()
        except ValueError:pass
    else:
        match=re.search(r'\b([A-Za-z]{3,9}\s+\d{1,2},?\s+20\d{2})\b',text)
        if match:
            for fmt in ['%b %d %Y','%B %d %Y']:
                try:draft['date']=datetime.strptime(match.group(1).replace(',',''),fmt).date().isoformat();break
                except ValueError:pass
    find('company',[r'(?:sent\s+to|paid\s+to|recipient|payee|company)\s*[:\n]\s*([^\n]+)'])
    candidates=[]
    for supplier in suppliers:
        name=norm(supplier['name'])
        if (name and len(name)>5 and name in norm(text)) or (tin(draft['tin']) and tin(draft['tin'])==tin(supplier.get('tin'))):candidates.append(supplier)
    by_name={norm(s['name']):s for s in candidates}
    if len(by_name)==1:
        supplier=next(iter(by_name.values()))
        draft.update(company=supplier['name'],tin=draft['tin'] or supplier.get('tin',''),address=supplier.get('address',''))
    elif draft['company']:
        supplier=next((s for s in suppliers if norm(s['name'])==norm(draft['company'])),None)
        if supplier:draft.update(tin=draft['tin'] or supplier.get('tin',''),address=supplier.get('address',''))
    codes={r['code'] for r in history if r.get('code') and draft['company'] and same_supplier(draft,r)}
    if len(codes)==1:
        draft['code']=next(iter(codes))
        draft['account']=next((r.get('account','') for r in history if r.get('code')==draft['code']), '')
    for regex,category in [(r'auto\s?sweep','Autosweep RFID'),(r'easy\s?trip','Easytrip'),(r'grab','Grab')]:
        if re.search(regex,text,re.I):draft['category']=category
    required=['company','amount','date']+(['reference'] if kind=='payment' and draft['method']!='Cash' else ['receipt_no'])
    warnings=[f'Missing {field.replace("_"," ")}' for field in required if not draft.get(field)]
    if re.search(r'\b\d{1,2}/\d{1,2}/20\d{2}\b',text) and not draft['date']:warnings.append('Numeric date is ambiguous; choose the date explicitly')
    if len(by_name)>1:warnings.append('Multiple supplier names share this evidence; verify legal supplier')
    warnings.append('Compare extracted digits with the document before saving')
    return draft,warnings


def duplicates(draft, rows):
    matches=[]
    for r in rows:
        if r['kind']!=draft['kind']:continue
        ref=norm(draft.get('reference'))
        same_ref=bool(ref and ref==norm(r.get('reference')))
        same_receipt=bool(receipt_numbers(draft)&receipt_numbers(r) and same_supplier(draft,r))
        if same_ref or same_receipt:
            exact=False
            try:exact=round(float(draft.get('amount') or 0),2)==round(float(r['amount']),2)
            except (ValueError,TypeError):pass
            matches.append(dict(id=r['id'],company=r['company'],amount=r['amount'],date=r.get('date',''),
                                receipt_no=r.get('receipt_no',''),reference=r.get('reference',''),
                                reason='Same payment reference' if same_ref else 'Same supplier and receipt number',exact_amount=exact))
    return matches
