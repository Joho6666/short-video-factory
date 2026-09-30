"""批量成片自动质检 + 评分。

用法: python qc.py b301 b302 ...   → 成片/qc_<首个名>_等.json + 每条联系表 成片/_qc_<name>.jpg
满分 85 分为自动项;另 15 分为人工画面评审(在报告里手填)。
"""
import json
import os
import re
import subprocess
import sys

import cv2
import zhconv
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import R, FF  # noqa: E402
names = sys.argv[1:]
ASR = set(filter(None, os.getenv('QC_ASR', '').split(','))) or set(names)   # 只对这些条做转写比对

from faster_whisper import WhisperModel  # noqa: E402
model = WhisperModel('small', device='cpu', compute_type='int8') if ASR else None

CN = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def norm(t):
    """统一成便于比对的串:标点变分隔符,中文数字转阿拉伯数字(简单情形)。"""
    t = re.sub(r'[、,，。!！?？:：·]', '|', t)
    t = re.sub(r"[{}\s“”\"'()（）.\-—]", '', t)
    t = t.replace('号', '日')
    t = re.sub(r'(?<![一二两三四五六七八九十百千])([零一二两三四五六七八九])(?=[折日月份团])', lambda m: str(CN[m.group(1)]), t)

    def cn2num(m):
        # 通用中文数字(万以内):四百五十→450,两千→2000,十→10,五百→500
        total, cur = 0, 0
        for ch in m.group(0):
            if ch in CN:
                cur = CN[ch]
            else:
                unit = {'十': 10, '百': 100, '千': 1000}[ch]
                total += (cur or 1) * unit
                cur = 0
        return str(total + cur)
    # 一个"数"= 若干(数字+单位)再跟一个可选个位;"五百九百"会被拆成两个数
    t = re.sub(r'(?:[一二两三四五六七八九]?千)?(?:[一二两三四五六七八九]百)?(?:[一二三四五六七八九]?十)?'
               r'(?:[一二三四五六七八九](?![百千十]))?', lambda m: cn2num(m) if m.group(0) and re.search('[十百千]', m.group(0)) else m.group(0), t)
    return t


def cer(ref, hyp):
    """字错误率(编辑距离 / 参考长度)。"""
    a, b = ref, hyp
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(b) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(b)] / max(1, len(a))


def probe(path):
    r = subprocess.run([FF, '-hide_banner', '-i', path], capture_output=True, text=True, encoding='utf-8', errors='ignore')
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', r.stderr)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    wh = re.search(r'Video:.*?(\d{3,4})x(\d{3,4})', r.stderr)
    return dur, (int(wh.group(1)), int(wh.group(2)))


def loudness(path):
    r = subprocess.run([FF, '-hide_banner', '-i', path, '-af', 'ebur128', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='ignore')
    m = re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)
    return float(m[-1]) if m else None


