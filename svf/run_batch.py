"""批量渲染一批脚本,并为每条生成剪映草稿。

用法: python run_batch.py [-j 3] b101 b102 ...
- 渲染用显卡编码(NVENC),默认同时跑 3 条(-j 调整;内存 16GB 下建议 ≤4)
- 每条:渲染 → 完整解码校验 → 剪映草稿
日志: 成片/batch.log;每条完成追加 "OK name 秒数"
"""
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import R, FF, CODE  # noqa: E402
PY = sys.executable
args = sys.argv[1:]
jobs = 3
if args[:1] == ['-j']:
    jobs, args = int(args[1]), args[2:]
log = open(R + '/成片/batch.log', 'a', encoding='utf-8')
lock = threading.Lock()
ENV = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'AVD_SHOT_WORKERS': str(max(2, 8 // jobs))}


def say(s):
    with lock:
        log.write(s + '\n')
        log.flush()
        print(s, flush=True)


FAILED = []


def one(name, retry=False):
    t0 = time.time()
    r = subprocess.run([PY, os.path.join(CODE, 'render.py'), name], capture_output=True, text=True, encoding='utf-8', env=ENV)
    out = f"{R}/成片/{name}.mp4"
    if r.returncode != 0 or 'render 0' not in r.stdout or not os.path.exists(out):
        say(f"FAIL render {name}: {r.stdout[-300:]} {r.stderr[-300:]}")
        if not retry:
            FAILED.append(name)
        return
    chk = subprocess.run([FF, '-v', 'error', '-i', out, '-f', 'null', '-'], capture_output=True, text=True)
    if chk.stderr.strip():
        say(f"FAIL decode {name}: {chk.stderr[:200]}")
        return
    j = subprocess.run([PY, os.path.join(CODE, 'jy_draft.py'), name], capture_output=True, text=True, encoding='utf-8', env=ENV)
    jy = 'draft_ok' if 'draft saved' in j.stdout else 'draft_fail'
    say(f"OK {name} {time.time() - t0:.0f}s {jy}")


T0 = time.time()
with ThreadPoolExecutor(jobs) as ex:
    list(ex.map(one, args))
for n in FAILED:  # 并行时 NVENC 偶发 -22,失败的条单独串行重跑
    say(f'RETRY {n} (串行)')
    one(n, retry=True)
say(f'BATCH DONE {len(args)} 条 {time.time() - T0:.0f}s (并行 {jobs})')
