"""Short Video Factory · 本地工作台(Gradio)

启动:  .venv/Scripts/python app.py      然后浏览器打开 http://127.0.0.1:7860
只监听本机,不上传任何素材。
"""
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter

import gradio as gr

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, 'svf'))
import config  # noqa: E402

PY = sys.executable
CFG = os.path.join(ROOT, 'config.json')
STYLES = {'S1 信息种草': 'S1', 'S2 博主口播': 'S2', 'S3 卡点混剪': 'S3', 'S4 清单体': 'S4', 'S5 美陈氛围': 'S5'}


def R():
    return json.load(open(CFG, encoding='utf-8')).get('project', config.R) if os.path.exists(CFG) else config.R


def env():
    return {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'SVF_PROJECT': R(), 'HF_HUB_DISABLE_SYMLINKS_WARNING': '1'}


# ------------------------------------------------------------------ 项目
def project_info():
    r = R()
    pj = os.path.join(r, 'project.json')
    p = json.load(open(pj, encoding='utf-8')) if os.path.exists(pj) else {}
    idx_f = os.path.join(r, '数据', '素材索引.json')
    idx = json.load(open(idx_f, encoding='utf-8')) if os.path.exists(idx_f) else {}
    lines = [f"**项目目录**:`{r}`", f"**项目名**:{p.get('name', '(未设置 project.json)')}",
             f"**ffmpeg**:`{config.FF}`", f"**剪映 skill**:`{config.JY_SKILL}`",
             f"**素材**:{len(idx)} 段(带风险标记 {sum(1 for e in idx.values() if e.get('标记'))} 段)",
             f"**明白卡数字白名单**:{', '.join(p.get('number_whitelist', [])) or '(空)'}",
             f"**禁用词**:{', '.join(p.get('banned_words', []))}"]
    return '\n\n'.join(lines)


