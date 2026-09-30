"""模板 B(信息种草)渲染器:旁白驱动 + 镜头运动 + 段落转场 + 标题花字 + 贴纸。

用法: python svf/render.py b001(项目目录由 config.json / SVF_PROJECT 决定)
脚本: 脚本/b001.json,结构见 脚本/b001.json;模板参数见 模板/B_信息种草.json
"""
import json, subprocess, sys, os, re, math, random, wave
import numpy as np
import time as _time
_TT=_time.time()
def _tick(lbl):
    global _TT
    print(f'[耗时] {lbl} {_time.time()-_TT:.1f}s', flush=True); _TT=_time.time()
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tts import synth, dur
from config import R, FF, WL, BANW, BAN_EXCEPT

name = sys.argv[1]
sc = json.load(open(f"{R}/脚本/{name}.json", encoding='utf-8'))
_tp = f"{R}/模板/B_信息种草.json"
if not os.path.exists(_tp):          # 项目没有自带模板时,用仓库 templates/ 里的
    _tp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates', 'B_信息种草.json')
TPL = json.load(open(_tp, encoding='utf-8'))
for _k in ('caption', 'title_sticker', 'big_card', 'shot'):      # 每条脚本可覆盖风格参数
    if _k in sc.get('style', {}):
        TPL[_k] = {**TPL[_k], **sc['style'][_k]}
idx = json.load(open(R + '/数据/素材索引.json', encoding='utf-8'))
BAD = ('路人或儿童正脸', '含明星肖像(版权肖像风险)', '品牌自带折扣牌(与全场2折起不同)', '拍摄者手指入镜', '画面虚焦/构图差', '第二位出镜者正脸', '汉堡节招牌可见(与国庆不符)')
FPS = int(os.getenv('AVD_FPS', '60'))
rng = random.Random(sc.get('seed', 1))
used = {}
# 同一批次共享的素材使用计数(顺序渲染,避免 5 条挑到同样的镜头)
GUSED_F = f"{R}/成片/_used_{sc['batch']}.json" if sc.get('batch') else None
gused = json.load(open(GUSED_F, encoding='utf-8')) if GUSED_F and os.path.exists(GUSED_F) else {}
work = f"{R}/成片/_work_{name}"
os.makedirs(work, exist_ok=True)

# xfade 名称映射(模板里的转场名 → ffmpeg xfade)
XF = {'cut': ('fade', 1 / FPS), 'push_left': ('slideleft', 0.17), 'flash_zoomblur': ('fadewhite', 0.2),
      'whip_left': ('hblur', 0.2), 'zoom_blur': ('zoomin', 0.17)}


def clip_path(n):
    e = idx[n]
    p = e.get('预览') or f"{R}/预览/{e['类别']}/2026-09-29 {n}.mp4"
    p60 = p.replace('/预览/', '/预览60/')
    return p60 if (FPS >= 60 and os.path.exists(p60)) else p


def plain(t):
    return re.sub(r'[{}]', '', t)


# ---------- 合规检查
errs = []
for L in sc['lines']:
    t = plain(L['text']) + ' ' + L.get('big', '')
    for w in BANW:
        if w in t and not any(x in t for x in BAN_EXCEPT):
            errs.append(('极限词', w, t))
    for num in re.findall(r'\d+', t):
        if not any(num in w for w in WL):
            errs.append(('数字不在白名单', num, t))
if errs:
    print('CHECK FAIL', errs)
    sys.exit(1)

# ---------- 配音
V, RT = sc.get('voice', '云扬'), sc.get('rate', '+10%')
GAP = sc.get('gap', TPL['voice']['gap_between_lines'])
for li_, L in enumerate(sc['lines']):
    if L.get('host_audio'):
        hc, hs, hd = L['host_audio']
        hw = f"{work}/host_{hc}_{hs}.wav"
        subprocess.run([FF, '-v', 'error', '-y', '-ss', str(hs), '-t', str(hd), '-i', clip_path(hc), '-vn', '-ac', '1',
                        '-ar', '44100', '-af', 'loudnorm=I=-16:TP=-1.5', hw], check=True)
        L['wav'] = hw
    L['_wav0'] = L.get('wav') or synth(plain(L['text']).replace('、', ','), V, RT, pitch=sc.get('pitch', '+0Hz'))
    SP = float(sc.get('speed', 1.0))
    if abs(SP - 1.0) > 1e-3:
        fw = f"{work}/tempo_{li_:02d}.wav"
        subprocess.run([FF, '-v', 'error', '-y', '-i', L['_wav0'], '-af', f'atempo={SP}', '-ar', '44100', fw], check=True)
        L['_wav'] = fw
    else:
        L['_wav'] = L['_wav0']
    L['_d'] = dur(L['_wav']) + GAP
