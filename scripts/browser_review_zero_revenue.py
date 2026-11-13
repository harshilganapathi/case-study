"""Browser regression for supported zero-revenue losses on synthetic replacement exports."""
import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    from playwright.sync_api import sync_playwright,expect
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8501/')
    args=parser.parse_args()
    output=ROOT/'reports/browser-review/zero-revenue';output.mkdir(parents=True,exist_ok=True)
    source=ROOT/'Case_Study_Dataset.csv'
    original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    with source.open(encoding='cp1252',newline='') as f: fields=next(csv.reader(f))
    results=[]
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch(channel='chrome',headless=True,chromium_sandbox=True)
        try:
            page=browser.new_page(viewport={'width':1440,'height':1200},accept_downloads=True)
            page.goto(args.url,wait_until='domcontentloaded')
            expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible(timeout=60000)
            page.get_by_test_id('stRadio').get_by_text('Review queue',exact=True).click()
            expect(page.get_by_test_id('stMetricValue').first).to_have_text('123',timeout=60000)
            with tempfile.TemporaryDirectory() as directory:
                for count in (5,10):
                    filename=f'zero-revenue-{count}.csv'
                    fixture=Path(directory)/filename
                    base=dict.fromkeys(fields,'NULL')
                    base.update({'PART':'QA-ZERO','SN':'NSI','Description':'Zero revenue test',
                                 'QTY':'1','Condition':'R','Module':'CORE','SubType':'HVM',
                                 'AvgNoofSalesDays':'90','Repair Unit Cost':'0','Repair Ext Cost':'0'})
                    stock=dict(base,Type='Inventory',WHSE='MDT',TAG_NO='STOCK')
                    losses=[dict(base,**{'Type':'Invoiced','TAG_NO':f'LOSS-{i}',
                            'Invoice Date':'4/1/2023','OH_DATE':'1/1/2023',
                            'Unit Sales Price':'0','Extended Sales Price':'0',
                            'Repair Unit Cost':'10','Repair Ext Cost':'10'}) for i in range(count)]
                    with fixture.open('w',newline='') as f:
                        writer=csv.DictWriter(f,fieldnames=fields)
                        writer.writeheader();writer.writerows([stock,*losses])
                    page.locator('input[type=file]').set_input_files(str(fixture))
                    reason=f'Repair costs exceed zero sales, contribution -{count*10:.2f} across {count} eligible sale records'
                    expect(page.get_by_test_id('stAlertContentInfo').get_by_text(reason,exact=True)).to_be_visible(timeout=60000)
                    expect(page.get_by_test_id('stMetricValue').first).to_have_text('1')
                    expect(page.get_by_test_id('stException')).to_have_count(0)
                    with page.expect_download() as downloaded:
                        page.get_by_role('button',name='Download full queue with evidence',exact=True).click()
                    csv_path=output/f'queue-{count}.csv';downloaded.value.save_as(str(csv_path))
                    with csv_path.open(encoding='utf-8-sig') as f: queue=list(csv.DictReader(f))
                    assert len(queue)==1
                    record=queue[0]
                    assert record['status']=='Review' and record['repair_evidence_supported']=='True'
                    assert record['repair_margin']==''
                    assert record['repair_contribution']==str(-count*10)
                    page.get_by_test_id('stMain').evaluate('(e)=>e.scrollTop=0')
                    page.screenshot(path=str(output/f'zero-revenue-{count}.png'),full_page=True)
                    results.append({'sale_records':count,'status':record['status'],
                                    'contribution':record['repair_contribution'],'percentage_margin':None})
                    page.get_by_role('button',name=f'Remove {filename}',exact=True).click()
                    expect(page.get_by_test_id('stMetricValue').first).to_have_text('123',timeout=60000)
            assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
            (output/'checks.json').write_text(json.dumps({'passed':True,'cases':results,
                'url':args.url,'default_review_parts_restored':123,'raw_source_sha256':original_hash},indent=2)+'\n')
            print('Browser regression passed for five and ten zero-revenue loss records; original source restored.')
        except Exception:
            if 'page' in locals():
                (output/'failure.txt').write_text(page.locator('body').inner_text())
                page.screenshot(path=str(output/'failure.png'),full_page=True)
            raise
        finally:
            browser.close()


if __name__=='__main__':
    main()
