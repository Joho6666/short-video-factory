"""素材入库第 2 步:扫描 预览60/<源名>/*.mp4,生成/补全 数据/素材索引.json(已有条目保持不变,只追加新素材)。

每条:文件 / 时长 / 类别(人物 或 空镜) / 内容(先写"未分类",打标后改) / 标记([]) / 预览(绝对路径)
project.json 的 sources 里 "host": true 的源算"人物"(博主出镜),其余都是"空镜"。
用法: python svf/ingest_index.py
"""
import glob
import json
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import R, PROJECT  # noqa: E402

IDX = R + '/数据/素材索引.json'


def duration(p):
    c = cv2.VideoCapture(p)
    n, f = c.get(cv2.CAP_PROP_FRAME_COUNT), c.get(cv2.CAP_PROP_FPS)
    c.release()
    return round(n / f, 2) if f else 0.0


def main():
    os.makedirs(os.path.dirname(IDX), exist_ok=True)
    idx = json.load(open(IDX, encoding='utf-8')) if os.path.exists(IDX) else {}
    added = 0
    for src in PROJECT.get('sources', []):
        cat = '人物' if src.get('host') else '空镜'
        for p in sorted(glob.glob(f"{R}/预览60/{src['name']}/*.mp4")):
            key = os.path.basename(p).rsplit('.', 1)[0].replace(' ', '_')
            if key in idx:
                continue
            idx[key] = dict(文件=f"{src['name']}/{os.path.basename(p)}", 时长=duration(p), 类别=cat, 内容='未分类', 标记=[],
                          预览=p.replace(os.sep, '/'))
            added += 1
    json.dump(idx, open(IDX, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'素材索引 共 {len(idx)} 段,新增 {added}')


if __name__ == '__main__':
    main()
