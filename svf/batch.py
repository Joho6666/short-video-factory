"""一条命令批量出片:文案生成 → 合规 → 配音 → 渲染(并行) → 质检 → 报告。

用法:
    python svf/batch.py --n 10 --start 401 [-j 3] [--styles S1,S3,S4] [--qc-sample 0.3]
产出:
    脚本/b401.json …   成片/b401.mp4 …   成片/批次_b401-b410/(成片 + 抽帧 + 报告.md + 清单.csv)
规则:
    - 数字只来自明白卡白名单(project.json number_whitelist),禁用词拦截(banned_words)
    - 配音文本自动转中文读法(450团500 → 四百五十团五百),字幕仍显示阿拉伯数字
    - 默认整体语速 1.12;博主口播风格 1.2(甲方反馈:语速再快一点)
    - 时长控制在 28–36 秒:短了自动补可选句,长了自动删
"""
import argparse
import asyncio
import csv
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import R, FF, PY, WL, BANW, BAN_EXCEPT, SAY, PROJECT, CODE  # noqa: E402
from universal_tts import generate_voice_with_meta  # noqa: E402   (来自 jianying-editor skill:剪映 SAMI 配音)

# ------------------------------------------------------------------ 项目数据(全部来自项目目录,代码里不放客户内容)
_B = PROJECT.get('batch', {})
BRAND = PROJECT.get('brand_title', '品牌名')
BIG = {'disc': '', 'tuan': '', 'cake': '', 'end': '', **_B.get('big_cards', {})}   # 大字卡文字
MUSIC = {k: [x.replace('{project}', R) for x in v] for k, v in _B.get('music', {}).items()}
SPK = _B.get('speakers') or {s: ['zh_male_ad'] for s in ['S1', 'S2', 'S3', 'S4', 'S5']}
SPEED = _B.get('speed') or {'S1': 1.12, 'S2': 1.2, 'S3': 1.08, 'S4': 1.12, 'S5': 1.1}
STYLE_NAME = {'S1': '信息种草', 'S2': '博主口播', 'S3': '卡点混剪', 'S4': '清单体', 'S5': '美陈氛围'}
HOST_POOL = _B.get('host_pool', [])
HOST = {k: [tuple(x) for x in v] for k, v in _B.get('host_clips', {}).items()}      # 博主原声:(素材, 起点, 时长, 字幕)
HOST_INSERT = _B.get('host_inserts', {})                                            # 口播中间插入的空镜
REASONS = [tuple(x) for x in _B.get('reasons', [])]                                 # 清单体:(口播, 大字卡, 镜头类别, 展开句)
CN_NUM = "一二三四五"
_PF = R + '/数据/文案池.json'                                                       # 可编辑的文案池
P = json.load(open(_PF, encoding='utf-8')) if os.path.exists(_PF) else {}
P.setdefault('S2_OPEN', P.get('HOOK', ['']))


def plain(t):
    return re.sub(r'[{}]', '', t)


def spoken(t):
    t = plain(t)
    for a, b in SAY:
        t = t.replace(a, b)
    return t.replace('、', ',')


def check(lines):
    errs = []
    for L in lines:
        t = plain(L['text']) + ' ' + L.get('big', '')
        for w in BANW:
            if w in t and not any(x in t for x in BAN_EXCEPT):
                errs.append(f"极限词[{w}] {t}")
        for num in re.findall(r'\d+', t.replace('NO.', '')):
            if not any(num in w for w in WL):
                errs.append(f"数字不在明白卡[{num}] {t}")
    return errs


def L_(text, cats, **k):
    return dict(text=text, cats=cats, **k)


# ------------------------------------------------------------------ 5 种风格的脚本结构
from collections import Counter as _Counter
TXT_USED = _Counter()   # 本批各句子已用次数:优先选用得最少的说法


