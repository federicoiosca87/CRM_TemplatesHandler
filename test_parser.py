"""Quick test script for word parser"""
import importlib
import word_parser
importlib.reload(word_parser)

from word_parser import parse_word_document
from pathlib import Path

doc = parse_word_document(Path(r'C:\temp\cms-analysis\Bet&Get_CashFreespin\Sett. Bet & Cash Free Spins -- 1550\EN_bet_on_sb_get_CFS.docx'))

print('=== SMS ===')
if doc.sms:
    for t in doc.sms.templates:
        body_preview = (t.body or "")[:60]
        print(f'Template {t.variant}: {body_preview}...')
else:
    print('No SMS found')
    
print('\n=== OMS Launch ===')
if doc.launch_oms:
    for t in doc.launch_oms.templates:
        title = t.title[:50] if t.title else "No title"
        print(f'Template {t.variant}: Title={title}')
else:
    print('No OMS Launch found')

print('\n=== OMS Reminder ===')
if doc.reminder_oms:
    for t in doc.reminder_oms.templates:
        title = t.title[:50] if t.title else "No title"
        print(f'Template {t.variant}: Title={title}')
else:
    print('No OMS Reminder found')

print('\n=== TC ===')
if doc.tc:
    sig = (doc.tc.significant_terms or "")[:80]
    tc_full = (doc.tc.terms_and_conditions or "")[:80]
    print(f'Sig Terms: {sig}...')
    print(f'Full T&C: {tc_full}...')
else:
    print('No TC found')
