"""口播模板:一段人对着镜头讲的原片 → 去静音/口癖的跳切 + 逐词卡拉 OK 字幕 + 钉在词上的空镜插画面 + 配乐。

用法:
  python svf/talk.py --video 口播原片.mp4 --name t001 [--music 曲.m4a] [--broll-every 5] [--max-gap 0.3] [--seed 1] [--no-broll]
产出: 成片/t001.mp4  +  成片/t001.talk.json(逐词时间、剪辑表、字幕、插画面,供复查)

要点(对应配方卡 talk-jumpcut / karaoke-caption / broll-cutaway):
  - 逐词时间戳来自 faster-whisper(word_timestamps),缓存在 数据/talk_cache/
  - 静音超过 --max-gap 的地方切掉;"嗯/呃/额"等独立口癖词整段删除;每个跳切点交替 100%/112% 推近,遮住接缝
  - 字幕按词边界分行,当前正在说的词变黄(出现时刻 = 该词开口时刻)
  - 空镜只换画面不换声音;插入点落在词边界,时长 1.4–2.2s;片头 2s、片尾 2.5s 保留人脸
"""
import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import R, FF, PROJECT, BANW, BAN_EXCEPT  # noqa: E402
from risk import BAD  # noqa: E402

import skeleton  # noqa: E402

FPS = int(os.getenv('AVD_FPS', '60'))
TPL = skeleton.load_all(R)['T1']              # 口播骨架:templates/skeletons/T1_口播.json(项目 模板/skeletons 可覆盖)
TP = TPL['params']
FILLERS = set(TP['fillers'])
FONT = 'C:/Windows/Fonts/msyhbd.ttc'
CAP = TP['caption']
HI = tuple(int(CAP['highlight'][i:i + 2], 16) for i in (1, 3, 5)) + (255,)
t0_ = time.time()


def tick(s):
    print(f'[耗时] {s} {time.time() - t0_:.1f}s', flush=True)


# ------------------------------------------------------------------ 1) 逐词转写(缓存)
def words_of(video, model='small'):
    h = hashlib.md5((os.path.abspath(video) + str(os.path.getsize(video)) + model).encode()).hexdigest()[:12]
    cache = f"{R}/数据/talk_cache/{h}.json"
    if os.path.exists(cache):
        return json.load(open(cache, encoding='utf-8'))
    from faster_whisper import WhisperModel
    from zhconv import convert
    m = WhisperModel(model, device='cpu', compute_type='int8')
    seg, _ = m.transcribe(video, language='zh', word_timestamps=True, initial_prompt=PROJECT.get('asr_prompt', '以下是普通话的句子。'))
    out = []
    for s in seg:
        for w in s.words or []:
            t = convert(w.word, 'zh-cn').strip()
            if t:
                out.append(dict(w=t, s=round(w.start, 3), e=round(w.end, 3)))
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(out, open(cache, 'w', encoding='utf-8'), ensure_ascii=False)
    return out


def bare(t):
    return re.sub(r'[,，。!！?？、:：;；…\s"“”\'‘’()（）]', '', t)


def to_chars(tokens):
    """whisper 的"词"(中文多半是 1~3 字)拆成逐字时间:词内均分。独立口癖词(嗯/呃…)直接丢弃。"""
    out = []
    for x in tokens:
        t = bare(x['w'])
        if not t or t in FILLERS:
            continue
        d = (x['e'] - x['s']) / len(t)
        for i, ch in enumerate(t):
            out.append(dict(w=ch, s=round(x['s'] + i * d, 3), e=round(x['s'] + (i + 1) * d, 3)))
    return out