def build(style, rng):
    def c(lst):
        m = min(TXT_USED[x] for x in lst)
        x = rng.choice([y for y in lst if TXT_USED[y] == m])
        TXT_USED[x] += 1
        return x
    if style == 'S1':
        blocks = [
            [L_(c(P['DISC']), ["折扣活动墙"], big=BIG["disc"], tin="flash_zoomblur"), L_(c(P['MEMBER']), ["店内_服装"], host_last=True)],
            [L_(c(P['CATS']), ["门店招牌", "店内_耐克"], tin="whip_left")],
            [L_(c(P['TUAN']), ["店内_服装", "橱窗"], tin="flash_zoomblur", big=BIG["tuan"], sticker="推荐", sticker_lines=2),
             L_(c(P['COUPON']), ["店内_耐克"])],
            [L_(c(P['CAKE']), ["人潮_中庭"], big=BIG["cake"], tin="push_left")],
        ]
        rng.shuffle(blocks)
        core = [L_(c(P['HOOK']), ["人潮_中庭", "门店招牌", "入口外立面"], motion="zoom_in_slow"),
                L_(c(P['TITLE']), ["入口外立面"], tin="push_left", title=BRAND)]
        for b in blocks:
            core += b
        core.append(L_(c(P['END']), ["门店招牌", "入口外立面"], tin="zoom_blur", motion="zoom_in_fast", big=BIG["end"]))
        extras = [L_(c(P['FOOD']), ["美食_现场"]), L_(c(P['PARTY']), ["巡游演出", "人潮_中庭"]),
                  L_(c(P['MEICHEN']), ["美陈_麦田", "美陈_猫咪"]), L_(c(P['MUSIC']), ["人潮_中庭", "中庭街景"])]
        rng.shuffle(extras)
        opt = [(len(core) - 1, e) for e in extras]
        return core, opt
    if style == 'S2':
        dk, ck, ed = c(HOST['DAKA']), c(HOST['CAKE']), c(HOST['END'])
        core = [L_(c(P['S2_OPEN']),
                   ["人潮_中庭", "入口外立面"], title=BRAND),
                L_(_B.get("s2_disc_line", P["DISC"][0]), ["折扣活动墙", "店内_服装"], big=BIG["disc"], tin="flash_zoomblur"),
                L_(c(P['TUAN']), ["店内_耐克", "门店招牌"], big=BIG["tuan"]),
                dict(text=dk[3], host_audio=[dk[0], dk[1], dk[2]], shots=[[dk[0], dk[1]], HOST_INSERT.get("DAKA", [dk[0], dk[1]]), [dk[0], dk[1]]],
                     tin="push_left"),
                L_(c(P['PARTY']), ["巡游演出", "人潮_中庭"]),
                dict(text=ck[3], host_audio=[ck[0], ck[1], ck[2]], shots=[[ck[0], ck[1]], HOST_INSERT.get("CAKE", [ck[0], ck[1]]), [ck[0], ck[1]]],
                     big=BIG["cake"]),
                dict(text=ed[3], host_audio=[ed[0], ed[1], ed[2]], shots=[[ed[0], ed[1]], [ed[0], ed[1]]], tin="zoom_blur")]
        opt = [(3, L_(c(P['COUPON']), ["店内_服装"])), (5, L_(c(P['FOOD']), ["美食_现场"]))]
        return core, opt
    if style == 'S3':
        pool = list(P['S3'])
        head = [c(P['S3_HEAD']), c(P['S3_TITLE'])]
        tail = [pool[11], c(P['S3_END'])]
        mid = pool[2:11] + pool[13:]
        rng.shuffle(mid)
        cats = {head[0]: ["人潮_中庭"], head[1]: ["入口外立面"], tail[1]: ["入口外立面"]}
        big = _B.get('s3_big', {})
        mcat = _B.get('s3_cats', {})
        tins = ["flash_zoomblur", "whip_left", "push_left"]
        core = []
        for i, t in enumerate(head + mid[:9] + tail):
            d = L_(t, cats.get(t) or mcat.get(t) or rng.choice([["门店招牌"], ["店内_服装"], ["店内_耐克"], ["橱窗"]]), beat=True)
            if t in big:
                d['big'] = big[t]
            if i == 1:
                d.update(title=BRAND, tin="push_left")
            elif i in (4, 8):
                d['tin'] = rng.choice(tins)
            core.append(d)
        opt = [(len(core) - 2, L_(x, mcat.get(x) or ["店内_服装"], beat=True)) for x in mid[9:]]
        return core, opt
    if style == 'S4':
        rs = REASONS[:2] + rng.sample(REASONS[2:], 2)
        rng.shuffle(rs)
        n = len(rs)
        core = [L_(c(P['S4_OPEN']).replace('{N}', CN_NUM[n - 1]),
                   ["入口外立面", "人潮_中庭"],
                   title=_B.get("list_title", "{n}个理由").format(n=n))]
        for i, (t, b, cats, more) in enumerate(rs):
            core.append(L_(f"理由{CN_NUM[i]}:{t}{rng.choice(more)}", cats, big=f"NO.{i + 1} {b}",
                           tin=["push_left", "flash_zoomblur", "whip_left"][i % 3]))
        core.append(L_(c(P['END']), ["入口外立面", "门店招牌"], tin="zoom_blur", motion="zoom_in_fast"))
        extra = [r for r in REASONS if r not in rs]
        rng.shuffle(extra)
        opt = [(len(core) - 1, L_(f"理由五:{extra[0][0]}{rng.choice(extra[0][3])}", extra[0][2], big=f"NO.5 {extra[0][1]}", tin="push_left",
                                  _retitle=True))]
        return core, opt
    if style == 'S5':
        s5 = P['S5']
        pick = [c(P['S5_OPEN']), c([s5[1], s5[10]]), c([s5[2], s5[3]]), s5[4], s5[5], s5[6], c([s5[7], s5[10]])]
        cats = [["美陈_麦田"], ["美陈_麦田"], ["美陈_猫咪", "美陈_天使雕像"], ["美陈_麦田", "美陈_天使雕像"],
                ["人潮_中庭", "中庭街景"], ["店内_服装", "门店招牌"], ["入口外立面"]]
        core = [L_(t, cc) for t, cc in zip(pick, cats)]
        core[0]['motion'] = "zoom_in_slow"
        core[1]['host_last'] = True
        core[4]['tin'] = "zoom_blur"
        opt = [(3, L_(x, ["美陈_天使雕像", "氛围_5周年天使灯", "美陈_猫咪", "美陈_麦田"])) for x in [s5[2], s5[3], s5[9]] if x not in pick]
        return core, opt
    raise ValueError(style)