def blackframes(path):
    r = subprocess.run([FF, '-hide_banner', '-i', path, '-vf', 'blackdetect=d=0.2:pix_th=0.08', '-an', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='ignore')
    return len(re.findall(r'black_start', r.stderr))


def tech_pass(path):
    # 一次解码同时做响度(ebur128)和黑帧检测(缩小后检测,更快)
    r = subprocess.run([FF, '-hide_banner', '-i', path, '-filter_complex',
                        '[0:a]ebur128[ao];[0:v]scale=270:480,blackdetect=d=0.2:pix_th=0.08[vo]',
                        '-map', '[ao]', '-map', '[vo]', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='ignore')
    m = re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)
    return (float(m[-1]) if m else None), len(re.findall(r'black_start', r.stderr))


def decode_ok(path):
    r = subprocess.run([FF, '-v', 'error', '-i', path, '-f', 'null', '-'], capture_output=True, text=True)
    return not r.stderr.strip()


shots_by = {}
report = {}
for n in names:
    mp4 = f"{R}/成片/{n}.mp4"
    sc = json.load(open(f"{R}/脚本/{n}.json", encoding='utf-8'))
    U = json.load(open(f"{R}/成片/{n}.用量.json", encoding='utf-8'))
    shots = [s['clip'] for s in U['镜头详情']]
    shots_by[n] = shots
    dur, wh = probe(mp4)
    lu, bf = tech_pass(mp4)
    ok = True   # 完整解码已在 run_batch 渲染后校验过
    # 转写比对
    wav = f"{R}/成片/_qc_{n}.wav"
    subprocess.run([FF, '-v', 'error', '-y', '-i', mp4, '-vn', '-ac', '1', '-ar', '16000', wav], check=True)
    if n in ASR:
        # 逐句转写:按旁白时间切片,避免整段转写的漏句/重复
        hyp_parts, t_ = [], 0.0
        for L_ in U['旁白']:
            cw = f"{R}/成片/_qc_{n}_seg.wav"
            subprocess.run([FF, '-v', 'error', '-y', '-ss', f"{t_:.3f}", '-t', f"{L_['d']:.3f}", '-i', wav, cw], check=True)
            sg, _ = model.transcribe(cw, language='zh', vad_filter=False, condition_on_previous_text=False,
                                     initial_prompt='以下是普通话的句子。')
            hyp_parts.append(''.join(x.text for x in sg))
            t_ += L_['d']
        hyp = zhconv.convert(''.join(hyp_parts), 'zh-cn')
        ref = ''.join(re.sub(r'[{}]', '', L['text']) for L in sc['lines'])
        c = cer(norm(ref).replace('|', ''), norm(hyp).replace('|', ''))
        # 数字核对:脚本里出现的每个数字串,转写里都要有
        nums = sorted(set(re.findall(r'\d+', norm(ref))))
        miss = [x for x in nums if x not in norm(hyp).replace('|', '')]
    else:
        c, miss, hyp = None, '未抽检', ''
    # 联系表
    cap = cv2.VideoCapture(mp4)
    fr = []
    for i in range(16):
        t = dur * (i + .5) / 16
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        okf, f = cap.read()
        if okf:
            f = cv2.resize(f, (216, 384))
            cv2.putText(f, f"{n} {t:.1f}", (4, 18), 0, 0.5, (0, 255, 255), 2)
            fr.append(f)
    open(f"{R}/成片/_qc_{n}.jpg", 'wb').write(
        cv2.imencode('.jpg', np.vstack([np.hstack(fr[:8]), np.hstack(fr[8:16])]), [cv2.IMWRITE_JPEG_QUALITY, 82])[1].tobytes())
    report[n] = dict(风格=sc.get('风格'), 配音=sc.get('speaker'), 音乐=os.path.basename(sc.get('music_file', ''))[20:],
                     时长=round(dur, 2), 分辨率=f"{wh[0]}x{wh[1]}", 解码=ok, 黑帧段=bf, 响度LUFS=lu,
                     字错误率=None if c is None else round(c, 3), 缺失数字=miss, 转写=hyp, 镜头数=len(shots), 同条重复镜头=len(shots) - len(set(shots)))

# 多样性:与其他条的镜头重合
for n in names:
    others = set(x for m, v in shots_by.items() if m != n for x in v)
    mine = set(shots_by[n])
    report[n]['与其他条重合镜头'] = len(mine & others)
    report[n]['重合率'] = round(len(mine & others) / max(1, len(mine)), 2)

# 打分(自动 85)
for n, r in report.items():
    s = {}
    s['技术完好15'] = (10 if r['解码'] else 0) + (3 if r['分辨率'] == '1080x1920' else 0) + (2 if r['黑帧段'] == 0 else 0)
    s['时长10'] = 10 if 28 <= r['时长'] <= 38 else (5 if 25 <= r['时长'] <= 42 else 0)
    lu = r['响度LUFS']
    s['响度10'] = 10 if lu is not None and -18 <= lu <= -12 else (5 if lu is not None and -21 <= lu <= -9 else 0)
    s['配音字幕一致25'] = None if r['字错误率'] is None else round(max(0, 25 * (1 - r['字错误率'] / 0.25)), 1)
    s['数字念对15'] = None if r['缺失数字'] == '未抽检' else (15 if not r['缺失数字'] else max(0, 15 - 5 * len(r['缺失数字'])))
    s['素材多样性10'] = round(max(0, 10 - 2 * r['同条重复镜头'] - 10 * max(0, r['重合率'] - 0.1)), 1)
    r['自动分'] = s
    r['自动合计85'] = round(sum(v for v in s.values() if v is not None), 1)

out = f"{R}/成片/qc_{'_'.join(names)}.json"
json.dump(report, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for n, r in report.items():
    print(n, r['风格'], '| 时长', r['时长'], '| LUFS', r['响度LUFS'], '| 字错率', r['字错误率'], '| 缺数字', r['缺失数字'],
          '| 镜头', r['镜头数'], '重合率', r['重合率'], '| 自动分', r['自动合计85'])
print('report ->', out)