T = sum(L['_d'] for L in sc['lines'])
print('旁白总长', round(T, 2)); _tick('配音/准备')


# ---------- 选镜头
def pick(cats, need, host=False):
    if host:
        c = [k for k in sc['host_pool'] if idx[k]['时长'] >= need + 0.3]
    else:
        c = [k for k, e in idx.items() if e['内容'] in cats and e['类别'] == '空镜' and '_重名' not in k
             and not any(b in e['标记'] for b in BAD) and e['时长'] >= need + 0.3 + e.get('min_ss', 0)]
    c.sort(key=lambda k: (used.get(k, 0) * 3 + gused.get(k, 0) * 2, rng.random()))
    k = c[0]
    used[k] = used.get(k, 0) + 1
    lo = idx[k].get('min_ss', 0.1)
    return k, round(rng.uniform(lo, max(lo, idx[k]['时长'] - need - 0.15)), 2)


import msvcrt as _ms
_LOCKF = open(f"{R}/成片/_pick.lock", 'a+')
while True:
    try:
        _LOCKF.seek(0)
        _ms.locking(_LOCKF.fileno(), _ms.LK_NBLCK, 1)
        break
    except OSError:
        _time.sleep(0.2)
gused = json.load(open(GUSED_F, encoding='utf-8')) if GUSED_F and os.path.exists(GUSED_F) else {}
shots = []   # dict(clip, ss, start, dur, motion, tin)
t0 = 0.0
MAXS = TPL['shot']['max']
BEATS = []


