"""回归检查:数据化骨架(skeleton.build)与旧的写死代码(build_legacy)结构是否等价。
结构 = 每句的 镜头类别 / 转场 / 运镜 / 大字卡 / 标题 / 贴纸 / 卡点 …(忽略具体抽到哪句文案、哪个博主片段)。
用法: SVF_PROJECT=E:/国庆复刻 python tests/check_skeleton_equiv.py     (需要项目里有 batch.cat_alias)
"""
import collections
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.argv = ['batch.py']
sys.path.insert(0, os.path.join(ROOT, 'svf'))
src = open(os.path.join(ROOT, 'svf', 'batch.py'), encoding='utf-8').read().split("if __name__")[0]
b = type(sys)('b')
b.__dict__['__file__'] = os.path.join(ROOT, 'svf', 'batch.py')
exec(compile(src, 'batch', 'exec'), b.__dict__)

KEYS = ('cats', 'tin', 'motion', 'big', 'title', 'sticker', 'sticker_lines', 'host_last', 'beat', 'host_audio', 'shots')


def fp(L):
    L = dict(L)
    if 'host_audio' in L:
        L['host_audio'] = 'H'
        L['shots'] = len(L['shots'])
    return json.dumps({k: L.get(k) for k in KEYS if L.get(k) is not None}, ensure_ascii=False, sort_keys=True)


bad = 0
N = 30
for st in b.SKEL:
    for no in range(1, N + 1):
        b.TXT_USED.clear()
        co, oo = b.build_legacy(st, random.Random(no * 100))
        b.TXT_USED.clear()
        cn, on = b.build(st, random.Random(no * 100))
        same = (collections.Counter(map(fp, co)) == collections.Counter(map(fp, cn))
                and collections.Counter(fp(x) for _, x in oo) == collections.Counter(fp(x) for _, x in on)
                and len(co) == len(cn))
        if not same:
            bad += 1
            if bad <= 3:
                print('DIFF', st, no, '\n  旧', [fp(x) for x in co][:3], '\n  新', [fp(x) for x in cn][:3])
print(f'结构不一致 {bad} / {len(b.SKEL) * N}')
sys.exit(1 if bad else 0)
