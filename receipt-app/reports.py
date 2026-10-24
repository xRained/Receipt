"""Generate all original workbook tabs using their column layouts and styles.

Source files are immutable. Spreadsheet XML is generated with cached formula
results, so exported totals are readable without Excel recalculation.
"""
import calendar
import copy
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from openpyxl.utils.datetime import to_excel
from openpyxl.utils.cell import get_column_letter

MAIN='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS={'m':MAIN}
ET.register_namespace('',MAIN)


def money(value):
    return int((Decimal(str(value or 0))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))/100


def serial(value):
    try:return to_excel(date.fromisoformat(str(value)[:10]))
    except (ValueError,TypeError):return ''


def cell(ref,value,style=None):
    attrs={'r':ref}
    if style:attrs['s']=str(style)
    c=ET.Element('{'+MAIN+'}c',attrs)
    if isinstance(value,tuple):
        formula,cached=value
        ET.SubElement(c,'{'+MAIN+'}f').text=formula
        ET.SubElement(c,'{'+MAIN+'}v').text=str(cached)
    elif isinstance(value,(int,float)):
        ET.SubElement(c,'{'+MAIN+'}v').text=str(value)
    else:
        c.set('t','inlineStr')
        ET.SubElement(ET.SubElement(c,'{'+MAIN+'}is'),'{'+MAIN+'}t').text=str(value or '')
    return c


def render_xml(original,header,body,merges=()):
    root=ET.fromstring(original)
    root.attrib.pop('{http://schemas.openxmlformats.org/markup-compatibility/2006}Ignorable',None)
    sd=root.find('m:sheetData',NS)
    oldrows=list(sd)
    styles={}
    for r in oldrows:
        if int(r.attrib['r'])>header:
            for c in r:
                styles.setdefault(re.sub(r'\d','',c.attrib['r']),c.attrib.get('s'))
            if len(styles)>12:break
    preserved=[copy.deepcopy(r) for r in oldrows if int(r.attrib['r'])<=header]
    sd.clear()
    for r in preserved:sd.append(r)
    maxcol=1
    for n,values in enumerate(body,header+1):
        r=ET.SubElement(sd,'{'+MAIN+'}row',{'r':str(n),'ht':'22','customHeight':'1'})
        for col,value in values.items():
            r.append(cell(f'{col}{n}',value,styles.get(col)))
            from openpyxl.utils.cell import column_index_from_string
            maxcol=max(maxcol,column_index_from_string(col))
    for tag in ['mergeCells','dataValidations','autoFilter','conditionalFormatting','extLst']:
        for element in list(root.findall('m:'+tag,NS)):root.remove(element)
    finalmerges=[]
    for r in ET.fromstring(original).findall('m:mergeCells/m:mergeCell',NS):
        nums=list(map(int,re.findall(r'\d+',r.attrib['ref'])))
        if nums and max(nums)<=header:finalmerges.append(r.attrib['ref'])
    finalmerges.extend(merges)
    if finalmerges:
        mc=ET.SubElement(root,'{'+MAIN+'}mergeCells',{'count':str(len(finalmerges))})
        for value in finalmerges:ET.SubElement(mc,'{'+MAIN+'}mergeCell',{'ref':value})
    dimension=root.find('m:dimension',NS)
    if dimension is not None:dimension.set('ref',f'A1:{get_column_letter(maxcol)}{header+len(body)}')
    order='sheetPr dimension sheetViews sheetFormatPr cols sheetData sheetCalcPr sheetProtection protectedRanges scenarios autoFilter sortState dataConsolidate customSheetViews mergeCells phoneticPr conditionalFormatting dataValidations hyperlinks printOptions pageMargins pageSetup headerFooter rowBreaks colBreaks customProperties cellWatches ignoredErrors smartTags drawing legacyDrawing legacyDrawingHF picture oleObjects controls webPublishItems tableParts extLst'.split()
    root[:]=sorted(list(root),key=lambda e:order.index(e.tag.split('}')[-1]) if e.tag.split('}')[-1] in order else len(order))
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def collection(r):
    existing=r.get('collection')
    if existing in ['Material Expense','Cost of Sales Expense','Operating Expense','COS_Allowance']:return existing
    code=r.get('code','')
    return 'COS_Allowance' if code=='CS-0008' else 'Material Expense' if code=='CS-0001' else 'Operating Expense' if code.startswith(('OE','PEOE')) else 'Cost of Sales Expense'


