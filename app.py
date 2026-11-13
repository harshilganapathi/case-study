"""Local Streamlit inventory decision support. Launch with ./run.sh."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from src import audit, economics, metrics, timing
from src.decision_support import build_queue, COLUMNS as QUEUE_COLUMNS
from src.presentation import category, csv_bytes, invoice_date, invoice_window, select_records

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='Parts inventory decisions', page_icon='✈', layout='wide')


@st.cache_data(show_spinner='Checking and cleaning the export…')
def load_data(raw, filename, rule_hash):
    # Run the same pipeline on a private snapshot, leaving the supplied file untouched.
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory)/Path(filename).name
        source.write_bytes(raw)
        out = Path(directory)/'audit'
        summary = audit.run(source, out)
        with (out/'calculation_records.csv').open(encoding='utf-8', newline='') as f:
            records = list(csv.DictReader(f))
        quarantine = (out/'quarantine.jsonl').read_bytes()
    return records, summary, quarantine


def percent(value):
    return f'{Decimal(str(value))*100:,.2f}%' if value is not None else 'Unavailable'


def money(value):
    return f'{Decimal(str(value)):,.2f}' if value is not None else 'Unavailable'


def days(value):
    return f'{value} days' if value is not None else 'Unavailable'


def column_label(column):
    return {'part': 'Part number', 'QTY': 'Quantity', 'sales': 'Sales amount',
            'paired_median_observed_days': 'Median overhaul-to-sale days',
            'paired_median_expected_days': 'Median expected days'}.get(
                column, column.replace('_', ' ').replace('--', ' ').title())


def frame(rows):
    df = pd.DataFrame(rows)
    # Only display values are floats; all calculations/exports retain exact source decimals.
    numeric = {'qty','units','QTY','sales','repair_cost','repair_contribution','contribution',
               'repair_margin','margin','scrap_share','zero_cost_sale_share','above_expected_share',
               'expected_days','difference_days','median_observed_days','paired_median_observed_days',
               'paired_median_expected_days','median_paired_difference_days','rank'}
    for column in df.columns:
        if column in numeric:
            df[column] = pd.to_numeric(df[column], errors='coerce')
    return df


def table(rows, key, columns=None):
    if not rows:
        st.info('No records match this selection.')
        return
    df = frame(rows)
    configs = {k: st.column_config.Column(column_label(k)) for k in df.columns}
    configs.update({k: st.column_config.NumberColumn(column_label(k), format='%.2f')
                    for k in ('sales','repair_cost','contribution','repair_contribution')})
    configs.update({k: st.column_config.NumberColumn(k.replace('_',' ').title(), format='percent')
                    for k in ('margin','repair_margin','scrap_share','above_expected_share','zero_cost_sale_share')})
    if columns:
        df = df[[c for c in columns if c in df]]
    st.dataframe(df, hide_index=True, width='stretch', column_config=configs)
    st.download_button('Download this table', csv_bytes(rows), f'{key}.csv', 'text/csv', key=f'download_{key}')


def bars(rows, x, y, limit=20):
    if rows:
        ys = [y] if isinstance(y, str) else y
        df = frame(rows[:limit]).sort_values(ys[0], ascending=False, kind='stable')
        if not df[ys].notna().any().any():
            st.info('No usable values for this chart in the current selection.')
            return
        names = {k: column_label(k) for k in [x, *ys]}
        names.update({k: v for k, v in {'paired_median_observed_days': 'Overhaul to sale',
                                      'paired_median_expected_days': 'Expected'}.items() if k in ys})
        measure = ('Days' if any('days' in k for k in ys) else
                   'Amount (source currency)' if any(k in {'sales','repair_cost'} for k in ys) else 'Units')
        st.bar_chart(df.rename(columns=names), x=names[x], y=[names[k] for k in ys],
                     horizontal=True, sort=False, stack=False if len(ys) > 1 else None,
                     x_label=names[x], y_label=measure, height=max(300, len(df)*30))


def dated(records, key):
    enable = st.checkbox('Filter by invoice date', key=f'{key}_dates_enabled')
    if not enable:
        return records
    dates = []
    for r in records:
        if r['Type'] == 'Invoiced':
            invoice = invoice_date(r)
            if invoice is not None:
                dates.append(invoice)
    if not dates:
        st.info('No usable invoice dates in this selection.')
        return []
    selected = st.date_input('Invoice date range', value=(min(dates), max(dates)),
                             min_value=min(dates), max_value=max(dates), key=f'{key}_dates')
    if len(selected) != 2:
        st.info('Select both a start and end date.')
        return []
    return invoice_window(records, *selected)


st.sidebar.title('Parts inventory')
view = st.sidebar.radio('View', ['Overview', 'Scrap', 'Repair economics', 'Inventory & timing',
                                  'Review queue', 'Data quality'], key='view')
uploaded = st.sidebar.file_uploader('Use another export', type=['csv'])
try:
    source = Path(os.environ.get('PARTS_DATA_PATH', str(ROOT/'Case_Study_Dataset.csv')))
    raw = uploaded.getvalue() if uploaded is not None else source.read_bytes()
    filename = uploaded.name if uploaded is not None else source.name
    rule_hash = hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'src').glob('*.py')))).hexdigest()
    records, quality, quarantine = load_data(raw, filename, rule_hash)
except (OSError, ValueError, UnicodeError, csv.Error) as error:
    st.error(f'The export could not be loaded: {error}')
    st.info('Use an export with the original 25-column header. The source file has not been edited.')
    st.stop()

modules = st.sidebar.multiselect('Module', sorted({category(r['Module']) for r in records}), key='modules')
subtypes = st.sidebar.multiselect('Subtype', sorted({category(r['SubType']) for r in records}), key='subtypes')
search = st.sidebar.text_input('Find a part or description', key='part_search')
st.sidebar.caption('Empty category selections include all categories.')
selected = select_records(records, modules, subtypes, search)
st.sidebar.caption(f'{len(selected):,} of {len(records):,} deduplicated records selected')
if st.sidebar.button('Reload source and clear cache'):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption(f'Source: {filename}\n\nFingerprint: {quality["source_sha256"][:12]}')

st.caption('AVIATION PARTS · INVENTORY DECISION SUPPORT')
st.title(view)
st.caption('Historical export · identical records count once · OH_DATE is assumed to be the overhaul date')
with st.expander('Data quality and definitions', expanded=False):
    a = quality['accounting']
    st.write(f"{a['reconstructed_records']:,} split records recovered; "
             f"{a['duplicate_copies_excluded_from_calculations']:,} duplicate copies excluded; "
             f"{a['quarantined_cases']:,} unresolved cases quarantined.")
    st.write('Reported zero repair costs are retained. Missing classifications display as Unknown. '
             'Review flags indicate records to inspect, not instructions to scrap parts.')
    st.write('Timing assumes OH_DATE means overhaul date. Inventory receipt and export snapshot dates '
             'are unavailable, so stock age is not calculated. Amounts are in the export’s unspecified currency.')

if view == 'Overview':
    totals = metrics.calculate(selected)
    repair = economics.calculate(selected)
    intervals = timing.calculate(selected)['summary']
    cols = st.columns(4)
    cols[0].metric('On-hand units', f"{totals['inventory_units']:,}")
    cols[1].metric('Observed scrap share', percent(totals['scrap_share']))
    cols[2].metric('Repair contribution margin', percent(repair['positive_sales']['margin']))
    cols[3].metric('Median overhaul-to-sale', days(intervals['median_observed_days']))
    st.write('Start with the inventory available, examine historical outcomes, then use the review '
             'queue to decide which parts deserve a closer look.')
    st.subheader('Inventory by module')
    bars(totals['inventory_by']['module'], 'module', 'units')
    table(totals['inventory_by']['module'], 'overview_inventory')
    st.caption(f"Timing covers {intervals['observed_records']:,} eligible sale records. "
               f"Repair margin covers {repair['positive_sales']['records']:,} positive-quantity sale records. "
               'Acquisition costs, freight and overhead are not included in repair contribution.')

elif view == 'Scrap':
    result = metrics.calculate(selected)
    cols = st.columns(3)
    cols[0].metric('Scrapped units', f"{result['scrapped_units']:,}")
    cols[1].metric('Positive sold units', f"{result['sold_units']:,}")
    cols[2].metric('Observed scrap share', percent(result['scrap_share']))
    st.write('Scrap share = scrapped units ÷ (scrapped units + positive sold units). '
             'Returns and on-hand inventory are excluded. This describes observed outcomes across '
             'the export; it does not estimate a future failure probability.')
    group = st.selectbox('Group outcomes by', ['module', 'subtype', 'module_subtype'], key='scrap_group')
    grouped = result['scrap_by'][group]
    if group != 'module_subtype':
        bars(grouped, group, ['scrapped_units', 'sold_units'])
    table(grouped, 'scrap_groups')
    st.subheader('Parts with the most scrapped units')
    top = [r for r in result['scrap_by']['part'] if r['scrapped_units'] > 0]
    bars(top, 'part', 'scrapped_units')
    table(top, 'scrapped_parts')
    with st.expander('Supporting records and exclusions'):
        table([r for r in selected if r['Type'] in {'Scrapped','Invoiced'}], 'scrap_source_records')
        table([r for r in result['exclusions'] if r['Type'] in {'Scrapped','Invoiced'}], 'scrap_quantity_exclusions')

elif view == 'Repair economics':
    rows = dated(selected, 'economics')
    threshold = st.slider('Weak margin threshold (%)', 0, 100, 20, key='economics_threshold')
    repair = economics.calculate(rows, Decimal(threshold)/100)
    main = repair['positive_sales']
    cards = list(zip(['Sales amount','Reported repair costs','Repair contribution','Contribution margin'],
                     [money(main['sales']),money(main['repair_cost']),money(main['contribution']),percent(main['margin'])]))
    for start in (0, 2):
        for col, (title, value) in zip(st.columns(2), cards[start:start+2]):
            col.metric(title, value)
    st.write('Contribution = extended sales − extended repair cost. Group margin = total contribution '
             '÷ total sales. Purchase costs, freight and overhead are unavailable.')
    st.caption(f"{main['records']:,} eligible positive-quantity sale records; "
               f"{main['zero_cost_records']:,} report zero repair cost; {repair['excluded_records']:,} invoice records excluded. "
               'Zero costs remain reported values; missing costs are never filled with zero.')
    group = st.selectbox('Group sales by', ['module','subtype','module_subtype','part'], key='economics_group')
    if group in {'module','subtype'}:
        bars(repair['by'][group], group, ['sales','repair_cost'])
    table(repair['by'][group], 'repair_groups')
    st.subheader('Transactions with weak or negative contribution')
    st.caption(f"{len(repair['weak_transactions']):,} transactions flagged at the {threshold}% margin threshold; "
               f"{main['negative_contribution_records']:,} have negative contribution.")
    table(repair['weak_transactions'], 'weak_sales')
    st.subheader('Parts with weak aggregate results')
    table(repair['part_review'], 'weak_parts')
    with st.expander('Returns, zero-cost coverage and supporting records'):
        st.write('Negative-quantity invoices are treated as possible credits. Signed totals retain '
                 'reported amounts, while positive-sale margins stay separate.')
        table([dict(population=k, **repair[k]) for k in ['positive_sales','credits','signed_total']], 'financial_reconciliation')
        table([dict(population=k, **repair[k]) for k in ['zero_cost_positive_sales','nonzero_cost_positive_sales']], 'zero_cost_coverage')
        table(repair['positive_details'], 'positive_sales')
        table(repair['credit_details'], 'credits')
        table(repair['exclusions'], 'economics_exclusions')

elif view == 'Inventory & timing':
    stock_tab, timing_tab = st.tabs(['On hand', 'Overhaul to sale'])
    with stock_tab:
        stock = [r for r in selected if r['Type'] == 'Inventory']
        left, right = st.columns(2)
        warehouses = left.multiselect('Warehouse', sorted({category(r['WHSE']) for r in stock}), key='stock_warehouses')
        conditions = right.multiselect('Condition', sorted({category(r['Condition']) for r in stock}), key='stock_conditions')
        stock = select_records(stock, warehouses=warehouses, conditions=conditions)
        result = metrics.calculate(stock)
        st.metric('Positive units on hand', f"{result['inventory_units']:,}")
        st.caption(f"{result['inventory_records']:,} positive-quantity records; "
                   f"{result['excluded_records']:,} quantity exceptions. No snapshot date is supplied.")
        group = st.selectbox('Group stock by', ['module','subtype','warehouse','condition','part'], key='stock_group')
        bars(result['inventory_by'][group], group, 'units')
        table(result['inventory_by'][group], 'inventory_group')
        table(result['inventory_detail'], 'inventory_locations')
        with st.expander('Stock records and quantity exceptions'):
            table(stock, 'inventory_source_records')
            table(result['exclusions'], 'inventory_exclusions')
    with timing_tab:
        st.write('Assumption: OH_DATE is the overhaul date. Overhaul-to-sale interval = invoice '
                 'date − overhaul date, in calendar days. Warehouse and condition filters above '
                 'apply only to on-hand stock; sold records have no warehouse.')
        rows = dated(selected, 'timing')
        limit = st.number_input('Maximum expected days for comparisons', min_value=1, max_value=1000000,
                                 value=3650, key='timing_expected_limit')
        result = timing.calculate(rows, limit)
        summary = result['summary']
        cols = st.columns(3)
        cols[0].metric('Median overhaul-to-sale', days(summary['median_observed_days']))
        cols[1].metric('Median paired difference', days(summary['median_paired_difference_days']))
        cols[2].metric('Above supplied expectation', percent(summary['above_expected_share']))
        st.caption(f"{summary['observed_records']:,} usable intervals / "
                   f"{result['positive_quantity_candidates']:,} positive-quantity sale records; "
                   f"{summary['paired_records']:,} paired comparisons. Statistics count each transaction once.")
        st.write('The origin of AvgNoofSalesDays is unspecified. Comparison assumes it is a useful '
                 'benchmark; its starting point may differ. This interval does not establish stock age.')
        grouped = st.selectbox('Group timing by', ['module','subtype','module_subtype'], key='timing_group')
        if grouped != 'module_subtype':
            bars(result['by'][grouped], grouped, ['paired_median_observed_days','paired_median_expected_days'])
        table(result['by'][grouped], 'timing_groups')
        if result['details']:
            paired = [r for r in result['details'] if not r['comparison_exclusion']]
            if paired:
                full_range = st.checkbox('Show full interval range', key='timing_full_range')
                focused = paired if full_range else [r for r in paired if r['observed_days'] <= 1000
                                                     and Decimal(r['expected_days']) <= 1000]
                st.caption(f'Showing {len(focused):,} of {len(paired):,} paired records. '
                           + ('Full interval range.' if full_range else 'Chart focus: 0–1,000 days.')
                           + ' All paired records remain in statistics and downloads.')
                if focused:
                    scatter = frame(focused).rename(columns={'expected_days': 'Expected days',
                                                             'observed_days': 'Overhaul-to-sale days'})
                    st.scatter_chart(scatter, x='Expected days', y='Overhaul-to-sale days', height=340)
        with st.expander('Intervals and excluded records'):
            table(result['details'], 'timing_details')
            table(result['observed_exclusions'], 'timing_exclusions')
            table(result['comparison_exclusions'], 'timing_comparison_exclusions')

elif view == 'Review queue':
    st.write('Review parts that are on hand using their historical repair economics and scrap outcomes. '
             'Stock is aggregated before attaching history, so transactions are never multiplied by stock rows.')
    with st.expander('Review rules', expanded=True):
        cols = st.columns(4)
        weak = cols[0].number_input('Margin below (%)', 0, 100, 20, key='queue_margin')
        min_sales = cols[1].number_input('Minimum sale records', 1, 1000000, 5, key='queue_min_sales')
        scrap_cutoff = cols[2].number_input('Scrap share at least (%)', 0, 100, 50, key='queue_scrap')
        min_disposed = cols[3].number_input('Minimum disposed units', 1, 1000000, 10, key='queue_min_disposed')
        st.caption('Editable assumptions. Review priority: number of triggered rules, then units on '
                   'hand, then part number. An untriggered rule is not proof of low risk.')
    stock = [r for r in selected if r['Type'] == 'Inventory']
    cols = st.columns(2)
    warehouses = cols[0].multiselect('Stock warehouse', sorted({category(r['WHSE']) for r in stock}), key='queue_warehouses')
    conditions = cols[1].multiselect('Stock condition', sorted({category(r['Condition']) for r in stock}), key='queue_conditions')
    stock = select_records(stock, warehouses=warehouses, conditions=conditions)
    queue = build_queue(records, stock, Decimal(weak)/100, min_sales, min_disposed, Decimal(scrap_cutoff)/100)
    st.caption('Module, subtype, search, warehouse and condition filters select stock. Historical '
               'evidence uses all deduplicated records for those part numbers, across warehouses and conditions. '
               'There is no condition-matched prediction or automatic scrap recommendation.')
    counts = {status: sum(r['status'] == status for r in queue) for status in ['Review','Insufficient evidence','No rule triggered']}
    for col, (label, value) in zip(st.columns(3), counts.items()):
        col.metric(label, value)
    statuses = st.multiselect('Queue groups', list(counts), default=['Review'], key='queue_statuses')
    shown = [r for r in queue if r['status'] in statuses]
    if not queue:
        st.info('No positive inventory matches the stock filters.')
    elif not shown:
        st.info('No parts in the selected queue groups. Select another group to inspect evidence coverage.')
    if shown:
        table(shown, 'inventory_review_queue', ['rank','part','status','on_hand_units','reasons','eligible_sale_records',
                                              'repair_margin','zero_cost_sale_share','scrapped_units','sold_units','scrap_share'])
    st.download_button('Download full queue with evidence', csv_bytes(queue, QUEUE_COLUMNS),
                       'full_review_queue.csv', 'text/csv', key='full_queue_csv', disabled=not queue)
    if shown:
        part = st.selectbox('Inspect a part', [r['part'] for r in shown], key='inspect_part')
        evidence = next(r for r in queue if r['part'] == part)
        st.subheader(f'Evidence for {part}')
        for reason in evidence['reasons'].split('; '):
            if reason:
                st.info(reason)
        if not evidence['reasons']:
            st.write(evidence['status'] + '. Check the evidence-support fields before drawing conclusions.')
        st.caption(f"{evidence['eligible_sale_records']:,} eligible sale records; "
                   f"{evidence['disposed_units']:,} disposed units; "
                   f"{evidence['zero_cost_sale_records']:,} sales report zero repair cost. "
                   f"Stock locations: {evidence['warehouses']}. Conditions: {evidence['conditions']}.")
        with st.expander('Detailed evidence fields'):
            table([evidence], 'part_evidence')
        table([r for r in stock if r['PART'] == part], 'part_stock_locations',
              ['PART','QTY','WHSE','Condition','SN','TAG_NO','audit_flags','source_records'])
        with st.expander('All historical records for this part'):
            table([r for r in records if r['PART'] == part and r['Type'] != 'Inventory'], 'part_history')

elif view == 'Data quality':
    st.write('File-wide audit before dashboard filters. The raw export is never edited.')
    st.json(quality['accounting'])
    st.caption('A split pair becomes one record. Deduplication then keeps the first identical occurrence. '
               'Source record ordinals include the header as record 1.')
    table([{'flag':k,'records':v} for k,v in sorted(quality['calculation_flags'].items())], 'quality_flags')
    st.download_button('Download full audit JSON', json.dumps(quality,indent=2), 'audit.json','application/json',key='audit_json')
    st.download_button('Download quarantine', quarantine, 'quarantine.jsonl','application/x-ndjson',key='quarantine_jsonl')
    st.download_button('Download deduplicated records', csv_bytes(records), 'calculation_records.csv','text/csv',key='all_records')
    with st.expander('Records in the current filter selection'):
        table(selected, 'selected_calculation_records')
