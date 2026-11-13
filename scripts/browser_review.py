"""Capture real app screens in a separate Chrome profile. Requires a running app."""
import argparse
import csv
import json
import tempfile
from pathlib import Path

VIEWS = ['Overview','Scrap','Repair economics','Inventory & timing','Review queue','Data quality']
ROOT = Path(__file__).resolve().parents[1]


def run(url, output, headed=False):
    from playwright.sync_api import sync_playwright, expect
    output.mkdir(parents=True, exist_ok=True)
    evidence = {'url':url,'mode':'Playwright Chrome','screenshots':[],
                'checks':[],'page_errors':[],'completed':False,
                'visual_approval':'Pending human/assistant inspection of captured screenshots'}
    with sync_playwright() as runtime:
        browser = None
        try:
            browser = runtime.chromium.launch(channel='chrome', headless=not headed,
                                               chromium_sandbox=True)
            context = browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
            page = context.new_page()
            page.on('pageerror',lambda error:evidence['page_errors'].append(str(error)))
            page.set_default_timeout(20000)
            page.goto(url,wait_until='domcontentloaded')

            def settled(view):
                expect(page.get_by_role('heading',name=view,exact=True)).to_be_visible(timeout=60000)
                expect(page.get_by_test_id('stApp')).to_have_attribute('data-test-script-state','notRunning',timeout=60000)
                expect(page.get_by_test_id('stException')).to_have_count(0)

            def shot(name):
                page.keyboard.press('Escape')
                page.wait_for_timeout(150)
                expect(page.get_by_test_id('stApp')).to_have_attribute('data-test-script-state','notRunning',timeout=60000)
                expect(page.locator('[data-stale="true"]:visible')).to_have_count(0,timeout=60000)
                expect(page.get_by_test_id('stException')).to_have_count(0)
                target = output/f'{len(evidence["screenshots"])+1:02d}-{name}.png'
                original_size = page.viewport_size
                main = page.get_by_test_id('stMain')
                main.evaluate('(element) => {element.scrollTop = 0}')
                full_height = min(12000, max(original_size['height'], main.evaluate('(element) => element.scrollHeight')+100))
                page.set_viewport_size({'width':original_size['width'], 'height':full_height})
                expect(page.get_by_test_id('stApp')).to_have_attribute('data-test-script-state','notRunning',timeout=60000)
                expect(page.locator('[data-stale="true"]:visible')).to_have_count(0,timeout=60000)
                page.screenshot(path=str(target),full_page=True,animations='disabled')
                page.set_viewport_size(original_size)
                evidence['screenshots'].append(target.name)
                evidence['checks'].append(name)
                print('Captured',target.name,flush=True)

            def view(name):
                page.get_by_test_id('stRadio').get_by_text(name,exact=True).click()
                settled(name)

            def choose(label, value):
                widget = page.locator('[data-testid="stSelectbox"],[data-testid="stMultiSelect"]').filter(
                    has=page.get_by_text(label,exact=True))
                widget.get_by_role('combobox').click()
                page.get_by_role('option',name=value,exact=True).click()
                page.keyboard.press('Escape')

            def number(label, value):
                control=page.get_by_role('spinbutton',name=label,exact=True)
                control.fill(str(value)); control.press('Enter')

            settled('Overview'); shot('overview')
            with page.expect_download() as download:
                page.get_by_role('button',name='Download this table',exact=True).click()
            csv_path=output/'overview_inventory.csv'
            download.value.save_as(str(csv_path))
            with csv_path.open(encoding='utf-8-sig') as f:
                downloaded=list(csv.DictReader(f))
            if not downloaded or 'units' not in downloaded[0]:
                raise AssertionError('Overview download is not the expected inventory table')
            evidence['downloaded_inventory_units']=sum(int(r['units']) for r in downloaded)
            evidence['checks'].append('overview_csv_download')

            view('Scrap'); shot('scrap-module')
            for group in ['subtype','module_subtype']:
                choose('Group outcomes by',group); shot('scrap-'+group)
            view('Repair economics'); shot('repair-module')
            for group in ['subtype','module_subtype','part']:
                choose('Group sales by',group); shot('repair-'+group)
            page.get_by_test_id('stCheckbox').filter(has_text='Filter by invoice date').click()
            expect(page.get_by_text('Invoice date range',exact=True)).to_be_visible()
            shot('repair-date-filter')

            view('Inventory & timing'); shot('inventory-module')
            for group in ['subtype','warehouse','condition','part']:
                choose('Group stock by',group); shot('inventory-'+group)
            page.get_by_role('tab',name='Overhaul to sale',exact=True).click(); shot('timing-module')
            page.get_by_test_id('stCheckbox').filter(has_text='Show full interval range').click()
            shot('timing-full-range')
            for group in ['subtype','module_subtype']:
                choose('Group timing by',group); shot('timing-'+group)
            number('Maximum expected days for comparisons',1); shot('timing-low-expectation-limit')
            page.get_by_test_id('stCheckbox').filter(has_text='Filter by invoice date').click()
            shot('timing-date-filter')

            view('Review queue'); shot('review-queue')
            number('Margin below (%)',0)
            number('Scrap share at least (%)',100)
            shot('review-strict-rules')
            number('Minimum sale records',1000000)
            number('Minimum disposed units',1000000)
            expect(page.get_by_text('No parts in the selected queue groups. Select another group to inspect evidence coverage.',exact=True)).to_be_visible()
            shot('review-no-flags')
            choose('Queue groups','Insufficient evidence'); shot('review-insufficient-evidence')
            choose('Stock warehouse','MDT'); choose('Stock condition','R')
            shot('review-stock-filters')
            view('Data quality'); shot('data-quality')

            # Stock-only filters are checked independently from history-based timing.
            view('Inventory & timing')
            page.get_by_role('tab',name='On hand',exact=True).click()
            choose('Warehouse','MDT'); choose('Condition','R'); shot('inventory-location-condition-filter')
            choose('Module','FAN'); choose('Subtype','HVM'); shot('global-category-filters')
            search=page.get_by_role('textbox',name='Find a part or description',exact=True)
            search.fill('NO-MATCH-EXAMPLE-987654321'); search.press('Enter')
            for name in VIEWS:
                view(name)
                if name=='Inventory & timing':
                    page.get_by_role('tab',name='On hand',exact=True).click()
                if name=='Data quality':
                    page.get_by_text('Records in the current filter selection',exact=True).click()
                shot('empty-'+name.lower().replace(' ','-').replace('&','and'))
            search.fill(''); search.press('Enter')
            view('Overview')
            desktop_page = page
            page = context.new_page()
            page.set_viewport_size({'width':390,'height':844})
            page.goto(url,wait_until='domcontentloaded')
            settled('Overview')
            shot('overview-mobile')
            page.close()
            page = desktop_page

            # Synthetic bad-header fixture only; no personal file is uploaded.
            with tempfile.TemporaryDirectory() as directory:
                fixture=Path(directory)/'invalid-header.csv'
                fixture.write_text('unexpected,header\na,b\n')
                page.locator('input[type=file]').set_input_files(str(fixture))
                expect(page.get_by_text('The export could not be loaded:',exact=False)).to_be_visible(timeout=60000)
                shot('invalid-header-upload')
                with (ROOT/'Case_Study_Dataset.csv').open(encoding='cp1252',newline='') as source:
                    fields=next(csv.reader(source))
                replacement=Path(directory)/'replacement.csv'
                record=dict.fromkeys(fields,'NULL')
                record.update({'Type':'Inventory','PART':'QA-REPLACEMENT','SN':'NSI','Description':'Review fixture',
                               'QTY':'7','TAG_NO':'QA-TAG','WHSE':'MDT','Condition':'R','Module':'CORE',
                               'SubType':'HVM','Repair Unit Cost':'0','Repair Ext Cost':'0','AvgNoofSalesDays':'90'})
                with replacement.open('w',newline='') as f:
                    writer=csv.DictWriter(f,fieldnames=fields)
                    writer.writeheader();writer.writerow(record)
                page.locator('input[type=file]').set_input_files(str(replacement))
                expect(page.get_by_test_id('stMetricValue').first).to_have_text('7',timeout=60000)
                shot('valid-replacement-upload')
                page.get_by_role('button',name='Remove replacement.csv',exact=True).click()
                expect(page.get_by_test_id('stMetricValue').first).to_have_text(
                    f"{evidence['downloaded_inventory_units']:,}",timeout=60000)
                shot('default-source-restored')
            if evidence['page_errors']:
                raise AssertionError('Browser page errors were recorded; inspect results.json')
            evidence['completed']=True
        except Exception as error:
            evidence['error']=str(error)
            raise
        finally:
            (output/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
            if browser is not None: browser.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8501/')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/browser-review/captures')
    parser.add_argument('--headed',action='store_true',help='Show the separate review browser')
    args=parser.parse_args()
    run(args.url,args.output,args.headed)
    print('Screenshots captured. Visual review still requires inspecting them.')


if __name__=='__main__':
    main()
