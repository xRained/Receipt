"""Read every worksheet cell, cached result and formula without modifying Excel."""
import collections
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def audit(path):
    with zipfile.ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',NS)]
        rels={n.attrib['Id']:n.attrib['Target'] for n in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        workbook=ET.fromstring(z.read('xl/workbook.xml'))
        out={'file':Path(path).name,'sheets':[],'external_link_files':sum(n.startswith('xl/externalLinks/externalLink') and n.endswith('.xml') for n in z.namelist())}
        for s in workbook.find('m:sheets',NS):
            rid=s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target=rels[rid]
            target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            root=ET.fromstring(z.read(target))
            rows=[];formulas=[];errors=[];nonempty=0;functions=collections.Counter()
            for row in root.findall('m:sheetData/m:row',NS):
                values={}
                for cell in row:
                    ref=cell.attrib['r'];kind=cell.attrib.get('t');value=cell.find('m:v',NS)
                    value=value.text if value is not None else None
                    if kind=='s' and value is not None:value=strings[int(value)]
                    elif kind=='inlineStr':value=''.join(cell.find('m:is',NS).itertext())
                    elif value is not None and kind not in ['str','e','b']:
                        try:value=float(value);value=int(value) if value.is_integer() else value
                        except ValueError:pass
                    if value is not None:values[re.sub(r'\d','',ref)]=value;nonempty+=1
                    f=cell.find('m:f',NS)
                    if f is not None:
                        text=f.text or ''
                        formulas.append({'cell':ref,'formula':text,'cached':value,'attributes':f.attrib})
                        for fn in re.findall(r'([A-Za-z_][A-Za-z0-9_.]*)\s*\(',text):functions[fn.upper()]+=1
                    if kind=='e':errors.append({'cell':ref,'error':value})
                if values:rows.append({'row':int(row.attrib['r']),'values':values})
            merges=[n.attrib['ref'] for n in root.findall('m:mergeCells/m:mergeCell',NS)]
            validations=[{'range':n.attrib.get('sqref'),'formula':n.findtext('m:formula1','',NS)} for n in root.findall('m:dataValidations/m:dataValidation',NS)]
            sheet={'name':s.attrib['name'],'rows':rows,'nonempty_cells':nonempty,'formulas':formulas,'formula_functions':dict(functions),'errors':errors,'merges':merges,'validations':validations}
            out['sheets'].append(sheet)
        return out


if __name__=='__main__':
    result=[audit(p) for p in sys.argv[1:]]
    target=Path(__file__).parent/'data'/'workbook-audit.json'
    target.write_text(json.dumps(result,default=str),encoding='utf-8')
    for w in result:
        print('\nWORKBOOK',w['file'],'external links',w['external_link_files'])
        for s in w['sheets']:
            print(s['name'],json.dumps({'populated_rows':len(s['rows']),'cells':s['nonempty_cells'],'formulas':len(s['formulas']),'functions':s['formula_functions'],'errors':s['errors'][:10],'merges':len(s['merges']),'validations':len(s['validations'])}))
            print('LAST ROWS',json.dumps(s['rows'][-3:])[:1800])
    print('Full cell/formula audit:',target)
