"""Shared, independently testable selection and CSV presentation helpers."""
import csv
import io
import json

from .timing import parse_date


def category(value):
    return value.strip() or 'Unknown'


def select_records(records, modules=(), subtypes=(), search='', warehouses=(), conditions=()):
    term = search.strip().casefold()
    return [r for r in records
            if (not modules or category(r['Module']) in modules)
            and (not subtypes or category(r['SubType']) in subtypes)
            and (not term or term in r['PART'].casefold() or term in r.get('Updated_Description', '').casefold()
                 or term in r.get('Description', '').casefold())
            and (not warehouses or category(r['WHSE']) in warehouses)
            and (not conditions or category(r['Condition']) in conditions)]


def invoice_date(record):
    """Use the same normalized date and audit-flag policy as timing."""
    return parse_date(record.get('Invoice Date', ''), 'Invoice Date',
                      json.loads(record.get('audit_flags', '[]')))


def invoice_window(records, start, end):
    """Only apply this on invoice-based views; undated inventory/scrap is never date-filtered."""
    result = []
    for r in records:
        if r['Type'] != 'Invoiced':
            continue
        invoice = invoice_date(r)
        if invoice is not None and start <= invoice <= end:
            result.append(r)
    return result


def csv_bytes(rows, columns=None):
    columns = columns or (list(rows[0]) if rows else [])
    text = io.StringIO(newline='')
    writer = csv.DictWriter(text, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue().encode('utf-8-sig')
