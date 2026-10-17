"""入库打标:免费的客观指标 + 视觉模型看分镜表打标签。

用法:
  ingest_tag.py metrics              # 给素材索引每段加 清晰度/亮度/运动量/质量分(本地计算,不花 token)
  ingest_tag.py sheets [N] [--todo]  # 每段取 首/中/尾 三帧,N 段一张表(默认 12),写 数据/tag_tasks/(--todo 只出还没打标的)
  ingest_tag.py apply 标签.json ...   # 校验并合并视觉模型给出的标签(默认只预演,加 --write 才写回)
  ingest_tag.py auto [--model M] [--sheets 01,02]  # 用本机 Claude Code(claude -p)自动看分镜表打标,写 数据/tag_tasks/auto_NN.json
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
try:      # 打标用哪个模型:环境变量 SVF_TAG_MODEL > config.json 的 tag_model > claude 默认
    CFG_TAG_MODEL = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json'), encoding='utf-8')).get('tag_model')
except Exception:
    CFG_TAG_MODEL = None


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


PROMPT = """你是素材打标员。请用 Read 工具读取这张分镜表图片:{img}
图里每个素材占 3 格(首/中/尾三帧),左上角黄色文字是素材编号,从上到下、每行 2 个素材。本张共 {n} 个素材,编号依次是:{labels}
给每个素材打标,字段:
- shot: {shots} 之一
- brand: 画面里清楚可见的品牌/店名,没有写空字符串
- quality: 1-5 整数(5=清晰稳定构图好,3=能用,1=糊/抖/构图差/大段废帧)
- position: {positions} 之一(适合放在片子的哪个位置)
- risk: 只能从下面这些标签里选(原文照抄),没有就 []:{risks}
- note: 一句话说明内容和风险依据
风险判断:{risk_help}
只标**清楚可辨**的风险:标牌/海报/价牌必须在画面里占较大面积、能读出文字或数字才算;远处小字、背景里模糊的小牌子不算。面孔必须清晰可辨才算(背影、很远的小人影、被遮挡的不算)。只输出一个 JSON 对象,键是素材编号,值是上面的字段,不要任何别的文字。"""

RISK_HELP = {
    '路人或儿童正脸': '画面里有路人/顾客/儿童且面孔可辨认(博主本人除外)',
    '含明星肖像(版权肖像风险)': '大幅明星/艺人/模特肖像海报、展板、LED 屏',
    '拍摄者手指入镜': '拍摄者的手或手指出现在画面里',
    '画面虚焦/构图差': '明显模糊、剧烈晃动、大段只拍地面/遮挡',
}


def ask_claude(sheet, labels, model):
    import re
    model = model or os.environ.get('SVF_TAG_MODEL') or CFG_TAG_MODEL
    import subprocess
    sc = schema()
    risks = list(BAD)
    help_ = ';'.join(f'{r}={RISK_HELP[r]}' for r in risks if r in RISK_HELP)
    help_ += ';' + ';'.join(f'{r}(按字面理解,画面里出现即标)' for r in risks if r not in RISK_HELP)
    prompt = PROMPT.format(img=sheet.replace(chr(92), '/'), n=len(labels), labels=', '.join(labels), shots=' / '.join(sc['shot']),
                           positions=' / '.join(sc['position']), risks=' | '.join(risks), risk_help=help_)
    import shutil
    exe = shutil.which('claude') or 'claude'
    cmd = [exe, '-p', '--allowedTools', 'Read', '--add-dir', os.path.dirname(sheet)] + (['--model', model] if model else [])
    # 桌面 App 会话里的 ANTHROPIC_* / CLAUDE_CODE_* 环境变量会让子进程连错网关(401),清掉后用用户 ~/.claude/settings.json 自己的配置
    env = {k: v for k, v in os.environ.items() if not (k.startswith('ANTHROPIC_') or k.startswith('CLAUDE_CODE_') or k.startswith('CLAUDE_'))}
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=os.path.dirname(sheet), timeout=900, env=env)
    txt = r.stdout
    m = re.search(r'\{.*\}', txt, re.S)
    if not m:
        raise RuntimeError('没有拿到 JSON:' + (txt + r.stderr)[-300:])
    return json.loads(m.group(0))


def cmd_auto(model, only):
    d = R + '/数据/tag_tasks'
    man = json.load(open(d + '/manifest.json', encoding='utf-8'))
    for no, labels in man.items():
        if only and no not in only:
            continue
        out = f'{d}/auto_{no}.json'
        if os.path.exists(out):
            print(no, '已有,跳过')
            continue
        for attempt in range(2):
            try:
                tags = ask_claude(f'{d}/{no}.jpg', labels, model)
            except Exception as e:
                print(no, '失败', str(e)[:200])
                continue
            bad = [l for l in labels if l not in tags or validate(tags[l])]
            if not bad:
                json.dump(tags, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
                print(no, '完成', len(tags), '段')
                break
            print(no, '有问题的编号', bad, '重试' if attempt == 0 else '放弃')


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
    elif a[0] == 'auto':
        mdl = a[a.index('--model') + 1] if '--model' in a else None
        only = a[a.index('--sheets') + 1].split(',') if '--sheets' in a else None
        cmd_auto(mdl, only)
    elif a[0] == 'apply':
        cmd_apply([x for x in a[1:] if not x.startswith('--')], '--write' in a)
    else:
        cmd_status()