def set_project(path):
    path = path.strip().replace('\\', '/')
    if not os.path.isdir(path):
        return f"❌ 目录不存在:{path}", project_info()
    c = json.load(open(CFG, encoding='utf-8')) if os.path.exists(CFG) else {}
    c['project'] = path
    json.dump(c, open(CFG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return f"✅ 已切换到 {path}(重启工作台后所有模块生效)", project_info()


# ------------------------------------------------------------------ 文案池
def pool_path():
    return os.path.join(R(), '数据', '文案池.json')


def load_pool():
    p = pool_path()
    return open(p, encoding='utf-8').read() if os.path.exists(p) else '{}'


def check_pool(text):
    try:
        P = json.loads(text)
    except Exception as e:
        return f"❌ JSON 格式错误:{e}"
    pj = json.load(open(os.path.join(R(), 'project.json'), encoding='utf-8'))
    wl, ban, exc = pj.get('number_whitelist', []), pj.get('banned_words', []), pj.get('banned_exceptions', [])
    errs = []
    for k, v in P.items():
        for t in v:
            s = re.sub(r'[{}]', '', t)
            for w in ban:
                if w in s and not any(x in s for x in exc):
                    errs.append(f"[{k}] 禁用词「{w}」:{t}")
            for n in re.findall(r'\d+', s.replace('{N}', '')):
                if not any(n in x for x in wl):
                    errs.append(f"[{k}] 数字「{n}」不在明白卡白名单:{t}")
    total = sum(len(v) for v in P.values())
    return (f"✅ {len(P)} 组 / {total} 句,全部通过" if not errs else f"❌ {len(errs)} 处问题:\n" + '\n'.join(errs[:50]))


def save_pool(text):
    msg = check_pool(text)
    if msg.startswith('❌ JSON'):
        return msg
    open(pool_path(), 'w', encoding='utf-8').write(json.dumps(json.loads(text), ensure_ascii=False, indent=1))
    return '已保存。' + msg


def dry_run(n):
    r = subprocess.run([PY, os.path.join(ROOT, 'svf', 'batch.py'), '--n', str(int(n)), '--start', '900', '--dry'],
                       capture_output=True, text=True, encoding='utf-8', env=env())
    return (r.stdout + r.stderr)[-3000:]


# ------------------------------------------------------------------ 批量出片
def next_start():
    nums = [int(m.group(1)) for f in glob.glob(os.path.join(R(), '脚本', 'b*.json'))
            if (m := re.match(r'b(\d+)\.json$', os.path.basename(f)))]
    return (max(nums) // 10 + 1) * 10 + 1 if nums else 101


def run_batch(n, start, styles, j, qc, fps60):
    if not styles:
        yield "请至少选择一种风格", None, []
        return
    st = ','.join(STYLES[s] for s in styles)
    cmd = [PY, '-u', os.path.join(ROOT, 'svf', 'batch.py'), '--n', str(int(n)), '--start', str(int(start)),
           '-j', str(int(j)), '--styles', st, '--qc-sample', str(qc)]
    e = env()
    e['AVD_FPS'] = '60' if fps60 else '30'
    log = f"$ {' '.join(cmd[2:])}\n"
    yield log, None, []
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                         errors='ignore', env=e)
    for line in p.stdout:
        if re.search(r'Trace|SAMI|^\[INFO\]|Warning|warn', line):
            continue
        log += line
        yield log[-8000:], None, []
    p.wait()
    folder = f"{R()}/成片/批次_b{int(start)}-b{int(start) + int(n) - 1}"
    rep = os.path.join(folder, '报告.md')
    vids = sorted(glob.glob(os.path.join(folder, '*.mp4')))
    yield log[-8000:] + f"\n完成(退出码 {p.returncode})", (open(rep, encoding='utf-8').read() if os.path.exists(rep) else None), vids


# ------------------------------------------------------------------ 成片浏览
def batches():
    return sorted([os.path.basename(d) for d in glob.glob(os.path.join(R(), '成片', '批次*')) if os.path.isdir(d)], reverse=True)


def open_batch(b):
    if not b:
        return gr.update(choices=[]), None, None
    d = os.path.join(R(), '成片', b)
    vids = sorted(os.path.basename(v) for v in glob.glob(os.path.join(d, '*.mp4')))
    rep = next((f for f in [os.path.join(d, '报告.md'), os.path.join(d, '批次01_报告.md')] if os.path.exists(f)), None)
    return gr.update(choices=vids, value=vids[0] if vids else None), (open(rep, encoding='utf-8').read() if rep else ''), None


def show_video(b, v):
    if not (b and v):
        return None, None
    d = os.path.join(R(), '成片', b)
    sheet = os.path.join(d, v.split('_')[0] + '_抽帧.jpg')
    return os.path.join(d, v), (sheet if os.path.exists(sheet) else None)


def open_folder(b):
    d = os.path.join(R(), '成片', b) if b else os.path.join(R(), '成片')
    os.startfile(d.replace('/', '\\'))
    return f"已打开 {d}"


# ------------------------------------------------------------------ 素材
def material_stats():
    f = os.path.join(R(), '数据', '素材索引.json')
    if not os.path.exists(f):
        return [], []
    idx = json.load(open(f, encoding='utf-8'))
    cat = Counter(e.get('内容') for e in idx.values())
    flag = Counter(x for e in idx.values() for x in e.get('标记', []))
    sheets = sorted(glob.glob(os.path.join(R(), '联系表', '**', '*.jpg'), recursive=True))
    return ([[k, v] for k, v in cat.most_common()] + [['— 风险标记 —', '']] + [[k, v] for k, v in flag.most_common()]), sheets[:40]


# ------------------------------------------------------------------ 界面
with gr.Blocks(title='Short Video Factory') as demo:
    gr.Markdown('# 🎬 Short Video Factory · 批量短视频工作台\n素材 → 文案 → 剪映配音 → 渲染 → 质检 → 交付,一站完成(全部在本机运行)')
    with gr.Tab('① 项目'):
        info = gr.Markdown(project_info())
        with gr.Row():
            path = gr.Textbox(label='项目目录', value=R(), scale=4)
            btn = gr.Button('切换项目', scale=1)
        msg = gr.Markdown()
        btn.click(set_project, path, [msg, info])
    with gr.Tab('② 文案池'):
        gr.Markdown('每组是一类句子,`{}` 里的内容会标黄。**数字只能来自明白卡白名单**,保存前自动检查。')
        pool = gr.Code(value=load_pool(), language='json', label='数据/文案池.json', lines=24)
        with gr.Row():
            b1 = gr.Button('检查')
            b2 = gr.Button('保存', variant='primary')
            dn = gr.Number(value=70, label='预演条数', precision=0)
            b3 = gr.Button('预演重复度')
        out = gr.Textbox(label='结果', lines=8)
        b1.click(check_pool, pool, out)
        b2.click(save_pool, pool, out)
        b3.click(dry_run, dn, out)
    with gr.Tab('③ 批量出片'):
        with gr.Row():
            n = gr.Number(value=6, label='条数', precision=0)
            start = gr.Number(value=next_start(), label='起始编号', precision=0)
            j = gr.Slider(1, 4, value=3, step=1, label='并行条数')
            qc = gr.Slider(0, 1, value=0.2, step=0.1, label='转写抽检比例')
        styles = gr.CheckboxGroup(list(STYLES), value=list(STYLES), label='风格(轮换分配)')
        fps60 = gr.Checkbox(value=True, label='60fps(更流畅,稍慢)')
        go = gr.Button('开始出片', variant='primary')
        log = gr.Textbox(label='进度', lines=16, autoscroll=True)
        rep = gr.Markdown()
        gal = gr.Files(label='成片')
        go.click(run_batch, [n, start, styles, j, qc, fps60], [log, rep, gal])
    with gr.Tab('④ 成片'):
        with gr.Row():
            bsel = gr.Dropdown(batches(), label='批次', scale=3)
            refresh = gr.Button('刷新', scale=1)
            ofold = gr.Button('打开文件夹', scale=1)
        vsel = gr.Dropdown([], label='视频')
        with gr.Row():
            player = gr.Video(height=560)
            sheet = gr.Image(label='抽帧', height=560)
        brep = gr.Markdown()
        fmsg = gr.Markdown()
        refresh.click(lambda: gr.update(choices=batches()), None, bsel)
        bsel.change(open_batch, bsel, [vsel, brep, player])
        vsel.change(show_video, [bsel, vsel], [player, sheet])
        ofold.click(open_folder, bsel, fmsg)
    with gr.Tab('⑤ 素材'):
        sb = gr.Button('统计')
        tbl = gr.Dataframe(headers=['类别 / 标记', '段数'])
        sg = gr.Gallery(label='联系表', columns=3, height=600)
        sb.click(material_stats, None, [tbl, sg])

if __name__ == '__main__':
    demo.queue().launch(server_name='127.0.0.1', server_port=7860, inbrowser=False,
                        allowed_paths=[R()])
