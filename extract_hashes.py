#!/usr/bin/env python3
"""Extract hashes from CMS export files."""
import re
import os

def extract_hashes(xml_path):
    with open(xml_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    hashes = {}
    for attr in ['ContentTypeHash', 'ContentTypeHeadHash', 'ContentTypeRulesHash', 'ContentTypeMetasHash', 'ContentTypeHeadHashV2']:
        match = re.search(rf'{attr}="([^"]+)"', content)
        if match:
            hashes[attr] = match.group(1)
    return hashes

# OMS
print('=== OMS Hashes ===')
oms_hashes = extract_hashes(r'C:\temp\cms-ref-2026\Common\CampaignWizardOmsTemplate\es-ar-ba\ContentList.xml')
for k, v in oms_hashes.items():
    print(f'    "{k}": "{v}",')

# SMS
print('\n=== SMS Hashes ===')
sms_dir = r'C:\temp\cms-ref-sms\Common\CampaignWizardSmsTemplate'
if os.path.exists(sms_dir):
    sms_files = [f for f in os.listdir(sms_dir) if os.path.isdir(os.path.join(sms_dir, f))]
    if sms_files:
        sms_hashes = extract_hashes(os.path.join(sms_dir, sms_files[0], 'ContentList.xml'))
        for k, v in sms_hashes.items():
            print(f'    "{k}": "{v}",')

# TC
print('\n=== TC Hashes ===')
tc_dir = r'C:\temp\cms-ref-tc\Common\CampaignWizardTCTemplate'
if os.path.exists(tc_dir):
    tc_files = [f for f in os.listdir(tc_dir) if os.path.isdir(os.path.join(tc_dir, f))]
    if tc_files:
        tc_hashes = extract_hashes(os.path.join(tc_dir, tc_files[0], 'ContentList.xml'))
        for k, v in tc_hashes.items():
            print(f'    "{k}": "{v}",')