def build_workbook(template, snapshot, records, suppliers, accounts, controls, month, quarterly, scope_month=None):
    """Return workbook bytes and an accounting manifest for validation."""
    with zipfile.ZipFile(template) as z:
        files={n:z.read(n) for n in z.namelist()}
    wb=ET.fromstring(files['xl/workbook.xml'])
    rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(files['xl/_rels/workbook.xml.rels'])}
    paths={}
    import posixpath
    for s in wb.find('m:sheets',NS):
        rel=rels[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
        paths[s.attrib['name']]=rel.lstrip('/') if rel.startswith('/') else posixpath.normpath('xl/'+rel)
    # Remove obsolete print-area names; keep names unrelated to regenerated tabs.
    defined=wb.find('m:definedNames',NS)
    if defined is not None:wb.remove(defined)
    files['xl/workbook.xml']=ET.tostring(wb,encoding='utf-8',xml_declaration=True)
    year=int(month[:4]);quarter=(int(month[5:])-1)//3
    payments=[r for r in records if r['kind']=='payment' and (not r.get('date') or (r['date'].startswith(str(year)) and (int(r['date'][5:7])-1)//3==quarter))]
    if scope_month:
        payments=[r for r in payments if r.get('date','').startswith(scope_month)]
        controls=[r for r in controls if str(r.get('date','')).startswith(scope_month)]
    receipts=[r for r in records if r['kind']=='receipt' and (r.get('receipt_month')==month or (not r.get('receipt_month') and str(r.get('date','')).startswith(month)))]
    manifest={'month':month,'sheets':{},'payment_principal':money(sum(r['amount'] for r in payments)),
              'payment_fees':money(sum(float(r.get('fee',0) or 0) for r in payments)),
              'receipt_gross':money(sum(r['amount'] for r in receipts)),
              'receipt_net':money(sum(r['settlement_amount'] for r in receipts)),
              'notes':['Payment and receipt totals are separate evidence; never add them together.',
                       'Personal/mixed groups are shown and excluded from the business subtotal until reviewed.',
                       'Aggregate cash/GCash/cheque controls are compared separately, not added to payment detail.',
                       'Historical external workbook values are snapshots; external sources were not accessed.']}
    sheet_by_name={s['name']:s for s in snapshot['sheets']}
    for name,path in paths.items():
        rows=[];header=3 if name in ['Material Expense','Cost of Sales Expense','Operating Expense','COS_Allowance'] else 13 if 'Voucher' in name or name=='Non Receipt' else 4 if name=='GCashCheck' else 1
        merges=[]
        if name in ['Material Expense','Cost of Sales Expense','Operating Expense','COS_Allowance']:
            selected=sorted([r for r in payments if collection(r)==name],key=lambda r:r.get('date',''))
            for r in selected:
                n=header+len(rows)+1;amount=money(r['amount']);fee=money(r.get('fee',0));receipt=r.get('linked_receipt_numbers') or r.get('receipt_no','')
                if name=='Material Expense':
                    values=dict(A=serial(r.get('date')),B=r.get('method'),C=receipt,D=r.get('reference'),E=r['company'],F=r.get('remarks'),G=r.get('tin'),H=r.get('address'),I=r.get('project'),J=r.get('code'),K=r.get('account'),L=amount,M=fee,N=(f'L{n}+M{n}',money(amount+fee)))
                elif name=='COS_Allowance':values=dict(A=serial(r.get('date')),B=r.get('method'),C=r.get('reference'),D=r['company'],E=r.get('project'),F=r.get('code'),G=r.get('account'),H=amount,I=r.get('treatment','advance'),J=money(r.get('allocated')),K=money(r.get('returned')),L=money(r.get('remaining')))
                else:values=dict(A=serial(r.get('date')),B=r.get('method'),C=r.get('reference'),D=r['company'],E=r.get('remarks'),F=r.get('code'),G=r.get('account'),H=r.get('project'),I=amount,J=fee,K=(f'I{n}+J{n}',money(amount+fee)))
                rows.append(values)
            column='N' if name=='Material Expense' else 'H' if name=='COS_Allowance' else 'K'
            rows.append({'A':'TOTAL',''+column:(f'SUM({column}4:{column}{3+len(selected)})' if selected else '0',money(sum(r['amount']+float(r.get('fee',0) or 0)*(name!='COS_Allowance') for r in selected)))})
        elif 'Voucher' in name or name=='Non Receipt':
            selected=[r for r in receipts if (r.get('collection')=='Non Receipt' or r.get('treatment')=='no_receipt')==(name=='Non Receipt') and (name=='Non Receipt' or ('check' in str(r.get('method','')).lower() or 'cheque' in str(r.get('method','')).lower() or r.get('collection')=='September Check Voucher')==('Check' in name))]
            for r in selected:
                n=header+len(rows)+1
                if name=='Non Receipt':values=dict(A=serial(r.get('date')),B=r['company'],C=r.get('code'),D=r.get('account'),F=money(r['amount']))
                else:
                    check='Check' in name
                    values=dict(A=serial(r.get('date')),D=r['company'],M=r.get('receipt_no',''))
                    mapping=({'N':r.get('reference'),'O':r.get('tin'),'P':r.get('address'),'Q':r.get('code'),'R':r.get('account'),'S':r.get('tax_tag',''),'T':money(r['amount']),'U':money(r.get('input_tax_goods')),'V':money(r.get('input_tax_services')),'W':money(r.get('net_tax_base',r['amount']-float(r.get('input_tax_goods',0))-float(r.get('input_tax_services',0)))),'X':money(r.get('withholding')),'Y':money(r['settlement_amount']),'AB':'personal/mixed' if r.get('personal') else ''} if check else {'N':r.get('tin'),'O':r.get('address'),'P':r.get('code'),'Q':r.get('account'),'R':r.get('tax_tag',''),'S':money(r['amount']),'T':money(r.get('input_tax_goods')),'U':money(r.get('input_tax_services')),'V':money(r.get('net_tax_base',r['amount']-float(r.get('input_tax_goods',0))-float(r.get('input_tax_services',0)))),'W':money(r.get('withholding')),'X':money(r['settlement_amount']),'Y':'personal/mixed' if r.get('personal') else ''})
                    values.update(mapping);merges.extend([f'A{n}:C{n}',f'D{n}:L{n}'])
                rows.append(values)
            amount_col='F' if name=='Non Receipt' else 'Y' if 'Check' in name else 'X'
            end=header+len(rows)
            total=money(sum(r['settlement_amount'] for r in selected))
            rows.append({'A':'TOTAL RECORDED',amount_col:(f'SUM({amount_col}14:{amount_col}{end})' if selected else '0',total)})
            business=[(14+i,r) for i,r in enumerate(selected) if not r.get('personal') and r.get('treatment')!='personal']
            formula='+'.join(f'{amount_col}{n}' for n,r in business) or '0'
            rows.append({'A':'BUSINESS / NOT PERSONAL',amount_col:(formula,money(sum(r['settlement_amount'] for n,r in business)))})
            rows.append({'A':'PERSONAL OR MIXED: REVIEW',amount_col:money(sum(r['settlement_amount'] for r in selected if r.get('personal') or r.get('treatment')=='personal'))})
            rows.append({'A':'Grouped S.I# values retain all source receipt lines. Tax figures are recorded values, not an inferred tax rate.'})
        elif name in ['Suppliers','Suppliers List']:
            rows=[dict(A=s['name'],B=s.get('tin',''),C=s.get('address','')) for s in suppliers]
        elif name in ['COA','Copy of Accounts']:
            rows=[dict(B=a['code'],C=a['title']) if name=='COA' else dict(A=a['code'],B=a['title']) for a in accounts]
        elif name=='GCashCheck':
            cs=[c for c in controls if c.get('kind')=='cash'];gs=[c for c in controls if c.get('kind')=='gcash'];chs=[c for c in controls if c.get('kind')=='cheque']
            for i in range(max(len(cs),len(gs),len(chs),1)):
                values={}
                for items,dc,ac,nc in [(cs,'A','B',None),(gs,'D','E',None),(chs,'G','I','H')]:
                    if i<len(items):
                        item=items[i];values[dc]=serial(item.get('date'));values[ac]=item['amount']
                        if nc:values[nc]=item.get('company','')
                rows.append(values)
            rows.append({'A':'Control totals only. Compare with payment detail; do not add both as expenses.'})
        elif name in ['Expense Summary','SummaryMonth']:
            grouped=defaultdict(list)
            for r in payments:
                key=(r['date'] if name=='Expense Summary' else r['date'][:7]) if r.get('date') else 'Date missing'
                grouped[key].append(r)
            if name=='SummaryMonth' and not scope_month:
                # Preserve January–June historical cached values, explicitly labelled.
                for raw in sheet_by_name[name]['rows'][1:]:
                    values=raw['values']
                    if values.get('A') in list(calendar.month_name)[1:7]:rows.append(values.copy())
            for key,items in sorted(grouped.items()):
                items=[r for r in items if not r.get('personal') and r.get('treatment')!='personal']
                amounts=[money(sum(r['amount']+float(r.get('fee',0) or 0) for r in items if collection(r)==s)) for s in ['Material Expense','Cost of Sales Expense','Operating Expense','COS_Allowance']]
                methods=[money(sum(r['amount']+float(r.get('fee',0) or 0) for r in items if method in r.get('method','').lower())) for method in ['cash','cheque','gcash']]
                # GCash contains "cash"; keep method categories disjoint.
                methods[0]=money(sum(r['amount']+float(r.get('fee',0) or 0) for r in items if r.get('method','').lower()=='cash'))
                methods[1]=money(sum(r['amount']+float(r.get('fee',0) or 0) for r in items if r.get('method','').lower() in ['cheque','check']))
                n=header+len(rows)+1
                rows.append(dict(zip('ABCDEFGHI',[serial(key) if name=='Expense Summary' and key!='Date missing' else key,*amounts,*methods,(f'SUM(B{n}:E{n})',money(sum(amounts)))])))
            rows.append({'A':'Totals are payment detail only. Cash/GCash/cheque columns are method breakdowns, not additional expenses.'})
            rows.append({'A':'September-only dataset; other months and undated quarterly payments are excluded.' if scope_month else 'Historical January–June monthly figures are source snapshots; missing controls/payroll are not invented.'})
        else:
            continue
        files[path]=render_xml(files[path],header,rows,merges)
        root=ET.fromstring(files[path]);sd=root.find('m:sheetData',NS)
        overrides={}
        if name in ['COA','Copy of Accounts']:
            overrides={'B1':'CODE','C1':'ACCOUNT TITLE'} if name=='COA' else {'A1':'CODE','B1':'ACCOUNT TITLE'}
        if name in ['Suppliers','Suppliers List']:overrides.update(A1='SUPPLIER',B1='TIN',C1='ADDRESS')
        if name=='COS_Allowance':overrides.update(I3='TREATMENT',J3='RECEIPTS LINKED',K3='RETURNED',L3='OUTSTANDING')
        for raw in sheet_by_name[name]['rows']:
            if raw['row']>header:break
            for col,v in raw['values'].items():
                if not isinstance(v,str):continue
                if 'QUARTER' in v.upper():overrides[f'{col}{raw["row"]}']=re.sub(r'\d(?:ST|ND|RD|TH) QUARTER',(calendar.month_name[int(scope_month[5:])].upper()+' '+scope_month[:4]) if scope_month else f'{quarter+1}{["ST","ND","RD","TH"][quarter]} QUARTER',v,flags=re.I)
                if re.fullmatch(r'[A-Za-z]+\s+20\d{2}',v.strip()):overrides[f'{col}{raw["row"]}']=calendar.month_name[int(month[5:])]+' '+str(year)
        for ref,value in overrides.items():
            number=int(re.search(r'\d+',ref).group());row=next((r for r in sd if int(r.attrib['r'])==number),None)
            if row is None:row=ET.SubElement(sd,'{'+MAIN+'}row',{'r':str(number)})
            old=next((c for c in row if c.attrib.get('r')==ref),None)
            style=old.attrib.get('s') if old is not None else None
            if old is not None:row.remove(old)
            row.append(cell(ref,value,style))
            from openpyxl.utils.cell import column_index_from_string
            row[:]=sorted(list(row),key=lambda c:column_index_from_string(re.sub(r'\d','',c.attrib['r'])))
        sd[:]=sorted(list(sd),key=lambda r:int(r.attrib['r']))
        files[path]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
        manifest['sheets'][name]={'output_rows':len(rows),'header_row':header}
    # Drop stale calculation chain referring to old source row numbers.
    files.pop('xl/calcChain.xml',None)
    relpath='xl/_rels/workbook.xml.rels'
    relroot=ET.fromstring(files[relpath])
    for r in list(relroot):
        if 'calcChain' in r.attrib.get('Type',''):relroot.remove(r)
    files[relpath]=ET.tostring(relroot,encoding='utf-8',xml_declaration=True)
    ct=ET.fromstring(files['[Content_Types].xml'])
    for e in list(ct):
        if e.attrib.get('PartName')=='/xl/calcChain.xml':ct.remove(e)
    files['[Content_Types].xml']=ET.tostring(ct,encoding='utf-8',xml_declaration=True)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    return output.getvalue(),manifest
