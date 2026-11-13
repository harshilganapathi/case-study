"""Non-destructive normalization and audit flags; no business imputation."""
from .ingest import DATES, FIELDS, MODULES, NUMERIC, SUBTYPES, Record, date, missing, number


def normalize(record: Record, max_expected_days: int) -> tuple[dict, list[str]]:
    values, flags = {}, []
    for key in FIELDS:
        raw = record.values[key]
        value = raw.strip()
        if raw != value:
            flags.append('trimmed:' + key)
        if missing(value):
            values[key] = ''
        elif key in NUMERIC:
            numeric = number(value)
            if numeric is None:
                flags.append('invalid_numeric:' + key)
                values[key] = value  # Preserve invalid input, never coerce to zero.
            else:
                values[key] = format(numeric, 'f')
        elif key in DATES:
            parsed = date(value)
            if parsed is None:
                flags.append('invalid_date:' + key)
                values[key] = value
            else:
                values[key] = parsed.isoformat()
        else:
            values[key] = value
    qty = number(record.values['QTY'])
    if qty is None:
        flags.append('quantity_unavailable')
    elif qty <= 0:
        flags.append('nonpositive_quantity')
    if qty is not None and qty != qty.to_integral_value():
        flags.append('fractional_quantity')
    for key in ('PART', 'Condition', 'Module', 'SubType'):
        if not values[key]:
            flags.append('missing:' + key)
    for key, allowed in [('Module', MODULES), ('SubType', SUBTYPES)]:
        if values[key] and values[key] not in allowed:
            flags.append('unrecognized:' + key)
    if record.recovery != 'unchanged':
        flags.append('recovered_split_missing_condition')
    if record.unlabelled_tail and not missing(record.unlabelled_tail):
        flags.append('unlabelled_tail_value')
    if values['SN'].upper() in {'', 'NSI', 'N/S/N'}:
        flags.append('serial_missing_or_placeholder')
    expected = number(record.values['AvgNoofSalesDays'])
    if expected is None:
        flags.append('expected_days_unavailable')
    elif expected <= 0 or expected > max_expected_days:
        flags.append('expected_days_outside_review_range')
    if record.values['Type'] in {'Inventory', 'Invoiced'}:
        for key in ('Repair Unit Cost', 'Repair Ext Cost'):
            amount = number(record.values[key])
            if amount is None:
                flags.append('cost_unavailable:' + key)
            elif amount == 0:
                flags.append('reported_zero:' + key)
    if record.values['Type'] == 'Invoiced':
        if qty is not None and qty < 0:
            flags.append('possible_credit')
        if date(record.values['Invoice Date']) is None:
            flags.append('invoice_date_unavailable')
        oh, invoice = date(record.values['OH_DATE']), date(record.values['Invoice Date'])
        if oh is None:
            flags.append('oh_date_unavailable')
        if oh and invoice and invoice < oh:
            flags.append('negative_oh_to_invoice_interval')
    return values, sorted(set(flags))
