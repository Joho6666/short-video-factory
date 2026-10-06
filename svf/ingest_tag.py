"""入库打标(阶段一:免费的客观指标 + 供视觉模型看的分镜表)。

用法:
  ingest_tag.py metrics            # 给素材索引每段加 清晰度/亮度/运动量/质量分(本地计算,不花 token)
  ingest_tag.py sheets [N]         # 每段取 首/中/尾 三帧,按 N 段一张表(默认 12),给视觉模型看
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import cv2, json, os, sys, numpy as np
from config import R

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


def cmd_sheets(n=12):
    d = json.load(open(IDX, encoding='utf-8'))
    os.makedirs(R + '/联系表/分镜', exist_ok=True)
    keys = list(d)
    for s in range(0, len(keys), n):
        rows = []
        for k in keys[s:s + n]:
            fr = frames(prev_path(k, d[k]))
            ims = []
            for f in fr:
                f = cv2.resize(f, (180, 320)) if f is not None else np.zeros((320, 180, 3), np.uint8)
                ims.append(f)
            ims[0] = ims[0].copy()
            cv2.rectangle(ims[0], (0, 0), (110, 22), (0, 0, 0), -1)
            cv2.putText(ims[0], k[-8:], (3, 16), 0, 0.5, (0, 255, 255), 1)
            rows.append(np.hstack(ims))
        # 每行放 2 段
        if len(rows) % 2:
            rows.append(np.zeros_like(rows[0]))
        im = np.vstack([np.hstack(rows[i:i + 2]) for i in range(0, len(rows), 2)])
        name = f"{R}/联系表/分镜/{s // n + 1:02d}.jpg"
        open(name, 'wb').write(cv2.imencode('.jpg', im, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes())
    print('sheets', (len(keys) + n - 1) // n)


if __name__ == '__main__':
    a = sys.argv[1:] or ['metrics']
    if a[0] == 'metrics':
        cmd_metrics()
    else:
        cmd_sheets(int(a[1]) if len(a) > 1 else 12)
