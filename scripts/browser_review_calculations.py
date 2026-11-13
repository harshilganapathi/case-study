"""Browser-to-source reconciliation for the supplied case-study export."""
from playwright.sync_api import sync_playwright,expect
from pathlib import Path
from decimal import Decimal
import csv,json
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'reports/browser-review/supplemental';out.mkdir(exist_ok=True)
with (ROOT/'reports/audit/calculation_records.csv').open() as f: records=list(csv.DictReader(f))
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=True,chromium_sandbox=True)
 page=browser.new_page(viewport={'width':1440,'height':1100},accept_downloads=True)
 page.goto('http://127.0.0.1:8501/')
 expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible(timeout=60000)
 page.get_by_test_id('stRadio').get_by_text('Repair economics',exact=True).click()
 expect(page.get_by_role('heading',name='Repair economics',exact=True)).to_be_visible(timeout=60000)
 expect(page.get_by_test_id('stApp')).to_have_attribute('data-test-script-state','notRunning',timeout=60000)
 slider=page.get_by_test_id('stSlider').get_by_role('slider')
 for _ in range(20): slider.press('ArrowLeft')
 expect(slider).to_have_attribute('aria-valuenow','0')
 page.keyboard.press('Tab')
 expect(page.get_by_text('165 transactions flagged at the 0% margin threshold; 165 have negative contribution.',exact=True)).to_be_visible(timeout=30000)
 expect(page.get_by_test_id('stApp')).to_have_attribute('data-test-script-state','notRunning',timeout=60000)
 with page.expect_download() as download:
  page.get_by_role('button',name='Download this table',exact=True).nth(1).click()
 download.value.save_as(str(out/'negative_sales.csv'))
 with (out/'negative_sales.csv').open(encoding='utf-8-sig') as f: losses=list(csv.DictReader(f))
 expected_losses=sum(Decimal(r['Extended Sales Price'])<Decimal(r['Repair Ext Cost']) for r in records if r['Type']=='Invoiced' and Decimal(r['QTY'])>0)
 assert len(losses)==expected_losses,len(losses)
 assert all(Decimal(r['contribution'])<0 for r in losses)
 print('Weak margin slider: zero threshold export contains exactly 165 negative-contribution sales',flush=True)
 page.get_by_test_id('stCheckbox').filter(has_text='Filter by invoice date').click()
 datebox=page.get_by_test_id('stDateInput').locator('input')
 expect(datebox).to_be_visible()
 print('Date field before:',datebox.input_value(),flush=True)
 datebox.fill('2023/08/01 – 2023/08/29');datebox.press('Enter');datebox.press('Tab')
 expected=sum((Decimal(r['Extended Sales Price']) for r in records if r['Type']=='Invoiced' and Decimal(r['QTY'])>0 and '2023-08-01'<=r['Invoice Date']<='2023-08-29'),Decimal(0))
 expect(page.get_by_test_id('stMetricValue').first).to_have_text(f'{expected:,.2f}',timeout=30000)
 page.get_by_test_id('stMain').evaluate('(e)=>e.scrollTop=0')
 page.screenshot(path=str(out/'narrow-invoice-date.png'),full_page=True)
 print('Narrowed invoice range sales match independent source sum:',expected,flush=True)
 (out/'checks.json').write_text(json.dumps({'weak_margin_zero_negative_records':len(losses),'date_range':['2023-08-01','2023-08-29'],'expected_sales':str(expected),'passed':True},indent=2))
 browser.close()