def align_script(chars, script):
    """用正确文稿替换识别出的错字,保留时间:difflib 对齐,替换段按字数在原时间跨度内均分。"""
    import difflib
    ref = bare(script)
    a = ''.join(c['w'] for c in chars)
    sm = difflib.SequenceMatcher(None, a, ref, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            out += chars[i1:i2]
        elif tag in ('replace', 'insert'):
            if i2 > i1:
                s0, e0 = chars[i1]['s'], chars[i2 - 1]['e']
            else:   # 纯插入:挂在前一个字的末尾,占一个很短的时间
                s0 = chars[i1 - 1]['e'] if i1 > 0 else chars[0]['s']
                e0 = s0 + 0.04 * (j2 - j1)
            d = (e0 - s0) / (j2 - j1)
            out += [dict(w=ref[j], s=round(s0 + k * d, 3), e=round(s0 + (k + 1) * d, 3)) for k, j in enumerate(range(j1, j2))]
        # delete: 识别多出来的字,丢弃
    return out


def lexical(chars):
    """逐字 → 词(jieba 分词 + 项目词表),字幕只在词边界换行,不会劈开"国庆节"这类词。"""
    import jieba
    for w in PROJECT.get('caption_words', []):
        jieba.add_word(w, freq=100000)
    toks, k = [], 0
    for t in jieba.lcut(''.join(c['w'] for c in chars), HMM=True):
        seg = chars[k:k + len(t)]
        k += len(t)
        if seg:
            toks.append(dict(w=t, s=seg[0]['s'], e=seg[-1]['e']))
    return toks


def compliance(text):
    return [w for w in BANW if w in text and not any(x in text for x in BAN_EXCEPT)]


# ------------------------------------------------------------------ 2) 剪辑表:去静音、去口癖
def make_edl(words, max_gap, pad_in=TP['pad_in_s'], pad_out=TP['pad_out_s']):
    ws = [dict(x, w=bare(x['w'])) for x in words]
    ws = [x for x in ws if x['w'] and x['w'] not in FILLERS]
    segs = []                                   # 源视频里保留的区间
    for x in ws:
        a, b = max(0.0, x['s'] - pad_in), x['e'] + pad_out
        if segs and a - segs[-1][1] <= max_gap:
            segs[-1][1] = max(segs[-1][1], b)
        else:
            segs.append([a, b])
    segs = [s for s in segs if s[1] - s[0] >= 0.25]
    # 源时间 → 成片时间
    out_t, acc = [], 0.0
    for a, b in segs:
        out_t.append(acc)
        acc += b - a
    for x in ws:
        for k, (a, b) in enumerate(segs):
            if a - 1e-6 <= x['s'] <= b:
                x['os'] = out_t[k] + (x['s'] - a)
                x['oe'] = out_t[k] + (min(x['e'], b) - a)
                x['seg'] = k
                break
    ws = [x for x in ws if 'os' in x]
    return segs, out_t, acc, ws


# ------------------------------------------------------------------ 3) 字幕:分行 + 逐词高亮
def make_lines(ws, jump_at):
    lines, cur = [], []
    for i, x in enumerate(ws):
        if cur and (sum(len(y['w']) for y in cur) + len(x['w']) > CAP['max_chars'] or x['seg'] != cur[-1]['seg']
                    or x['os'] - cur[-1]['oe'] > 0.45):
            lines.append(cur)
            cur = []
        cur.append(x)
    if cur:
        lines.append(cur)
    # 过短的尾行(<3 字)并入上一行
    merged = []
    for ln in lines:
        if merged and sum(len(y['w']) for y in ln) < 3 and sum(len(y['w']) for y in merged[-1]) + sum(len(y['w']) for y in ln) <= CAP['max_chars'] + 2 \
                and ln[0]['seg'] == merged[-1][-1]['seg']:
            merged[-1] += ln
        else:
            merged.append(ln)
    return merged


def blank():
    return Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))


def badge(im):
    ImageDraw.Draw(im).text((40, 1830), '广告', font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 30), fill=(255, 255, 255, 210),
                            stroke_width=2, stroke_fill=(0, 0, 0, 170))
    return im


def cap_png(line, hi, fn):
    im = badge(blank())
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, CAP['size'])
    text = ''.join(x['w'] for x in line)
    w = d.textlength(text, font=f)
    x0, y = (1080 - w) / 2, CAP['center_y'] - CAP['size'] / 2
    for k, wd in enumerate(line):
        col = HI if k == hi else (255, 255, 255, 255)
        for ch in wd['w']:
            d.text((x0 + 4, y + 6), ch, font=f, fill=(0, 0, 0, 110))
            d.text((x0, y), ch, font=f, fill=col, stroke_width=CAP['stroke'], stroke_fill=(15, 15, 15, 255))
            x0 += d.textlength(ch, font=f)
    im.save(fn)


# ------------------------------------------------------------------ 4) 空镜选取
def broll_windows(ws, T, every, rng):
    """在词边界上选插入窗口:[(起, 止)],片头 2s、片尾 2.5s 不插。"""
    if every <= 0:
        return []
    ends = [x['oe'] for x in ws]
    wins, t = [], TP['keep_head_s'] + rng.uniform(0, 1.0)
    while t < T - TP['keep_tail_s'] - TP['broll_len_s'][0]:
        a = min(ends, key=lambda e: abs(e - t))
        want = rng.uniform(*TP['broll_len_s'])
        b = min((e for e in ends if e >= a + 1.2), key=lambda e: abs(e - (a + want)), default=None)
        if b is None or b > T - TP['keep_tail_s']:
            break
        wins.append((round(a, 3), round(b, 3)))
        t = b + every * rng.uniform(0.8, 1.2)
    return wins


