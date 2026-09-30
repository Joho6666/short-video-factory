"""把活动"明白卡"(xlsx)转成 数据/明白卡.json,并列出其中出现的数字,作为 project.json 白名单的候选。

用法: python svf/ingest_mingbaika.py <明白卡.xlsx> [sheet 名]
注意:白名单最终要人工确认后写进 project.json 的 number_whitelist —— 数字只能来自明白卡。
"""
import json
import os
import re
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import R  # noqa: E402

xlsx = sys.argv[1]
wb = openpyxl.load_workbook(xlsx)
ws = wb[sys.argv[2]] if len(sys.argv) > 2 else wb.worksheets[0]
rows = []
head = None
for r in ws.iter_rows(values_only=True):
    cells = [('' if c is None else str(c)).strip() for c in r]
    if not any(cells):
        continue
    if head is None and sum(1 for c in cells if c) >= 3:
        head = cells
        continue
    if head:
        rows.append({h or f'col{i}': v for i, (h, v) in enumerate(zip(head, cells)) if v})
os.makedirs(f"{R}/数据", exist_ok=True)
json.dump(rows, open(f"{R}/数据/明白卡.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
text = json.dumps(rows, ensure_ascii=False)
cands = sorted(set(re.findall(r'\d+(?:\.\d+)?(?:折|团\d+|月\d+日|日|号|份|张|元)?', text)), key=lambda x: (len(x), x))
print(f"写入 {R}/数据/明白卡.json,共 {len(rows)} 条活动")
print("明白卡中出现的数字(白名单候选,请人工挑选写入 project.json):")
print(', '.join(cands))