def detect_beats(path):
    # 解码音乐 → 低频能量通量 → 自相关求拍长 → 求相位,得到拍点序列(秒)
    tmp = f"{work}/_beat.wav"
    subprocess.run([FF, '-v', 'error', '-y', '-i', path, '-t', '60', '-ac', '1', '-ar', '11025', tmp], check=True)
    w = wave.open(tmp)
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float)
    sr, hop = 11025, 256
    frames = np.array([np.abs(np.fft.rfft(x[i:i + 1024] * np.hanning(1024)))[:40].sum() for i in range(0, len(x) - 1024, hop)])
    flux = np.maximum(0, np.diff(frames))
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    ac = np.correlate(flux, flux, 'full')[len(flux) - 1:]
    lags = np.arange(len(ac)) * hop / sr
    sel = (lags > 0.35) & (lags < 0.9)
    period = lags[sel][np.argmax(ac[sel])]
    P = int(round(period * sr / hop))
    phase = int(np.argmax([flux[p::P].sum() for p in range(P)]))
    return [(phase + i * P) * hop / sr for i in range((len(flux) - phase) // P)], period


if sc.get('music_file') and any(L.get('beat') for L in sc['lines']):
    BEATS, _period = detect_beats(sc['music_file'])
    print('音乐拍长', round(_period, 3), 's, 拍点', len(BEATS))
for li, L in enumerate(sc['lines']):
    d = L['_d']
    if 'shots' in L:                      # 明确指定镜头(照案例的剪辑清单)
        n_ = len(L['shots'])
        per = d / n_
        for si, (k, ss) in enumerate(L['shots']):
            avail_ = idx[k]['时长']
            need = per + 0.3
            if ss + need > avail_ - 0.05 and not L.get('host_audio'):
                ss = max(0.05, avail_ - need - 0.05)
            spd = 1.0
            if L.get('host_audio') and k == L['host_audio'][0]:
                spd = float(sc.get('speed', 1.0))
                ss = L['host_audio'][1] + si * per * spd  # 同一口播镜头:画面时间=音频时间(按加速换算)
            tin = L.get('tin', 'cut') if si == 0 else 'cut'
            motion = L.get('motion') if (si == 0 and L.get('motion')) else rng.choice(TPL['shot']['motion_pool'])
            shots.append(dict(clip=k, ss=round(ss, 3), start=t0, dur=per, motion=motion, tin=tin, spd=spd))
            t0 += per
        continue
    if L.get('beat') and BEATS:
        # 卡点:句内镜头边界 = 句内的拍点(相邻至少 0.45s)
        bs = [b for b in BEATS if t0 + 0.45 < b < t0 + d - 0.45]
        cuts, last = [], t0
        for b in bs:
            if b - last >= 0.45:
                cuts.append(b)
                last = b
        edges = [t0] + cuts + [t0 + d]
        for si in range(len(edges) - 1):
            seg_d = edges[si + 1] - edges[si]
            k, ss = pick(L.get('cats', []), seg_d + 0.25)
            tin = L.get('tin', 'cut') if si == 0 else 'cut'
            shots.append(dict(clip=k, ss=ss, start=edges[si], dur=seg_d, motion=rng.choice(TPL['shot']['motion_pool']), tin=tin))
        t0 += d
        continue
    ns = max(1, math.ceil(d / MAXS))
    per = d / ns
    for s in range(ns):
        is_host = (L.get('host_last') and s == ns - 1) or not L.get('cats')
        tin = L.get('tin', 'cut') if s == 0 else 'cut'
        xd = 0.25
        if 'clips' in L and s < len(L['clips']):
            k = L['clips'][s]
            ss = L.get('ss', [0.3] * 9)[s]
        else:
            k, ss = pick(L.get('cats', []), per + xd, is_host)
        motion = L.get('motion') if (s == 0 and L.get('motion')) else rng.choice(TPL['shot']['motion_pool'])
        if is_host:
            motion = 'zoom_in_slow'
        shots.append(dict(clip=k, ss=ss, start=t0, dur=per, motion=motion, tin=tin))
        t0 += per

if GUSED_F:
    for s_ in shots:
        gused[s_['clip']] = gused.get(s_['clip'], 0) + 1
    json.dump(gused, open(GUSED_F, 'w', encoding='utf-8'), ensure_ascii=False)
_LOCKF.seek(0)
_ms.locking(_LOCKF.fileno(), _ms.LK_UNLCK, 1)
_LOCKF.close()
# ---------- 每个镜头单独渲染(带运动)
A = TPL['shot']['zoom_amount']
ENC = os.getenv('AVD_ENC', 'nvenc')          # nvenc(显卡) / x264(CPU,备用)
VENC_MID = ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '18', '-g', '600', '-bf', '0'] if ENC == 'nvenc' else ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16']
jobs = []
F0 = [round(sh['start'] * FPS) for sh in shots] + [round(T * FPS)]
for i, s in enumerate(shots):
    nxt = shots[i + 1]['tin'] if i + 1 < len(shots) else 'cut'
    s['_xd_next'] = 0.0 if nxt == 'cut' else XF[nxt][1]
    s['_nf'] = F0[i + 1] - F0[i] + round(s['_xd_next'] * FPS)
    L_ = s['_nf'] / FPS + 0.1
    N = max(1, s['_nf'])
    m = s['motion']
    if m in ('zoom_in_slow', 'zoom_in_fast', 'zoom_out_slow'):
        a = 0.22 if m == 'zoom_in_fast' else A
        z = f"1+{a}*on/{N}" if m != 'zoom_out_slow' else f"{1 + a}-{a}*on/{N}"
        # 先 2 倍放大再 zoompan:取整误差缩小一半,运动速度波动 0.76→0.44(消除轻微抖动)
        vf = (f"scale=1620:2880:flags=bicubic,zoompan=z='{z}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1080x1920:fps={FPS}")
    else:  # 平移:先放大 8%,再用 crop 横移
        W2, H2 = 1752, 3114        # 1.5 倍分辨率下平移,最后缩回 1080x1920
        sx = f"(iw-1620)*t/{L_:.3f}" if m == 'pan_right' else f"(iw-1620)*(1-t/{L_:.3f})"
        vf = f"scale={W2}:{H2}:flags=bicubic,crop=1620:2880:x='{sx}':y='(ih-2880)/2',scale=1080:1920:flags=bicubic"
    out = f"{work}/s{i:02d}.mp4"
    spd_ = s.get('spd', 1.0)
    pre = f"setpts=PTS/{spd_},fps={FPS}," if abs(spd_ - 1.0) > 1e-3 else ''
    jobs.append([FF, '-v', 'error', '-y', '-ss', f"{s['ss']:.3f}", '-t', f"{L_ * spd_:.3f}", '-i', clip_path(s['clip']),
                 '-an', '-vf', f"fps={FPS}," + pre + vf + ',format=yuv420p,setsar=1', '-r', str(FPS), '-frames:v', str(s['_nf'])] + VENC_MID + [out])
    s['_file'] = out
    s['_len'] = L_
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(int(os.getenv('AVD_SHOT_WORKERS', '6'))) as _ex:
    for _r in _ex.map(lambda c: subprocess.run(c, capture_output=True, text=True), jobs):
        if _r.returncode != 0:
            raise RuntimeError('镜头渲染失败: ' + _r.stderr[-300:])
print('镜头数', len(shots)); _tick('逐镜头渲染')

# ---------- 字幕、花字、贴纸 PNG
CAP = TPL['caption']
FC = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', CAP['size'])
FT = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', TPL['title_sticker']['size'])
FS = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 84)
FA = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 30)


