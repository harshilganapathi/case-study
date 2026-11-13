"""Nonvisual full-export Streamlit AppTest checks; not a screenshot review."""
from streamlit.testing.v1 import AppTest
from pathlib import Path
import sys,time
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
app=AppTest.from_file(str(root/'app.py'),default_timeout=60).run()
def check(label):
 errors=[e.message for e in app.exception]
 if errors: raise AssertionError((label,errors))
 print(label,'OK',flush=True)
check('Overview full export')
for view in ['Scrap','Repair economics','Inventory & timing','Review queue','Data quality']:
 app.sidebar.radio[0].set_value(view).run();check(view)
 if view=='Scrap':
  for group in ['subtype','module_subtype','module']:
   app.selectbox(key='scrap_group').set_value(group).run();check('Scrap '+group)
 if view=='Repair economics':
  for group in ['subtype','module_subtype','part','module']:
   app.selectbox(key='economics_group').set_value(group).run();check('Repair '+group)
  app.checkbox(key='economics_dates_enabled').check().run();check('Repair date filter')
 if view=='Inventory & timing':
  for group in ['warehouse','condition','part','subtype','module']:
   app.selectbox(key='stock_group').set_value(group).run();check('Stock '+group)
  for group in ['subtype','module_subtype','module']:
   app.selectbox(key='timing_group').set_value(group).run();check('Timing '+group)
  app.checkbox(key='timing_dates_enabled').check().run();check('Timing date filter')
 if view=='Review queue':
  app.multiselect(key='queue_statuses').set_value(['Insufficient evidence']).run();check('Queue insufficient evidence')
  app.multiselect(key='queue_statuses').set_value([]).run();check('Empty queue status filter')
app.sidebar.text_input[0].set_value('NO-MATCH-EXAMPLE-987654321').run()
for view in ['Overview','Scrap','Repair economics','Inventory & timing','Review queue','Data quality']:
 app.sidebar.radio[0].set_value(view).run();check('Empty '+view)
print('FULL EXPORT CHECKS PASSED',flush=True)
