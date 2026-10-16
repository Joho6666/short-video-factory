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
        if n == 'push-in-slow' and p['zoom_in_slow']['amount'] != tpl['shot']['zoom_amount']:
            errs.append(f'{n}: amount 与模板 zoom_amount 不一致')
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