# ------------------------------------------------------------------ 配音(剪映 SAMI,带缓存,并发)
TTS_DIR = R + '/数据/tts_cache_sami'
os.makedirs(TTS_DIR, exist_ok=True)


def tts_path(text, spk):
    h = hashlib.md5(f"{spk}|{spoken(text)}".encode()).hexdigest()[:14]
    return f"{TTS_DIR}/{h}.wav"


async def tts_one(sem, text, spk):
    wav = tts_path(text, spk)
    if os.path.exists(wav):
        return wav
    async with sem:
        ogg = wav[:-4] + '.ogg'
        for attempt in range(3):
            r = await generate_voice_with_meta(spoken(text), ogg, spk, backend="sami", allow_fallback=False, sami_retries=2)
            if r and r[0] and os.path.exists(ogg):
                break
            await asyncio.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(f"TTS 失败: {text}")
        subprocess.run([FF, '-v', 'error', '-y', '-i', ogg, '-ar', '44100', '-ac', '1', wav], check=True)
        os.remove(ogg)
    return wav


async def tts_many(items, conc=4):
    sem = asyncio.Semaphore(conc)
    return await asyncio.gather(*[tts_one(sem, t, s) for t, s in items])


def wav_dur(p):
    w = wave.open(p)
    return w.getnframes() / w.getframerate()


