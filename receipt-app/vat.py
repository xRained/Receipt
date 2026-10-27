"""Philippine VAT split for explicitly classified, VAT-inclusive purchases."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def purchase_vat(amount, tag):
    tag = str(tag or '').strip().upper()
    if tag not in ('PG', 'PS', 'EX'):
        raise ValueError('Choose PG (goods), PS (services), or EX (VAT-exempt)')
    try:
        gross = Decimal(str(amount).replace(',', ''))
        if not gross.is_finite() or gross < 0:
            raise ValueError('Amount must be finite and non-negative')
        gross = gross.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError('Enter a valid VAT-inclusive amount')
    tax = (gross * Decimal(12) / Decimal(112)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if tag != 'EX' else Decimal(0)
    return dict(tax_tag=tag, vat_basis='inclusive', vat_rate=0 if tag == 'EX' else 12,
                input_tax_goods=float(tax) if tag == 'PG' else 0,
                input_tax_services=float(tax) if tag == 'PS' else 0,
                net_tax_base=float(gross - tax))


def automatic_withholding(amount, tag):
    """Standard selected purchase CWT; not an eligibility determination."""
    tag = str(tag or '').strip().upper()
    if tag not in ('PG','PS'):
        raise ValueError('Automatic withholding requires PG or PS; use document amount for EX or special cases')
    base = Decimal(str(purchase_vat(amount, tag)['net_tax_base']))
    rate = Decimal(1 if tag == 'PG' else 2)
    withheld = (base * rate / Decimal(100)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return dict(withholding=float(withheld),withholding_rate=float(rate),withholding_base=float(base),withholding_mode='auto')
