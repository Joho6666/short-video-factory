"""配方卡工具:读取 cards/**/*.md,校验字段,并核对卡里的参数与渲染器/模板是否一致。
用法: python svf/cards.py [list|check]
"""
import os, re, sys, json, glob

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cards')
REQ = ['name', '一句话', '类别', '适用', '时长', '能量', '风格', '实现', '参数']


def load(path):
    txt = open(path, encoding='utf-8').read()
    m = re.match(r'---\n(.*?)\n---\n(.*)', txt, re.S)
    if not m:
        raise ValueError('缺少 frontmatter')
    fm = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(':')
        fm[k.strip()] = v.strip()
    fm['参数'] = json.loads(fm['参数']) if fm.get('参数') else {}
    fm['风格'] = [s for s in fm.get('风格', '').split(',') if s]
    fm['_body'] = m.group(2)
    fm['_path'] = path
    return fm


def all_cards():
    return [load(p) for p in sorted(glob.glob(os.path.join(ROOT, '*', '*.md')))]


def derive_used(tpl):
    """从骨架里的实际用法推出它用到了哪些配方卡(转场/大字卡/标题/卡点/运镜/字幕)。"""
    if tpl.get('kind') == 'talk':                      # 口播骨架:固定三张口播卡
        return {'talk-jumpcut', 'karaoke-caption', 'broll-cutaway'}
    cards = {'caption-bold-outline'}
    nodes = []

    def walk(x):
        if isinstance(x, dict):
            nodes.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(tpl.get('sequence', []))
    walk(tpl.get('optional', []))
    tin_card = {'push_left': 'push-left', 'flash_zoomblur': 'flash-whitefade', 'whip_left': 'whip-blur', 'zoom_blur': 'zoom-in-cut'}
    for n in nodes:
        for k in ('tin', 'title_tin', 'extra_tin'):
            if n.get(k) in tin_card:
                cards.add(tin_card[n[k]])
        for t in n.get('tins', []) if isinstance(n.get('tins'), list) else []:
            if t in tin_card:
                cards.add(tin_card[t])
        if 'big' in n or 'big_format' in n or 'big_key' in n:
            cards.add('big-card-pop')
        if 'title' in n or 'open_cats' in n:
            cards.add('title-sticker-pop')
        if n.get('beat') or n.get('type') == 'montage':
            cards.add('beat-cut-snap')
    pool = (tpl.get('style_override', {}).get('shot', {}) or {}).get('motion_pool') or ['zoom_in_slow', 'zoom_out_slow', 'pan_left', 'pan_right']
    if any(m.startswith('zoom') for m in pool):
        cards.add('push-in-slow')
    if any(m.startswith('pan') for m in pool):
        cards.add('pan-sweep')
    return cards


def skeleton_T1_params():
    from skeleton import load_all
    from config import R
    return load_all(R)['T1']['params']


def check():
    errs = []
    cards = all_cards()
    names = set()
    here = os.path.dirname(os.path.abspath(__file__))
    render_src = open(os.path.join(here, 'render.py'), encoding='utf-8').read()
    tpl = json.load(open(os.path.join(os.path.dirname(here), 'templates', 'B_信息种草.json'), encoding='utf-8'))
    xf = dict(re.findall(r"'(\w+)': \('(\w+)',", render_src))
    for c in cards:
        n = c.get('name', '?')
        for k in REQ:
            if k not in c or c[k] in ('', {}, []):
                errs.append(f'{n}: 缺字段 {k}')
        if n in names:
            errs.append(f'{n}: 名字重复')
        names.add(n)
        if os.path.basename(c['_path'])[:-3] != n:
            errs.append(f'{n}: 文件名与 name 不一致')
        for sec in ('## 意图', '## 参数表', '## 已知坑'):
            if sec not in c['_body']:
                errs.append(f'{n}: 缺章节 {sec}')
        p = c['参数']
        if c.get('类别') == 'transition':          # 转场:xfade 名要和渲染器一致
            tk = p.get('template_key')
            if xf.get(tk) != p.get('xfade'):
                errs.append(f'{n}: xfade={p.get("xfade")} 与 render.py XF[{tk}]={xf.get(tk)} 不一致')
        if n == 'caption-bold-outline':
            for k in ('size', 'stroke', 'center_y', 'max_chars'):
                if p.get(k) != tpl['caption'].get(k):
                    errs.append(f'{n}: {k} 与模板不一致')
        if n == 'title-sticker-pop':
            for k in ('size', 'y', 'anim_dur', 'hold'):
                if p.get(k) != tpl['title_sticker'].get(k):
                    errs.append(f'{n}: {k} 与模板不一致')
        if n == 'big-card-pop':
            for k in ('size', 'center_y', 'fill', 'stroke', 'stroke_w', 'outer', 'pop'):
                if p.get(k) != tpl['big_card'].get(k):
                    errs.append(f'{n}: {k} 与模板不一致')
        if c.get('类别') == 'talk':
            tp = skeleton_T1_params()
            for k, v in p.items():
                if k in tp and tp[k] != v:
                    errs.append(f'{n}: {k}={v} 与 T1_口播.json 的 {tp[k]} 不一致')
                if k == 'caption':
                    pass
            if n == 'karaoke-caption':
                for k, v in p.items():
                    if tp['caption'].get(k) != v:
                        errs.append(f'{n}: {k} 与 T1_口播.json caption 不一致')
        if n == 'push-in-slow' and p['zoom_in_slow']['amount'] != tpl['shot']['zoom_amount']:
            errs.append(f'{n}: amount 与模板 zoom_amount 不一致')
    # 骨架 ↔ 配方卡 双向一致:骨架声明的 cards 必须等于实际用到的;卡的"风格"必须等于用到它的骨架
    import skeleton
    from config import R
    skel = skeleton.load_all(R)
    byname = {c['name']: c for c in cards}
    used_by = {n: set() for n in byname}
    for sid, t in skel.items():
        used = derive_used(t)
        decl = set(t.get('cards', []))
        if decl != used:
            errs.append(f"骨架 {sid}: 声明的 cards 与实际不符  多写 {sorted(decl - used)}  漏写 {sorted(used - decl)}")
        for n in used:
            if n not in byname:
                errs.append(f'骨架 {sid}: 引用了不存在的卡 {n}')
            else:
                used_by[n].add(sid)
    for n, c in byname.items():
        if set(c['风格']) != used_by[n]:
            errs.append(f"{n}: 卡里写的风格 {sorted(c['风格'])} 与骨架实际使用 {sorted(used_by[n])} 不一致")
    return cards, errs


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    cards, errs = check()
    if cmd == 'list':
        for c in cards:
            print(f"{c['类别']:<10}{c['name']:<24}{','.join(c['风格']):<14}{c['一句话']}")
    else:
        print(f'{len(cards)} 张卡', '全部通过' if not errs else '')
        for e in errs:
            print('✗', e)
        sys.exit(1 if errs else 0)
