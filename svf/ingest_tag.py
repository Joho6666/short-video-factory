"""入库打标:免费的客观指标 + 视觉模型看分镜表打标签。

用法:
  ingest_tag.py metrics              # 给素材索引每段加 清晰度/亮度/运动量/质量分(本地计算,不花 token)
  ingest_tag.py sheets [N] [--todo]  # 每段取 首/中/尾 三帧,N 段一张表(默认 12),写 数据/tag_tasks/(--todo 只出还没打标的)
  ingest_tag.py apply 标签.json ...   # 校验并合并视觉模型给出的标签(默认只预演,加 --write 才写回)
  ingest_tag.py status               # 统计已打标/未打标

视觉模型不绑定:谁都行,只要按 templates/tag_schema.json 的格式写出 {"素材label": {shot, brand, quality, position, risk, note}}。
  - 默认做法:在 Claude Code 会话里让 Claude 看 数据/tag_tasks/NN.jpg,把结果写成 tags_NN.json
  - 以后可换 API 模型(如火山方舟 doubao 视觉模型),只要产出同格式 JSON 即可
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import cv2, json, os, sys, shutil, numpy as np
from config import R
from risk import BAD

IDX = R + '/数据/素材索引.json'


def prev_path(k, v):
    if v.get('预览'):
        return v['预览']
    f = os.path.join(R, '预览60', v['文件'].replace('/', os.sep))
    if not os.path.exists(f):
        f = os.path.join(R, '预览', v['文件'].replace('/', os.sep))
    return f


def frames(path, n=3):
    c = cv2.VideoCapture(path)
    tot = int(c.get(7)); out = []
    for i in range(n):
        c.set(cv2.CAP_PROP_POS_FRAMES, int(tot * (i + 0.5) / n))
        ok, fr = c.read()
        out.append(fr if ok else None)
    return out


def metrics(path):
    c = cv2.VideoCapture(path)
    tot = int(c.get(7))
    sh, br, mo, prev = [], [], [], None
    for i in range(8):
        c.set(cv2.CAP_PROP_POS_FRAMES, int(tot * (i + 0.5) / 8))
        ok, fr = c.read()
        if not ok:
            continue
        g = cv2.cvtColor(cv2.resize(fr, (270, 480)), cv2.COLOR_BGR2GRAY)
        sh.append(cv2.Laplacian(g, cv2.CV_64F).var())
        br.append(g.mean())
        if prev is not None:
            mo.append(float(np.abs(g.astype(np.int16) - prev).mean()))
        prev = g.astype(np.int16)
    return (float(np.median(sh)) if sh else 0, float(np.mean(br)) if br else 0, float(np.mean(mo)) if mo else 0)


def cmd_metrics():
    d = json.load(open(IDX, encoding='utf-8'))
    for i, (k, v) in enumerate(d.items()):
        v['清晰度'], v['亮度'], v['运动量'] = [round(x, 1) for x in metrics(prev_path(k, v))]
    sharps = sorted(v['清晰度'] for v in d.values())
    lo, hi = sharps[len(sharps) // 10], sharps[len(sharps) * 9 // 10]
    for v in d.values():
        s = (v['清晰度'] - lo) / max(hi - lo, 1e-6)
        dark = 0 if 60 < v['亮度'] < 200 else 0.3
        v['质量分'] = round(max(0, min(1, s)) * 4 + 1 - dark * 2, 1)  # 1~5
    json.dump(d, open(IDX, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('metrics done', len(d))


def label_of(k):
    return k[-8:]


def cmd_sheets(n=12, todo=False):
    d = json.load(open(IDX, encoding='utf-8'))
    out = R + '/数据/tag_tasks'
    os.makedirs(out, exist_ok=True)
    keys = [k for k in d if not (todo and d[k].get('AI标签'))]
    labels = [label_of(k) for k in keys]
    assert len(set(labels)) == len(labels), 'label 重复,无法在分镜表里区分素材'
    manifest = {}
    for s in range(0, len(keys), n):
        rows = []
        for k in keys[s:s + n]:
            fr = frames(prev_path(k, d[k]))
            ims = []
            for f in fr:
                f = cv2.resize(f, (200, 356)) if f is not None else np.zeros((356, 200, 3), np.uint8)
                ims.append(f)
            ims[0] = ims[0].copy()
            cv2.rectangle(ims[0], (0, 0), (118, 24), (0, 0, 0), -1)
            cv2.putText(ims[0], label_of(k), (3, 17), 0, 0.55, (0, 255, 255), 1)
            rows.append(np.hstack(ims))
        if len(rows) % 2:
            rows.append(np.zeros_like(rows[0]))
        im = np.vstack([np.hstack(rows[i:i + 2]) for i in range(0, len(rows), 2)])
        no = f"{s // n + 1:02d}"
        open(f"{out}/{no}.jpg", 'wb').write(cv2.imencode('.jpg', im, [cv2.IMWRITE_JPEG_QUALITY, 82])[1].tobytes())
        manifest[no] = [label_of(k) for k in keys[s:s + n]]
    json.dump(manifest, open(out + '/manifest.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('sheets', len(manifest), '->', out)


def schema():
    return json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates', 'tag_schema.json'), encoding='utf-8'))


def validate(tag):
    sc = schema()
    errs = []
    if tag.get('shot') not in sc['shot']:
        errs.append(f"shot={tag.get('shot')}")
    if tag.get('position') not in sc['position']:
        errs.append(f"position={tag.get('position')}")
    if tag.get('quality') not in (1, 2, 3, 4, 5):
        errs.append(f"quality={tag.get('quality')}")
    for r in tag.get('risk', []):
        if r not in BAD:
            errs.append(f'risk 不在 BAD 里: {r}')
    return errs


def cmd_apply(files, write):
    d = json.load(open(IDX, encoding='utf-8'))
    by_label = {label_of(k): k for k in d}
    stat = {'ok': 0, 'bad': 0, 'unknown': 0, 'new_risk': 0}
    for f in files:
        for lab, tag in json.load(open(f, encoding='utf-8')).items():
            k = by_label.get(lab)
            if not k:
                stat['unknown'] += 1
                print('未知素材', lab)
                continue
            es = validate(tag)
            if es:
                stat['bad'] += 1
                print('✗', lab, es)
                continue
            new = [r for r in tag.get('risk', []) if r not in d[k]['标记']]
            if new:
                stat['new_risk'] += 1
                print(f'  新增风险 {lab}: {new}  ({tag.get("note", "")})')
            if write:
                d[k]['AI标签'] = {x: tag.get(x) for x in ('shot', 'brand', 'quality', 'position', 'risk', 'note')}
                d[k]['标记'] = list(d[k]['标记']) + new
                if new:
                    d[k]['AI新增风险'] = new
            stat['ok'] += 1
    print(stat)
    if write:
        shutil.copy(IDX, IDX.replace('.json', '.bak_apply.json'))
        json.dump(d, open(IDX, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('已写回', IDX)
    else:
        print('(预演,未写回;确认无误后加 --write)')


def cmd_status():
    d = json.load(open(IDX, encoding='utf-8'))
    n = sum(1 for v in d.values() if v.get('AI标签'))
    print(f'已打标 {n} / {len(d)};AI 新增风险 {sum(1 for v in d.values() if v.get("AI新增风险"))} 段')


if __name__ == '__main__':
    a = sys.argv[1:] or ['status']
    if a[0] == 'metrics':
        cmd_metrics()
    elif a[0] == 'sheets':
        nums = [x for x in a[1:] if x.isdigit()]
        cmd_sheets(int(nums[0]) if nums else 12, '--todo' in a)
    elif a[0] == 'apply':
        cmd_apply([x for x in a[1:] if not x.startswith('--')], '--write' in a)
    else:
        cmd_status()