def clip_file(idx, k):
    e = idx[k]
    p = e.get('预览') or f"{R}/预览/{e['类别']}/2026-09-29 {k}.mp4"
    p60 = p.replace('/预览/', '/预览60/')
    return p60 if os.path.exists(p60) else p


def pick_broll(idx, need, used, rng):
    c = [k for k, e in idx.items() if e['类别'] == '空镜' and '_重名' not in k and not any(b in e['标记'] for b in BAD)
         and e['时长'] >= need + 0.3 + e.get('min_ss', 0)]
    if not c:
        raise RuntimeError('没有可用空镜(检查素材索引与风险标记)')
    c.sort(key=lambda k: (used.get(k, 0), rng.random()))
    k = c[0]
    used[k] = used.get(k, 0) + 1
    lo = idx[k].get('min_ss', 0.1)
    return k, round(rng.uniform(lo, max(lo, idx[k]['时长'] - need - 0.15)), 2)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return r


def enc_args():
    if os.getenv('AVD_ENC', 'nvenc') == 'nvenc':
        return ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '20', '-bf', '0']
    return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--music')
    ap.add_argument('--music-vol', type=float, default=TP['music_vol'])
    ap.add_argument('--broll-every', type=float, default=TP['broll_every_s'])
    ap.add_argument('--no-broll', action='store_true')
    ap.add_argument('--max-gap', type=float, default=TP['max_gap_s'])
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--model', default='small', help='faster-whisper 模型:small(快) / medium / large-v3(准,慢)')
    ap.add_argument('--script', help='正确文稿文件(txt):按它纠正识别错字,保留逐词时间')
    a = ap.parse_args()
    rng = random.Random(a.seed)
    work = f"{R}/成片/_work_{a.name}"
    os.makedirs(work, exist_ok=True)

    raw = words_of(a.video, a.model)
    chars = to_chars(raw)
    if a.script:
        chars = align_script(chars, open(a.script, encoding='utf-8').read())
    words = lexical(chars)
    full = ''.join(x['w'] for x in words)
    bad = compliance(full)
    if bad:
        print(f'[合规告警] 口播内容含禁用词 {bad}:原声无法改,请换素材或剪掉对应片段')
    tick(f'转写 {len(chars)} 字 / {len(words)} 词')
    segs, out_t, T, ws = make_edl(words, a.max_gap)
    print(f'保留 {len(segs)} 段,成片 {T:.1f}s(原 {words[-1]["e"]:.1f}s 内的有效口播)')

    # 4.1) 主画面:每段保留区间切出来,交替 100%/112% 推近遮跳切
    jobs = []
    for k, (s, e) in enumerate(segs):
        zoom = TP['jump_zoom'][k % 2]
        vf = (f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
              + (f"scale={int(1080 * zoom)}:{int(1920 * zoom)},crop=1080:1920," if zoom != 1.0 else '') + f"fps={FPS},scale=out_range=tv,format=yuv420p,setsar=1")
        fn = f"{work}/h{k:03d}.mp4"
        jobs.append(([FF, '-v', 'error', '-y', '-ss', f'{s:.3f}', '-t', f'{e - s:.3f}', '-i', a.video, '-vf', vf, '-r', str(FPS)]
                     + enc_args() + ['-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', fn], fn))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda j: run(j[0]), jobs))
    open(f"{work}/host.txt", 'w', encoding='utf-8').write(''.join(f"file '{os.path.basename(j[1])}'\n" for j in jobs))
    run([FF, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', f"{work}/host.txt", '-c', 'copy', f"{work}/host.mp4"])
    tick('主画面跳切')

    # 4.2) 空镜窗口 + 渲染
    idx = json.load(open(R + '/数据/素材索引.json', encoding='utf-8'))
    wins = [] if a.no_broll else broll_windows(ws, T, a.broll_every, rng)
    used, brolls = {}, []
    for i, (x, y) in enumerate(wins):
        k, ss = pick_broll(idx, y - x, used, rng)
        fn = f"{work}/b{i:02d}.mp4"
        n = round((y - x) * FPS)
        z = f"1+0.08*on/{n}"
        vf = (f"fps={FPS},scale=1620:2880:flags=bicubic,zoompan=z='{z}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1080x1920:fps={FPS},"
              f"scale=out_range=tv,format=yuv420p,setsar=1")
        run([FF, '-v', 'error', '-y', '-ss', f'{ss:.3f}', '-t', f'{y - x + 0.1:.3f}', '-i', clip_file(idx, k), '-an', '-vf', vf, '-r', str(FPS),
             '-frames:v', str(n)] + enc_args() + [fn])
        brolls.append(dict(clip=k, ss=ss, start=x, end=y, file=fn))
    tick(f'空镜 {len(brolls)} 段')

    # 4.3) 字幕层:逐词高亮
    lines = make_lines(ws, None)
    ov = []                                      # (png, 起, 止)
    cap_log = []
    blank_fn = f"{work}/blank.png"
    badge(blank()).save(blank_fn)
    n_png = 0
    for li, ln in enumerate(lines):
        end_line = ln[-1]['oe'] + 0.12
        if li + 1 < len(lines):
            end_line = min(end_line, lines[li + 1][0]['os'])
        for k, wd in enumerate(ln):
            fn = f"{work}/c{n_png:04d}.png"
            n_png += 1
            cap_png(ln, k, fn)
            b = ln[k + 1]['os'] if k + 1 < len(ln) else end_line
            ov.append((fn, wd['os'], max(b, wd['os'] + 0.05)))
        cap_log.append(dict(text=''.join(x['w'] for x in ln), start=round(ln[0]['os'], 3), end=round(end_line, 3)))
    lst, t = ['ffconcat version 1.0'], 0.0
    for fn, s, e in ov:
        if s - t > 1e-3:
            lst += [f"file '{os.path.basename(blank_fn)}'", f"duration {s - t:.4f}"]
        s2 = max(s, t)
        lst += [f"file '{os.path.basename(fn)}'", f"duration {max(0.02, e - s2):.4f}"]
        t = s2 + max(0.02, e - s2)
    if T - t > 1e-3:
        lst += [f"file '{os.path.basename(blank_fn)}'", f"duration {T - t:.4f}"]
    lst.append(f"file '{os.path.basename(blank_fn)}'")
    open(f"{work}/cap.txt", 'w', encoding='utf-8').write('\n'.join(lst))
    tick(f'字幕 {len(lines)} 行 {n_png} 个状态')

    # 4.4) 合成
    inp = ['-i', f"{work}/host.mp4"]
    fc = []
    prev = '[0:v]'
    for i, b in enumerate(brolls):
        inp += ['-i', b['file']]
        fc.append(f"[{i + 1}:v]setpts=PTS-STARTPTS+{b['start']:.3f}/TB[bv{i}]")
        fc.append(f"{prev}[bv{i}]overlay=0:0:enable='between(t,{b['start']:.3f},{b['end']:.3f})':eof_action=pass[o{i}]")
        prev = f'[o{i}]'
    inp += ['-f', 'concat', '-safe', '0', '-i', f"{work}/cap.txt"]
    ci = len(brolls) + 1
    fc.append(f"[{ci}:v]format=yuva420p,fps={FPS}[cap]")
    fc.append(f"{prev}[cap]overlay=0:0:eof_action=repeat:format=yuv420[vout]")
    if a.music and os.path.exists(a.music):
        inp += ['-stream_loop', '-1', '-i', a.music]
        fc.append(f"[0:a]loudnorm=I=-15:TP=-1.5:LRA=11,aresample=48000[v1]")
        fc.append(f"[{ci + 1}:a]atrim=0:{T:.2f},asetpts=PTS-STARTPTS,volume={a.music_vol},afade=t=in:d=0.3,afade=t=out:st={T - 1:.2f}:d=1,"
                  f"aformat=channel_layouts=stereo[bd]")
        fc.append("[v1][bd]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[ao]")
    else:
        fc.append("[0:a]loudnorm=I=-15:TP=-1.5:LRA=11,aresample=48000[ao]")
    out = f"{R}/成片/{a.name}.mp4"
    vopt = (['-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', '22', '-b:v', '9M', '-maxrate', '12M', '-bufsize', '18M']
            if os.getenv('AVD_ENC', 'nvenc') == 'nvenc' else ['-c:v', 'libx264', '-crf', '20', '-preset', 'fast'])
    r = subprocess.run([FF, '-v', 'error', '-y'] + inp + ['-filter_complex', ';'.join(fc), '-map', '[vout]', '-map', '[ao]', '-t', f'{T:.2f}']
                       + vopt + ['-c:a', 'aac', '-b:a', '192k', out], capture_output=True, text=True, encoding='utf-8', errors='replace')
    tick('合成')
    print('render', r.returncode, r.stderr[-800:])
    json.dump(dict(video=a.video, 成片时长=round(T, 2), 剪辑表=[[round(s, 3), round(e, 3)] for s, e in segs],
                   逐词=[dict(w=x['w'], 源起=x['s'], 成片起=round(x['os'], 3), 成片止=round(x['oe'], 3)) for x in ws],
                   字幕=cap_log, 合规告警=bad, 空镜=[{k: v for k, v in b.items() if k != 'file'} for b in brolls]),
              open(f"{R}/成片/{a.name}.talk.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    sys.exit(r.returncode)


if __name__ == '__main__':
    main()
