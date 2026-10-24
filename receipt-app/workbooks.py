"""Normalize workbook layout, including vertical merged voucher groups."""
import re
from openpyxl.utils.cell import range_boundaries
from openpyxl.utils.datetime import from_excel
from audit_workbooks import audit


def normalized_receipts(workbook):
    result=[]
    for sheet in workbook['sheets']:
        if 'Voucher' not in sheet['name']:continue
        rows={r['row']:r['values'] for r in sheet['rows']}
        header=next((n for n,v in rows.items() if 'S.I#' in v.values()),None)
        if header is None:continue
        columns={v:k for k,v in rows[header].items() if isinstance(v,str)}
        company_col=columns['PARTICULARS']
        groups={}
        for merged in sheet['merges']:
            left,top,right,bottom=range_boundaries(merged)
            if left==4 and bottom>top:groups[top]=bottom
        for n,values in rows.items():
            if n<=header or not values.get(company_col):continue
            amount=values.get(columns['AMOUNT'])
            if not isinstance(amount,(int,float)) or amount<=0:continue
            end=groups.get(n,n)
            parts=[rows.get(i,{}) for i in range(n,end+1)]
            gross=sum(float(v.get(columns['AMOUNT']) or 0) for v in parts)
            paid_col=columns.get('AMOUNT PAID',columns.get('CASH IN BANK'))
            paid=sum(float(v.get(paid_col) or 0) for v in parts)
            ewt=sum(float(v.get(columns['EXPANDED WITHHOLDING TAX']) or 0) for v in parts)
            numbers=[str(v[columns['S.I#']]) for v in parts if v.get(columns['S.I#']) not in (None,'','-')]
            personal=any(isinstance(value,str) and value.strip().lower()=='personal' for v in parts for value in v.values())
            result.append(dict(source=workbook['file']+' / '+sheet['name'],source_row=n,
                               amount=round(gross,2),settlement_amount=round(paid if paid_col else gross,2),
                               withholding=round(ewt,2),receipt_numbers=numbers,
                               source_rows=list(range(n,end+1)),personal=personal,
                               receipt_no=', '.join(numbers),
                               input_tax_goods=round(sum(float(v.get(columns.get('INPUT TAX - GOODS')) or 0) for v in parts),2),
                               input_tax_services=round(sum(float(v.get(columns.get('INPUT TAX - SERVICES',columns.get('INPUT TAX -  SERVICES'))) or 0) for v in parts),2)))
    return result


def account_entries(workbook):
    for sheet in workbook['sheets']:
        if sheet['name'] not in ['COA','Copy of Accounts']:continue
        for row in sheet['rows']:
            vals=list(row['values'].values())
            for i,v in enumerate(vals[:-1]):
                if isinstance(v,str) and re.fullmatch(r'[A-Z]+-\d{4}',v):yield v,str(vals[i+1])
