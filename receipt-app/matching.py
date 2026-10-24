"""Conservative deterministic matching; amounts alone never identify a supplier."""
import re
from collections import defaultdict
from functools import lru_cache
from decimal import Decimal
from difflib import SequenceMatcher


def norm(value):
    return _normalized(str(value or ''))


@lru_cache(maxsize=16384)
def _normalized(value):
    return re.sub(r'[^a-z0-9]', '', value.lower())


def number(value):
    text = str(value or '').strip()
    if text.lower() in ('', '-', 'n/a', 'na', 'none', '0'):
        return ''
    # Excel numeric receipt numbers can have a trailing .0 or leading zeroes.
    if re.fullmatch(r'\d+(?:\.0+)?', text):
        return str(int(Decimal(text)))
    return norm(text)


def receipt_numbers(row):
    values=row.get('receipt_numbers') or re.split(r'[,;]',str(row.get('receipt_no') or ''))
    return {number(v) for v in values if number(v)}


def tin(value):
    digits = re.sub(r'\D', '', str(value or ''))
    # Compare the taxpayer's nine digits; branch suffixes vary in these files.
    return digits[:9] if len(digits) in (9, 12) else ''


def identity(row):
    return norm(row.get('company')) + '|' + tin(row.get('tin'))


def same_supplier(a, b, aliases=()):
    if (identity(a), identity(b)) in aliases or (identity(b), identity(a)) in aliases:
        return True
    at, bt = tin(a.get('tin')), tin(b.get('tin'))
    if at and bt:
        return at == bt
    if a.get('supplier_key') and a.get('supplier_key')==b.get('supplier_key'):return True
    business_a,business_b=norm(a.get('business_name')),norm(b.get('business_name'))
    if business_a and business_a==business_b:return True
    an, bn = norm(a.get('company')), norm(b.get('company'))
    return bool(an and an == bn)


def centavos(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal('1')))


def plan_matches(rows, blocked=(), aliases=(), require_identifiers=False, allow_si_groups=False):
    """Return only mutually unique exact matches and explicit receipt groups.

    Partial groups require a shared receipt number and a sum equal to the
    receipt balance. Guessing subsets of equal-looking payments is avoided.
    """
    blocked = set(blocked)
    payments = [r for r in rows if r['kind'] == 'payment' and centavos(r['remaining']) > 0 and not r.get('personal') and r.get('treatment')!='personal']
    receipts = [r for r in rows if r['kind'] == 'receipt' and centavos(r['remaining']) > 0
                and r.get('collection') != 'Non Receipt' and not r.get('personal')]
    remaining = {r['id']: centavos(r['remaining']) for r in payments + receipts}
    plans = []

    def identifiers(row):
        return receipt_numbers(row)|({number(row.get('reference'))} if number(row.get('reference')) else set())

    def eligible(p, r):
        if tin(p.get('tin')) and tin(r.get('tin')) and tin(p.get('tin'))!=tin(r.get('tin')):return False
        if (p['id'], r['id']) in blocked or not same_supplier(p, r, aliases):
            return False
        if require_identifiers:
            if tin(p.get('tin')) and tin(r.get('tin')) and tin(p.get('tin'))!=tin(r.get('tin')):return False
            if not identifiers(p)&identifiers(r):return False
        pn, rn = receipt_numbers(p), receipt_numbers(r)
        return not (pn and rn and pn.isdisjoint(rn))

    # One payment can explicitly reference several receipts. Require an exact
    # sum, complete receipt-number coverage and no competing group proposal.
    combined=[]
    for p in payments:
        pn=receipt_numbers(p)
        if len(pn)<2:continue
        group=[r for r in receipts if remaining[r['id']]>0 and eligible(p,r) and receipt_numbers(r)&pn]
        if group and set().union(*(receipt_numbers(r) for r in group))==pn and sum(remaining[r['id']] for r in group)==remaining[p['id']]:combined.append((p,group))
    used=defaultdict(int)
    for p,group in combined:
        for r in group:used[r['id']]+=1
    for p,group in combined:
        if all(used[r['id']]==1 for r in group):
            for r in group:
                amount=remaining[r['id']]
                plans.append(dict(payment=p['id'],receipt=r['id'],cents=amount,reason='Explicit receipt list and supplier match; receipt balances equal payment'))
                remaining[r['id']]=0;remaining[p['id']]-=amount

    # A receipt identifier recorded in the payment workbook is stronger than
    # an amount match. Require the whole remaining group to reconcile exactly.
    groups = []
    for r in receipts:
        if not remaining[r['id']]:continue
        rn = receipt_numbers(r)
        if not rn:
            continue
        def si_eligible(p):
            if (p['id'],r['id']) in blocked:return False
            pt,rt=tin(p.get('tin')),tin(r.get('tin'))
            if pt and rt and pt!=rt:return False
            return eligible(p,r) or allow_si_groups
        ps = [p for p in payments if remaining[p['id']]>0 and si_eligible(p) and receipt_numbers(p) & rn]
        if ps and sum(remaining[p['id']] for p in ps) == remaining[r['id']]:
            groups.append((r, ps))
    uses = defaultdict(int)
    for r, ps in groups:
        for p in ps:
            uses[p['id']] += 1
    for r, ps in groups:
        if all(uses[p['id']] == 1 for p in ps):
            for p in ps:
                amount = remaining[p['id']]
                plans.append(dict(payment=p['id'], receipt=r['id'], cents=amount,
                                  reason='Shared S.I.#; payment group exactly equals receipt balance; no conflicting TIN'))
                remaining[p['id']] = 0
                remaining[r['id']] -= amount

    # Missing receipt numbers: exact supplier and amount, unique in BOTH
    # directions. Repeated amounts, contradictory TINs and receipt numbers
    # remain for manual review. Dates are deliberately not restricted by month.
    candidates = []
    receipts_by_amount=defaultdict(list)
    for r in receipts:receipts_by_amount[remaining[r['id']]].append(r)
    for p in payments:
        if not remaining[p['id']]:
            continue
        for r in receipts_by_amount[remaining[p['id']]]:
            if remaining[r['id']] == remaining[p['id']] and eligible(p, r):
                candidates.append((p, r))
    pc, rc = defaultdict(int), defaultdict(int)
    for p, r in candidates:
        pc[p['id']] += 1
        rc[r['id']] += 1
    for p, r in candidates:
        if pc[p['id']] == rc[r['id']] == 1:
            plans.append(dict(payment=p['id'], receipt=r['id'], cents=remaining[p['id']],
                              reason='Unique exact supplier and principal amount match'))
    return plans


