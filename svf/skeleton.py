"""骨架解释器:把 templates/skeletons/*.json(数据)翻译成一条片的句子序列。

骨架 = 这条片有哪些句子、每句用哪个文案池、要什么类别的镜头、用哪张配方卡(转场/大字卡/标题/卡点)。
代码里不再有任何"某商场"的内容:镜头需求用通用角色名(storefront/interior/...),
由项目 project.json 的 batch.cat_alias 映射到自己素材里的真实分类。

节点类型
  line      一句话      text 来源: pool / literal / project_key / index / index_choice
  shuffle   块洗牌      blocks: [[节点...], ...]  打乱后展开
  host      博主原声句   clip: host_clips 的键;insert: host_inserts 的键(中间插入的空镜)
  montage   卡点混剪    由文案池按"头 + 乱序中段 + 尾"拼成,每句卡点(见 build_montage)
  reasons   清单体      由 project 的 reasons 组成"理由一…理由四"
"""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

PASS_THROUGH = ('tin', 'motion', 'host_last', 'sticker', 'sticker_lines', 'beat')


def skeleton_dirs(project_root):
    return [os.path.join(project_root, '模板', 'skeletons'), os.path.join(REPO, 'templates', 'skeletons')]


def load_all(project_root):
    """{风格 id: 骨架}。项目目录里的同名骨架覆盖仓库自带的。"""
    out = {}
    for d in reversed(skeleton_dirs(project_root)):
        for f in sorted(glob.glob(os.path.join(d, '*.json'))):
            t = json.load(open(f, encoding='utf-8'))
            t['_file'] = f
            out[t['id']] = t
    return out


class Ctx:
    """解释骨架需要的上下文(全部来自项目数据)。"""

    def __init__(self, pools, project_batch, brand, big, host, host_insert, reasons, choose, make_line):
        self.P, self.B, self.brand, self.big = pools, project_batch, brand, big
        self.host, self.host_insert, self.reasons = host, host_insert, reasons
        self.c, self.L = choose, make_line


def _text(src, ctx):
    if 'pool' in src:
        return ctx.c(ctx.P[src['pool']])
    if 'literal' in src:
        return src['literal']
    if 'project_key' in src:
        return ctx.B.get(src['project_key'], ctx.P[src['fallback_pool']][0])
    if 'index' in src:
        k, i = src['index']
        return ctx.P[k][i]
    if 'index_choice' in src:
        return ctx.c([ctx.P[k][i] for k, i in src['index_choice']])
    raise ValueError(f'未知文案来源: {src}')


def _title(spec, ctx, n=None):
    if spec == 'brand':
        return ctx.brand
    if spec == 'list_title':
        return ctx.B.get('list_title', '{n}个理由').format(n=n)
    return spec


def _line(node, ctx):
    extra = {k: node[k] for k in PASS_THROUGH if k in node}
    if 'big' in node:
        extra['big'] = ctx.big[node['big']]
    if 'title' in node:
        extra['title'] = _title(node['title'], ctx)
    return ctx.L(_text(node['text'], ctx), node.get('cats', []), **extra)


def _host(node, ctx):
    h = ctx.c(ctx.host[node['clip']])
    base = [h[0], h[1]]
    mid = ctx.host_insert.get(node['insert'], base) if node.get('insert') else None
    shots = [base, mid, base] if mid else [base, base]
    d = dict(text=h[3], host_audio=[h[0], h[1], h[2]], shots=shots)
    for k in PASS_THROUGH:
        if k in node:
            d[k] = node[k]
    if 'big' in node:
        d['big'] = ctx.big[node['big']]
    return d


def _expand(nodes, ctx, rng, out):
    for nd in nodes:
        t = nd.get('type', 'line')
        if t == 'line':
            out.append(_line(nd, ctx))
        elif t == 'host':
            out.append(_host(nd, ctx))
        elif t == 'shuffle':
            blocks = [[x for x in _flat(b, ctx, rng)] for b in nd['blocks']]
            rng.shuffle(blocks)
            for b in blocks:
                out.extend(b)
        else:
            raise ValueError(f'未知节点类型: {t}')


def _flat(nodes, ctx, rng):
    out = []
    _expand(nodes, ctx, rng, out)
    return out