def est_total(lines, spk, speed, gap):
    tot = 0.0
    for L in lines:
        d = L['host_audio'][2] if L.get('host_audio') else wav_dur(tts_path(L['text'], spk))
        tot += d / speed + gap
    return tot


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=5)
    ap.add_argument('--start', type=int, default=401)
    ap.add_argument('-j', type=int, default=3)
    ap.add_argument('--styles', default='S1,S2,S3,S4,S5')
    ap.add_argument('--qc-sample', type=float, default=0.3, help='抽多大比例做转写质检(0–1)')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--dry', action='store_true', help='只生成文案并统计重复度,不配音不渲染')
    a = ap.parse_args()
    styles = a.styles.split(',')
    T0 = time.time()
    tm = {}
    names, meta = [], {}
    seen = set()

    # 1) 文案 + 合规
    t = time.time()
    plans = []
    for i in range(a.n):
        no = a.start + i
        style = styles[i % len(styles)]
        for attempt in range(30):
            rng = random.Random(a.seed * 100000 + no * 100 + attempt)
            core, opt = build(style, rng)
            sig = hashlib.md5('|'.join(plain(x['text']) for x in core).encode()).hexdigest()
            if sig in seen:
                continue
            if not check(core + [o for _, o in opt]):
                break
        else:
            raise RuntimeError(f"b{no} 合规检查始终不过: {check(core + [o for _, o in opt])}")
        seen.add(sig)
        spk = rng.choice(SPK[style])
        plans.append(dict(no=no, style=style, core=core, opt=opt, spk=spk, rng=rng))
    tm['文案+合规'] = time.time() - t
    if a.dry:
        from collections import Counter
        hooks = [plain(p['core'][0]['text']) for p in plans]
        allx = [plain(x['text']) for p in plans for x in p['core']]
        print(f"预演 {len(plans)} 条:开头句不同 {len(set(hooks))}/{len(hooks)};句子不重复 {len(set(allx))}/{len(allx)};"
              f"整条文案完全相同 {len(plans) - len({'|'.join(plain(x['text']) for x in p['core']) for p in plans})} 条")
        print('开头最常见:', Counter(hooks).most_common(3))
        return

    # 2) 配音(含可选句,便于控时长)
    t = time.time()
    items = {(x['text'], p['spk']) for p in plans for x in p['core'] + [o for _, o in p['opt']] if not x.get('host_audio')}
    asyncio.run(tts_many(sorted(items)))
    tm['配音'] = time.time() - t

    # 3) 控时长 + 写脚本
    for p in plans:
        style, rng = p['style'], p['rng']
        gap = {'S3': 0.25, 'S5': 0.3}.get(style, 0.12)
        lines = list(p['core'])
        opt = list(p['opt'])
        while est_total(lines, p['spk'], SPEED[style], gap) < 28 and opt:
            pos, o = opt.pop(0)
            lines.insert(min(pos, len(lines) - 1), o)
        while est_total(lines, p['spk'], SPEED[style], gap) > 36 and len(lines) > 5:
            cand = [k for k in range(1, len(lines) - 1) if not lines[k].get('host_audio') and not lines[k].get('title')]
            if not cand:
                break
            lines.pop(cand[len(cand) // 2])
        if any(x.pop('_retitle', False) for x in lines):
            lines[0] = dict(lines[0], text=lines[0]['text'].replace('四个', '五个'), title=_B.get("list_title", "{n}个理由").format(n=5))
            asyncio.run(tts_many([(lines[0]['text'], p['spk'])]))
        for L in lines:
            L.pop('_retitle', None)
            if not L.get('host_audio'):
                L['wav'] = tts_path(L['text'], p['spk'])
        name = f"b{p['no']}"
        sc = dict(name=name, template="B_信息种草", batch=f"b{a.start}", seed=p['no'], host_pool=HOST_POOL,
                  style_id=style, 风格=STYLE_NAME[style], speaker=p['spk'], speed=SPEED[style], gap=gap,
                  music_file=rng.choice(MUSIC[style]), music_vol={'S2': 0.16, 'S3': 0.3, 'S5': 0.3}.get(style, 0.22),
                  lines=lines)
        if style == 'S3':
            sc['style'] = dict(caption=dict(size=92, center_y=1250, max_chars=9, stroke=9))
        if style == 'S4':
            sc['style'] = dict(big_card=dict(size=120, center_y=640))
        if style == 'S5':
            sc['style'] = dict(caption=dict(size=58, stroke=5, center_y=1480, highlight=False),
                               shot=dict(max=2.6, zoom_amount=0.05, motion_pool=["zoom_in_slow", "zoom_out_slow"]))
        json.dump(sc, open(f"{R}/脚本/{name}.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        names.append(name)
        meta[name] = dict(风格=STYLE_NAME[style], 配音=p['spk'], 预估时长=round(est_total(lines, p['spk'], SPEED[style], gap), 1),
                          句数=len(lines), 文案=' | '.join(plain(x['text']) for x in lines))
        print(name, STYLE_NAME[style], meta[name]['预估时长'], 's', len(lines), '句', flush=True)

    # 4) 渲染(并行)
    t = time.time()
    subprocess.run([PY, os.path.join(CODE, 'run_batch.py'), '-j', str(a.j)] + names, check=False,
                   env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    tm['渲染+校验+草稿'] = time.time() - t

    # 5) 质检(抽样转写 + 全量抽帧/响度/时长)
    t = time.time()
    ok = [n for n in names if os.path.exists(f"{R}/成片/{n}.mp4")]
    k = max(1, round(len(ok) * a.qc_sample)) if ok else 0
    sample = random.Random(a.start).sample(ok, k) if k else []
    if ok:
        subprocess.run([PY, os.path.join(CODE, 'qc.py')] + ok, env={**os.environ, 'PYTHONIOENCODING': 'utf-8',
                                                               'QC_ASR': ','.join(sample)}, check=False)
    tm['质检'] = time.time() - t

    # 6) 交付目录 + 报告
    out = f"{R}/成片/批次_{names[0]}-{names[-1]}"
    os.makedirs(out, exist_ok=True)
    qcf = f"{R}/成片/qc_{'_'.join(ok)}.json"
    qc = json.load(open(qcf, encoding='utf-8')) if os.path.exists(qcf) else {}
    rows = []
    for n in names:
        m = meta[n]
        q = qc.get(n, {})
        if os.path.exists(f"{R}/成片/{n}.mp4"):
            shutil.copy(f"{R}/成片/{n}.mp4", f"{out}/{n}_{m['风格']}.mp4")
            if os.path.exists(f"{R}/成片/_qc_{n}.jpg"):
                shutil.copy(f"{R}/成片/_qc_{n}.jpg", f"{out}/{n}_抽帧.jpg")
        rows.append(dict(编号=n, 风格=m['风格'], 配音=m['配音'], 时长=q.get('时长'), 响度=q.get('响度LUFS'),
                         黑帧=q.get('黑帧段'), 重合率=q.get('重合率'), 缺失数字=q.get('缺失数字', '未抽检'),
                         状态='OK' if os.path.exists(f"{R}/成片/{n}.mp4") else 'FAIL', 文案=m['文案']))
    with open(f"{out}/清单.csv", 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    total = time.time() - T0
    rep = [f"# 批次 {names[0]}–{names[-1]}", "",
           f"- 条数 {len(names)},成功 {len(ok)};总耗时 {total / 60:.1f} 分钟,平均 {total / max(1, len(ok)):.0f} 秒/条",
           "- 各环节耗时:" + ",".join(f"{k} {v:.0f}s" for k, v in tm.items()),
           f"- 付费调用 0 次(剪映 SAMI 配音 + 剪映云端音乐 + 本机渲染)",
           f"- 转写抽检:{', '.join(sample) or '无'}", "", "| 编号 | 风格 | 时长 | 响度 | 缺失数字 | 状态 |", "|---|---|---|---|---|---|"]
    rep += [f"| {r['编号']} | {r['风格']} | {r['时长']} | {r['响度']} | {r['缺失数字']} | {r['状态']} |" for r in rows]
    open(f"{out}/报告.md", 'w', encoding='utf-8').write('\n'.join(rep))
    print('\n'.join(rep))
    print('交付目录:', out)


if __name__ == '__main__':
    main()
