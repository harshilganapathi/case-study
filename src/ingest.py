"""Strict CSV ingestion and narrowly validated recovery of split export records."""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = (
    'Type', 'PART', 'Invoice Date', 'SN', 'Description', 'QTY', 'Condition',
    'TAG_NO', 'FSC', 'OH_DATE', 'Rep Order No', 'WHSE', 'Repair Unit Cost',
    'Repair Ext Cost', 'Unit Sales Price', 'Extended Sales Price', 'PO_No',
    'Misc_PONO', 'BackLog', 'OrderNo', 'Ultimate_Destination_Country',
    'Updated_Description', 'Module', 'SubType', 'AvgNoofSalesDays',
)
STATUSES = {'Inventory', 'Invoiced', 'Scrapped'}
NUMERIC = ('QTY', 'Repair Unit Cost', 'Repair Ext Cost', 'Unit Sales Price',
           'Extended Sales Price', 'AvgNoofSalesDays')
DATES = ('Invoice Date', 'OH_DATE')
MODULES = {'Non-HVM', 'CORE', 'LPT', 'FAN', 'QEC / LRU'}
SUBTYPES = {'Non-HVM', 'Airfoils', 'HVM', 'LLPs'}


def missing(value: str) -> bool:
    return value.strip().upper() in {'', 'NULL'}


def number(value: str) -> Decimal | None:
    try:
        result = Decimal(value.strip())
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def date(value: str):
    for pattern in ('%m/%d/%Y', '%Y-%m-%d'):
        try:
            parsed = datetime.strptime(value.strip(), pattern).date()
            if pattern == '%Y-%m-%d' and parsed.isoformat() != value.strip():
                continue
            return parsed
        except ValueError:
            continue
    return None


@dataclass
class Record:
    values: dict[str, str]
    source_records: tuple[int, ...]
    recovery: str = 'unchanged'
    unlabelled_tail: str = ''


@dataclass
class Quarantine:
    source_records: tuple[int, ...]
    reason: str
    raw_rows: list[list[str]]


@dataclass
class IngestResult:
    records: list[Record]
    quarantine: list[Quarantine]
    raw_rows: list[list[str]]
    encoding: str
    sha256: str


def decode(raw: bytes, encoding: str | None = None) -> tuple[str, str]:
    if encoding:
        return raw.decode(encoding, errors='strict'), encoding
    try:
        return raw.decode('utf-8-sig', errors='strict'), 'utf-8-sig'
    except UnicodeDecodeError:
        # This is an explicit fallback policy, not proof of source encoding.
        return raw.decode('cp1252', errors='strict'), 'cp1252'


def recover(head: list[str], tail: list[str]) -> tuple[dict[str, str], str] | None:
    """Only recover the observed missing-condition pattern; never infer quantity."""
    if len(head) != len(FIELDS) or len(tail) != len(FIELDS):
        return None
    if not head[4].strip() or any(head[5:]) or any(tail[20:]):
        return None
    qty = number(tail[0])
    if qty is None or qty != qty.to_integral_value():
        return None
    candidate = dict(zip(FIELDS, head[:5] + [tail[0], ''] + tail[1:19], strict=True))
    if not candidate['PART'].strip() or missing(candidate['TAG_NO']):
        return None
    if candidate['Module'] not in MODULES or candidate['SubType'] not in SUBTYPES:
        return None
    for key in NUMERIC:
        if not missing(candidate[key]) and number(candidate[key]) is None:
            return None
    for key in DATES:
        if not missing(candidate[key]) and date(candidate[key]) is None:
            return None
    if candidate['Type'] == 'Invoiced':
        if date(candidate['Invoice Date']) is None or any(
            number(candidate[k]) is None for k in ('Unit Sales Price', 'Extended Sales Price')
        ):
            return None
    elif candidate['Type'] == 'Inventory':
        if missing(candidate['WHSE']) or not missing(candidate['Invoice Date']):
            return None
    else:
        return None  # No observed split scrap pattern is authorized by this rule.
    return candidate, tail[19]


def ingest_rows(rows: list[list[str]], encoding: str = '', sha256: str = '') -> IngestResult:
    records, quarantine = [], []
    index = 0
    while index < len(rows):
        row = rows[index]
        ordinal = index + 2  # Header is CSV record 1; not necessarily physical line 1.
        if len(row) != len(FIELDS):
            quarantine.append(Quarantine((ordinal,), 'wrong_column_count', [row]))
            index += 1
            continue
        if row[0] not in STATUSES:
            quarantine.append(Quarantine((ordinal,), 'orphan_or_unknown_status', [row]))
            index += 1
            continue
        if not any(row[5:]):
            if index + 1 < len(rows) and rows[index + 1] and rows[index + 1][0] not in STATUSES:
                tail = rows[index + 1]
                recovered = recover(row, tail)
                if recovered:
                    values, extra = recovered
                    records.append(Record(values, (ordinal, ordinal + 1),
                                          'split_missing_condition', extra))
                else:
                    quarantine.append(Quarantine((ordinal, ordinal + 1),
                                                 'ambiguous_split', [row, tail]))
                index += 2
            else:
                quarantine.append(Quarantine((ordinal,), 'incomplete_record', [row]))
                index += 1
        else:
            records.append(Record(dict(zip(FIELDS, row, strict=True)), (ordinal,)))
            index += 1
    accounted = [n for r in records + quarantine for n in r.source_records]
    if sorted(accounted) != list(range(2, len(rows) + 2)):
        raise AssertionError('Source record accounting failed')
    return IngestResult(records, quarantine, rows, encoding, sha256)


def load(path: Path, encoding: str | None = None) -> IngestResult:
    raw = path.read_bytes()
    text, actual_encoding = decode(raw, encoding)
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    header = next(reader, None)
    if header != list(FIELDS):
        raise ValueError('CSV schema mismatch: expected the exact 25-column source header')
    return ingest_rows(list(reader), actual_encoding, hashlib.sha256(raw).hexdigest())
