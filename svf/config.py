"""统一配置:所有路径都从这里取,不在各脚本里写死。

优先级:环境变量 > 仓库根目录 config.json > 默认值
    SVF_PROJECT   项目数据目录(素材索引/预览/脚本/成片/文案池 都在这里)
    SVF_FFMPEG    ffmpeg 可执行文件
    SVF_JY_SKILL  jianying-editor skill 根目录(剪映 SAMI 配音 / 云端音乐 / 草稿)
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_cfg = {}
_cf = os.path.join(ROOT, 'config.json')
if os.path.exists(_cf):
    _cfg = json.load(open(_cf, encoding='utf-8'))


def _get(key, env, default):
    return os.getenv(env) or _cfg.get(key) or default


def _find_ffmpeg():
    p = shutil.which('ffmpeg')
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return 'ffmpeg'


R = _get('project', 'SVF_PROJECT', os.path.join(ROOT, 'projects', 'example')).replace('\\', '/')
FF = _get('ffmpeg', 'SVF_FFMPEG', None) or _find_ffmpeg()
JY_SKILL = _get('jianying_skill', 'SVF_JY_SKILL', os.path.expanduser('~/.claude/skills/jianying-editor'))
PY = sys.executable            # 所有子进程用同一个 Python,不再混用两套环境
CODE = HERE

# 项目规则(明白卡数字白名单 / 禁用词 / 数字读法),放在项目目录 project.json
_pj = os.path.join(R, 'project.json')
PROJECT = json.load(open(_pj, encoding='utf-8')) if os.path.exists(_pj) else {}
WL = set(PROJECT.get('number_whitelist', []))
BANW = PROJECT.get('banned_words', ['最', '第一', '唯一', '顶级', '全网', '绝对', '史上'])
BAN_EXCEPT = PROJECT.get('banned_exceptions', ['最会'])
SAY = [tuple(x) for x in PROJECT.get('spoken_numbers', [])]

if JY_SKILL and os.path.isdir(os.path.join(JY_SKILL, 'scripts')):
    sys.path.insert(0, os.path.join(JY_SKILL, 'scripts'))


def summary():
    return dict(project=R, ffmpeg=FF, python=PY, jianying_skill=JY_SKILL,
                whitelist=len(WL), banned=len(BANW), project_json=os.path.exists(_pj))


if __name__ == '__main__':
    print(json.dumps(summary(), ensure_ascii=False, indent=1))