def review_matches(rows, blocked=(), aliases=()):
    """Explain likely matches without allocating or changing accounting amounts."""
    blocked=set(blocked)
    ps=[r for r in rows if r['kind']=='payment' and centavos(r['remaining'])>0]
    rs=[r for r in rows if r['kind']=='receipt' and centavos(r['remaining'])>0 and r.get('collection')!='Non Receipt' and not r.get('personal')]
    proposals=[]
    for r in rs:
        rn=receipt_numbers(r)
        group=[p for p in ps if rn & receipt_numbers(p) and (p['id'],r['id']) not in blocked]
        if group:
            candidates=[(group,'Receipt number matches',100)]
        else:
            candidates=[]
            for p in ps:
                if (p['id'],r['id']) in blocked:continue
                pn=receipt_numbers(p)
                if pn and rn and pn.isdisjoint(rn):continue
                delta=abs(centavos(p['remaining'])-centavos(r['remaining']))
                if delta>100:continue
                known=same_supplier(p,r,aliases)
                similar=not known and SequenceMatcher(None,norm(p.get('company')),norm(r.get('company'))).ratio()>=.75
                if delta<=100 and (known or similar):
                    candidates.append(([p], 'Supplier identity matches' if known else 'Similar supplier name; verify identity',60 if known else 30))
        for group,reason,score in candidates:
            total=sum(centavos(p['remaining']) for p in group)
            difference=centavos(r['remaining'])-total
            issues=[]
            if len(group)>1:issues.append(f'{len(group)} partial payments grouped by S.I#')
            for p in group:
                if not same_supplier(p,r,aliases):
                    issues.append('Supplier identity needs confirmation')
                if tin(p.get('tin')) and tin(r.get('tin')) and tin(p.get('tin'))!=tin(r.get('tin')):
                    issues.append('TIN conflict: verify original documents')
                if norm(p.get('company'))!=norm(r.get('company')):issues.append('Payment payee and receipt legal name differ')
            if difference:
                issues.append('Small amount difference; no automatic write-off' if abs(difference)<=100 else 'Amount difference needs investigation')
            collision=sum(bool(receipt_numbers(other) & rn) for other in rs)>1 if rn else False
            if collision:issues.append('Receipt number appears on multiple open receipts')
            proposals.append(dict(receipt=r['id'],payments=[p['id'] for p in group],reason=reason,
                                  issues=list(dict.fromkeys(issues)),difference=difference/100,
                                  payment_total=total/100,receipt_total=centavos(r['remaining'])/100,
                                  score=score,can_confirm=total<=centavos(r['remaining'])))
    return sorted(proposals,key=lambda p:(-p['score'],abs(p['difference'])))