def blank():
    return Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))


def cap_png(text, mask, fn):
    # mask[i]=True 的字标黄
    im = blank()
    d = ImageDraw.Draw(im)
    w = d.textlength(text, font=FC)
    x, y = (1080 - w) / 2, CAP['center_y'] - CAP['size'] / 2
    for ch, hi in zip(text, mask):
        col = (255, 224, 0, 255) if hi else (255, 255, 255, 255)
        d.text((x + 4, y + 6), ch, font=FC, fill=(0, 0, 0, 110))
        d.text((x, y), ch, font=FC, fill=col, stroke_width=CAP['stroke'], stroke_fill=(15, 15, 15, 255))
        x += d.textlength(ch, font=FC)
    im.save(fn)


def hl_mask(text):
    # 把 {xx} 解析成 纯文本 + 每字是否高亮
    out, mask, on = '', [], False
    for ch in text:
        if ch == '{':
            on = True
        elif ch == '}':
            on = False
        else:
            out += ch
            mask.append(on)
    return out, mask


BC = TPL['big_card']
FB = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', BC['size'])


def hexc(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


def bigcard_pngs(text, prefix):
    # 生成弹出动画的每一帧(整屏 PNG),返回文件列表
    card = Image.new('RGBA', (1080, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    w = d.textlength(text, font=FB)
    if w > 1000:
        f2 = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', int(BC['size'] * 1000 / w))
    else:
        f2 = FB
    w = d.textlength(text, font=f2)
    x, y = (1080 - w) / 2, 200 - f2.size * 0.62
    d.text((x, y), text, font=f2, fill=hexc(BC['outer']), stroke_width=BC['stroke_w'] + 8, stroke_fill=hexc(BC['outer']))
    d.text((x, y), text, font=f2, fill=hexc(BC['fill']), stroke_width=BC['stroke_w'], stroke_fill=hexc(BC['stroke']))
    card = card.rotate(-4, resample=Image.BICUBIC)
    files = []
    for i, sc_ in enumerate(BC['pop']):
        im = blank()
        c2 = card.resize((int(1080 * sc_), int(400 * sc_)), Image.LANCZOS)
        im.paste(c2, (int((1080 - c2.width) / 2), int(BC['center_y'] - c2.height / 2)), c2)
        fn = f"{prefix}_{i}.png"
        im.save(fn)
        files.append(fn)
    return files


WORDS = ['全场', '会员', '折上再', '折上', '抖音团购', '抖音', '团购', '定制礼', '免费的', '免费', '蛋糕', '运动潮牌', '男装女装',
         '鞋子包包', '一站逛齐', '折后', '满额', '用券', '美食', '姐妹', '打卡', '分享', '持续', '一直', '活动', '约上', '出发', '谁懂啊']
try:
    from config import PROJECT as _PJ
    WORDS = list(dict.fromkeys(_PJ.get('caption_words', []) + WORDS))      # 项目专有词(品牌名/活动名)优先
except Exception:
    pass
_TOK = re.compile('|'.join(map(re.escape, sorted(WORDS, key=len, reverse=True))) + r'|[0-9A-Za-z.]+(?:[团月][0-9]+)?[折团日号份月起]*|NO\.[0-9]|.')


def split_cap(text, maxc):
    """先按标点分句;超长句在"词边界"上平衡切开(不劈开固定词、不留 ≤2 字的尾巴)。"""
    out = []
    for p in [p for p in re.split(r'[,，。!！?？、:：]', text) if p]:
        toks = _TOK.findall(p)
        if len(p) <= maxc:
            out.append(p)
            continue
        k = math.ceil(len(p) / maxc)                      # 需要几段
        cuts, acc, total = [], 0, len(p)
        bounds = []
        for tk in toks:
            acc += len(tk)
            bounds.append(acc)
        bounds = bounds[:-1]
        best, bestcost = None, 1e9
        import itertools
        for comb in itertools.combinations(bounds, k - 1):
            pts = [0, *comb, total]
            segs = [pts[i + 1] - pts[i] for i in range(k)]
            if min(segs) < 3 or max(segs) > maxc + 2:
                continue
            cost = max(segs) - min(segs)
            if cost < bestcost:
                best, bestcost = pts, cost
        if best is None:                                   # 实在切不出合法方案:退回均分(按词边界最近)
            step = total / k
            best = [0] + [min(bounds, key=lambda b: abs(b - step * (i + 1))) for i in range(k - 1)] + [total]
        out += [p[best[i]:best[i + 1]] for i in range(k)]
    return out


def title_png(text, k, fn):
    # 黄色马克笔色块 + 黑色粗体,前 k 个字可见
    im = blank()
    d = ImageDraw.Draw(im)
    w = d.textlength(text, font=FT)
    x0 = (1080 - w) / 2
    y0 = TPL['title_sticker']['y']
    fs_ = FT.size
    d.rounded_rectangle([x0 - 40, y0 + fs_ * 0.18, x0 + w + 40, y0 + fs_ * 1.42], radius=28, fill=(255, 224, 0, 255),
                        outline=(0, 0, 0, 255), width=5)
    x = x0
    for i, ch in enumerate(text):
        if i < k:
            d.text((x, y0), ch, font=FT, fill=(0, 0, 0, 255), stroke_width=3, stroke_fill=(255, 255, 255, 255))
        x += d.textlength(ch, font=FT)
    for sx, sy in [(x0 - 60, y0 - 5), (x0 + w + 44, y0 + 5)]:   # 两侧小闪光
        d.line([sx, sy, sx + 18, sy + 30], fill=(255, 224, 0, 255), width=6)
        d.line([sx + 22, sy - 4, sx + 30, sy + 26], fill=(255, 224, 0, 255), width=6)
    im.save(fn)


def sticker_png(text, fn):
    im = Image.new('RGBA', (520, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((20, 40), text, font=FS, fill=(255, 224, 0, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))
    tw = d.textlength(text, font=FS)
    cx, cy = 20 + tw + 40, 80   # 手画一个点赞星
    pts = [(cx + 30 * math.cos(a) * (1 if j % 2 == 0 else 0.45), cy + 30 * math.sin(a) * (1 if j % 2 == 0 else 0.45))
           for j, a in enumerate([-math.pi / 2 + j * math.pi / 5 for j in range(10)])]
    d.polygon(pts, fill=(255, 224, 0, 255), outline=(0, 0, 0, 255), width=4)
    im = im.rotate(8, resample=Image.BICUBIC, expand=True)
    big = blank()
    big.paste(im, (30, 400), im)
    big.save(fn)


ov = []   # (png, start, end)
cap_log = []
t0 = 0.0
for li, L in enumerate(sc['lines']):
    ptxt, pmask = hl_mask(L['text'])
    segs = split_cap(ptxt, CAP['max_chars'])
    tot = sum(len(p) for p in segs)
    c0 = t0
    cursor = 0
    for j, p in enumerate(segs):
        dd = (L['_d'] - GAP) * len(p) / tot
        pos = ptxt.find(p, cursor)
        cursor = pos + len(p)
        fn = f"{work}/cap{li}_{j}.png"
        cap_png(p, pmask[pos:pos + len(p)], fn)
        ov.append((fn, c0, c0 + dd + (GAP if j == len(segs) - 1 else 0)))
        cap_log.append(dict(text=p, mask=pmask[pos:pos + len(p)], start=round(c0, 3), end=round(c0 + dd + (GAP if j == len(segs) - 1 else 0), 3)))
        c0 += dd
    if L.get('title'):
        tt = L['title']
        ts = TPL['title_sticker']
        step = ts['anim_dur'] / len(tt)
        for k in range(1, len(tt) + 1):
            fn = f"{work}/title{k}.png"
            title_png(tt, k, fn)
            a = t0 + 0.12 + (k - 1) * step
            b = t0 + 0.12 + k * step if k < len(tt) else t0 + 0.12 + ts['anim_dur'] + ts['hold']
            ov.append((fn, a, b))
    if L.get('big'):
        fs = bigcard_pngs(L['big'], f"{work}/big{li}")
        a0 = t0 + 0.08
        for i, fn in enumerate(fs):
            a = a0 + i / FPS
            b = a0 + (i + 1) / FPS if i < len(fs) - 1 else t0 + L['_d'] - 0.05
            ov.append((fn, a, b))
    if L.get('sticker'):
        fn = f"{work}/stk{li}.png"
        sticker_png(L['sticker'], fn)
        end = t0 + sum(x['_d'] for x in sc['lines'][li:li + L.get('sticker_lines', 1)])
        ov.append((fn, t0 + 0.25, end))
    t0 += L['_d']
im = blank()
ImageDraw.Draw(im).text((40, 1830), '广告', font=FA, fill=(255, 255, 255, 210), stroke_width=2, stroke_fill=(0, 0, 0, 170))
im.save(work + '/ad.png')
ov.append((work + '/ad.png', 0, T + 1))

# ---------- 合成:镜头 xfade 链 + 叠加 + 音频
inp, fc = [], []
runs = [[shots[0]]]
for sh in shots[1:]:
    if sh['tin'] == 'cut':
        runs[-1].append(sh)
    else:
        runs.append([sh])
for ri, run in enumerate(runs):
    lst = f"{work}/run{ri:02d}.txt"
    open(lst, 'w', encoding='utf-8').write(''.join(f"file '{os.path.basename(x['_file'])}'\n" for x in run))
    rf = f"{work}/run{ri:02d}.mp4"
    subprocess.run([FF, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', rf], check=True)
    inp += ['-i', rf]
prev = '[0:v]'
for ri in range(1, len(runs)):
    tr, xd = XF[runs[ri][0]['tin']]
    lab = f'[x{ri}]'
    fc.append(f"{prev}[{ri}:v]xfade=transition={tr}:duration={xd:.3f}:offset={F0[shots.index(runs[ri][0])] / FPS:.3f}{lab}")
    prev = lab
n = len(runs)
last = prev
# 所有叠加层按时间切成区间,每个区间合成一张整屏 PNG,再用 concat 串成一条图层轨,只叠加一次
bounds = sorted({0.0, T} | {round(max(0, min(T, x)), 4) for _, a, b in ov for x in (a, b)})
cache = {}
lst = [f"ffconcat version 1.0"]
for a, b in zip(bounds[:-1], bounds[1:]):
    if b - a < 1e-3:
        continue
    mid = (a + b) / 2
    act = tuple(fn for fn, x, y in ov if x <= mid < y)
    if act not in cache:
        im = blank()
        for fn in act:
            layer = Image.open(fn).convert('RGBA')
            im.alpha_composite(layer)
        p = f"{work}/L{len(cache):03d}.png"
        im.save(p)
        cache[act] = p
    lst.append(f"file '{os.path.basename(cache[act])}'")
    lst.append(f"duration {b - a:.4f}")
lst.append(f"file '{os.path.basename(cache[act])}'")
open(f"{work}/layers.txt", 'w', encoding='utf-8').write(chr(10).join(lst))
inp += ['-f', 'concat', '-safe', '0', '-i', f"{work}/layers.txt"]
fc.append(f"[{n}:v]format=yuva420p,fps={FPS}[lay]")
fc.append(f"{last}[lay]overlay=0:0:shortest=0:eof_action=repeat:format=yuv420[vout]")
last = '[vout]'
n += 1
al = []
for L in sc['lines']:
    inp += ['-i', L['_wav']]
    fc.append(f"[{n}:a]aresample=48000,apad=whole_dur={L['_d']:.3f},aformat=channel_layouts=stereo[a{n}]")
    al.append(f'[a{n}]')
    n += 1
fc.append(''.join(al) + f"concat=n={len(al)}:v=0:a=1[na]")

# 背景音乐:有真实曲子用曲子,否则用合成占位
mf = sc.get('music_file')
if not mf:
    sr = 44100
    t = np.arange(int(sr * (T + 1))) / sr
    b = 60 / sc.get('bpm', 112)
    np.random.seed(sc.get('seed', 1))
    ph = t % b
    m = 0.8 * np.sin(2 * np.pi * (55 + 90 * np.exp(-ph * 30)) * ph) * np.exp(-ph * 9)
    ph8 = t % (b / 2)
    m += 0.05 * np.random.randn(len(t)) * np.exp(-ph8 * 60) * (((t // (b / 2)) % 2) == 1)
    ch = [(261.6, 329.6, 392), (196, 246.9, 392), (220, 261.6, 329.6), (174.6, 220, 261.6)]
    bar = (t // (4 * b)).astype(int) % 4
    idn = (t // (b / 2)).astype(int) % 3
    notes = np.zeros_like(t)
    for kk in range(4):
        for j in range(3):
            notes[(bar == kk) & (idn == j)] = ch[kk][j] * 2
    m += 0.18 * np.sin(2 * np.pi * notes * t) * np.exp(-ph8 * 7)
    m = m / np.abs(m).max() * 0.6
    mf = work + '/bed.wav'
    w = wave.open(mf, 'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((m * 32767).astype(np.int16).tobytes())
    w.close()
inp += ['-i', mf]
fc.append(f"[{n}:a]atrim=0:{T:.2f},asetpts=PTS-STARTPTS,volume={sc.get('music_vol', 0.30)},"
          f"afade=t=in:d=0.3,afade=t=out:st={T - 1:.2f}:d=1,aformat=channel_layouts=stereo[bd]")
fc.append("[na]loudnorm=I=-15:TP=-1.5:LRA=11,aresample=48000[nan]")
fc.append("[nan][bd]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[ao]")
out = f"{R}/成片/{name}.mp4"
cmd = [FF, '-v', 'error', '-y'] + inp + ['-filter_complex', ';'.join(fc), '-map', last, '-map', '[ao]',
                                         '-t', f"{T:.2f}"] + (['-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', '22', '-b:v', '9M', '-maxrate', '12M', '-bufsize', '18M'] if ENC == 'nvenc' else ['-c:v', 'libx264', '-crf', '20', '-preset', 'fast']) + [
                                         '-c:a', 'aac', '-b:a', '192k', out]
_tick('字幕图层生成'); r = subprocess.run(cmd, capture_output=True, text=True); _tick('最终合成编码')
print('render', r.returncode, r.stderr[-1500:])
json.dump(dict(script=name, 时长=round(T, 2), 镜头=[(s['clip'], s['motion'], s['tin'], round(s['start'], 2)) for s in shots],
               镜头详情=[dict(clip=s['clip'], ss=s['ss'], start=round(s['start'], 3), dur=round(s['dur'], 3), motion=s['motion'], tin=s['tin']) for s in shots],
               旁白=[dict(wav=L['_wav'], text=plain(L['text']), d=round(L['_d'], 3)) for L in sc['lines']], 字幕=cap_log, work=work,
               素材使用=used), open(f"{R}/成片/{name}.用量.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
