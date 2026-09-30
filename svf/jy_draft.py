"""把 render_b 出的一条成片拆成剪映草稿(可在剪映里继续改花字/贴纸/美颜)。

用法: python svf/jy_draft.py b004
镜头、旁白、字幕都来自 成片/<name>.用量.json,数字/文案不在这里改。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import R, JY_SKILL, PROJECT  # noqa: E402
PREFIX = PROJECT.get("draft_prefix", "svf_")
name = sys.argv[1]
U = json.load(open(f"{R}/成片/{name}.用量.json", encoding='utf-8'))
idx = json.load(open(R + '/数据/素材索引.json', encoding='utf-8'))

skill_root = JY_SKILL
sys.path.insert(0, os.path.join(skill_root, "scripts"))
from jy_wrapper import JyProject  # noqa: E402
import pyJianYingDraft as draft  # noqa: E402


def clip_path(n):
    e = idx[n]
    p = e.get('预览') or f"{R}/预览/{e['类别']}/2026-09-29 {n}.mp4"
    p60 = p.replace('/预览/', '/预览60/')
    return (p60 if os.path.exists(p60) else p).replace('/', os.sep)


proj = JyProject(f"{PREFIX}{name}", width=1080, height=1920, overwrite=True)

# 1) 视频轨:每个镜头一段,源起点与渲染时一致
EPS = 0.002  # 相邻片段留 2ms 余量,避免微秒取整造成的重叠
shots = U['镜头详情']
for i, s in enumerate(shots):
    end = shots[i + 1]['start'] if i + 1 < len(shots) else s['start'] + s['dur']
    d = round(max(0.1, end - s['start'] - EPS), 3)
    proj.add_clip(clip_path(s['clip']), source_start=f"{s['ss']}s", duration=f"{d}s",
                  target_start=f"{round(s['start'], 3)}s", track_name="VideoTrack")

# 2) 旁白轨:每句一段
t = 0.0
for L in U['旁白']:
    proj.add_audio_safe(L['wav'].replace('/', os.sep), start_time=f"{round(t, 3)}s",
                        duration=f"{round(L['d'] - EPS, 3)}s", track_name="旁白")
    t += L['d']

# 3) 配乐轨(占位音乐,方便在剪映里换成正式曲子)
bgm = proj.add_audio_safe(os.path.join(U['work'], 'bed.wav').replace('/', os.sep), start_time="0s",
                          duration=f"{U['时长']}s", track_name="BGM")
try:
    bgm.volume = 0.3
except Exception:
    pass

# 4) 字幕轨:白字,位置靠下;关键数字用黄色的部分留给剪映套花字
caps = sorted(U['字幕'], key=lambda c: c['start'])
for i, c in enumerate(caps):
    nxt = caps[i + 1]['start'] if i + 1 < len(caps) else c['end']
    d = round(max(0.2, min(c['end'], nxt) - c['start'] - EPS), 3)
    proj.add_text_simple(c['text'], start_time=f"{round(c['start'], 3)}s", duration=f"{d}s",
                         track_name="Subtitles",
                         style=draft.TextStyle(size=9.0, bold=True, color=(1.0, 1.0, 1.0), align=1),
                         border=draft.TextBorder(color=(0.05, 0.05, 0.05), width=60.0),
                         clip_settings=draft.ClipSettings(transform_y=-0.46))

proj.save()
print("draft saved:", f"{PREFIX}{name}")