def build_montage(nd, ctx, rng):
    """卡点混剪:头(2 句)+ 乱序中段 + 尾(2 句),每句 beat=True,切点吸附音乐拍点。"""
    P = ctx.P
    pool = list(P[nd['pool']])
    head = [ctx.c(P[p]) for p in nd['head_pools']]
    tail = [pool[nd['tail_fixed_index']], ctx.c(P[nd['tail_pool']])]
    mid = []
    for a, b in nd['mid_slices']:
        mid += pool[a:b]
    rng.shuffle(mid)
    cats = {head[0]: nd['head_cats'][0], head[1]: nd['head_cats'][1], tail[1]: nd['tail_cat']}
    big = ctx.B.get(nd.get('big_key', 's3_big'), {})
    mcat = ctx.B.get(nd.get('cats_key', 's3_cats'), {})
    core = []
    for i, t in enumerate(head + mid[:nd['mid_take']] + tail):
        d = ctx.L(t, cats.get(t) or mcat.get(t) or rng.choice(nd['fallback_cats']), beat=True)
        if t in big:
            d['big'] = big[t]
        if i == nd['title_at']:
            d.update(title=_title(nd['title'], ctx), tin=nd['title_tin'])
        elif i in nd['random_tin_at']:
            d['tin'] = rng.choice(nd['tins'])
        core.append(d)
    opt = [(len(core) - 2, ctx.L(x, mcat.get(x) or nd['leftover_cat'], beat=True)) for x in mid[nd['mid_take']:]]
    return core, opt


def build_reasons(nd, ctx, rng):
    """清单体:开场 + N 个理由(每个带编号大字卡)+ 结尾。N 个理由取自 project 的 reasons。"""
    R = ctx.reasons
    fixed = nd.get('fixed_first', 2)
    rs = R[:fixed] + rng.sample(R[fixed:], nd['take'] - fixed)
    rng.shuffle(rs)
    n = len(rs)
    cn = nd['numerals']
    core = [ctx.L(ctx.c(ctx.P[nd['open_pool']]).replace('{N}', cn[n - 1]), nd['open_cats'], title=_title('list_title', ctx, n))]
    for i, (t, b, cats, more) in enumerate(rs):
        core.append(ctx.L(nd['line_format'].format(cn=cn[i], t=t, more=rng.choice(more)), cats,
                          big=nd['big_format'].format(i=i + 1, b=b), tin=nd['tins'][i % len(nd['tins'])]))
    core.append(_line(nd['end'], ctx))
    extra = [r for r in R if r not in rs]
    rng.shuffle(extra)
    opt = [(len(core) - 1, ctx.L(nd['line_format'].format(cn=cn[n], t=extra[0][0], more=rng.choice(extra[0][3])), extra[0][2],
                                big=nd['big_format'].format(i=n + 1, b=extra[0][1]), tin=nd['extra_tin'], _retitle=True))]
    return core, opt


def build(tpl, ctx, rng):
    """返回 (核心句列表, 可选句列表[(插入位置, 句)])。"""
    core, opt = [], []
    for nd in tpl['sequence']:
        t = nd.get('type', 'line')
        if t == 'montage':
            c_, o_ = build_montage(nd, ctx, rng)
            core += c_
            opt += o_
        elif t == 'reasons':
            c_, o_ = build_reasons(nd, ctx, rng)
            core += c_
            opt += o_
        else:
            _expand([nd], ctx, rng, core)
    # 可选句(控时长时按需插入)
    for o in tpl.get('optional', []):
        at = o['at']
        nodes = _flat(o['nodes'], ctx, rng)
        if o.get('shuffle'):
            rng.shuffle(nodes)
        if o.get('exclude_core_texts'):
            have = {x['text'] for x in core}
            nodes = [x for x in nodes if x['text'] not in have]
        for x in nodes:
            pos = len(core) + (int(at[3:]) if at[3:] else 0) if isinstance(at, str) and at.startswith('end') else int(at)
            opt.append((pos, x))
    return core, opt


def requirements(tpl):
    """骨架需要项目提供什么:文案池名、博主片段、清单理由。用来判断这个项目能不能出这种风格。"""
    pools, host, reasons = set(), set(), False

    def walk(x):
        nonlocal reasons
        if isinstance(x, dict):
            t = x.get('type', 'line')
            if t == 'host':
                host.add(x['clip'])
            if t == 'reasons':
                reasons = True
                pools.add(x['open_pool'])
            if t == 'montage':
                pools.update([x['pool'], *x['head_pools'], x['tail_pool']])
            if 'text' in x and isinstance(x['text'], dict):
                tx = x['text']
                if 'pool' in tx:
                    pools.add(tx['pool'])
                if 'index' in tx:
                    pools.add(tx['index'][0])
                if 'index_choice' in tx:
                    pools.update(k for k, _ in tx['index_choice'])
                if 'fallback_pool' in tx:
                    pools.add(tx['fallback_pool'])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(tpl.get('sequence', []))
    walk(tpl.get('optional', []))
    return dict(pools=sorted(pools), host=sorted(host), reasons=reasons)


def missing(tpl, pools, host_clips, reasons):
    """返回这个项目缺什么(空列表 = 能出)。"""
    r = requirements(tpl)
    out = [f'文案池 {p}' for p in r['pools'] if not pools.get(p)]
    out += [f'博主片段 {h}' for h in r['host'] if not host_clips.get(h)]
    if r['reasons'] and not reasons:
        out.append('清单理由 reasons')
    return out
