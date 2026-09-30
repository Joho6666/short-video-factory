"""素材入库第 1 步:把所有素材转成 1080x1920 / 60fps 预览(预览60/<源名>/),HDR 自动色调映射。可断点续跑。

素材源在项目 project.json 的 "sources" 里配置:
    [{"name": "空镜", "path": "D:/素材/空镜", "pattern": "*.mp4", "strip": 0}, ...]
    strip:输出文件名去掉原文件名前多少个字符(兼容已有索引的命名)
用法: python svf/ingest_proxy.py [-j 3]
"""
import glob
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import R, FF, PROJECT  # noqa: E402

TM = ("zscale=w=1080:h=1920:t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
      "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def jobs():
    out = []
    for src in PROJECT.get('sources', []):
        path = src['path'].replace('{project}', R)
        for f in sorted(glob.glob(os.path.join(path, src.get('pattern', '*.*')))):
            stem = os.path.basename(f).rsplit('.', 1)[0][src.get('strip', 0):]
            keep_name = src.get('keep_name', False)
            name = os.path.basename(f) if keep_name else stem + '.mp4'
            out.append((f, f"{R}/预览60/{src['name']}/{name}"))
    return out


def is_hdr(f):
    r = subprocess.run([FF, '-hide_banner', '-i', f], capture_output=True, text=True, encoding='utf-8', errors='ignore')
    return 'arib-std-b67' in r.stderr or 'smpte2084' in r.stderr


def run(j):
    s, d = j
    if os.path.exists(d):
        return 'skip'
    os.makedirs(os.path.dirname(d), exist_ok=True)
    hdr = is_hdr(s)
    vf = (TM + ",scale=1080:1920" if hdr else
          "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p") + ",fps=60,setsar=1"
    r = subprocess.run([FF, '-v', 'error', '-y', '-i', s, '-map', '0:v:0', '-map', '0:a:0?', '-vf', vf,
                        '-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '19', '-g', '120',
                        '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-b:a', '128k', d + '.tmp.mp4'],
                       capture_output=True, text=True)
    if r.returncode != 0:     # 没有 NVIDIA 显卡时退回 CPU 编码
        r = subprocess.run([FF, '-v', 'error', '-y', '-i', s, '-map', '0:v:0', '-map', '0:a:0?', '-vf', vf,
                            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19',
                            '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-b:a', '128k', d + '.tmp.mp4'],
                           capture_output=True, text=True)
    if r.returncode == 0:
        os.replace(d + '.tmp.mp4', d)
        return 'ok'
    return 'FAIL ' + r.stderr[-150:]


if __name__ == '__main__':
    n = int(sys.argv[sys.argv.index('-j') + 1]) if '-j' in sys.argv else 3
    J = jobs()
    t = time.time()
    with ThreadPoolExecutor(n) as ex:
        res = list(ex.map(run, J))
    bad = [(j[0], r) for j, r in zip(J, res) if r.startswith('FAIL')]
    print('done', len(J), 'fail', len(bad), 'secs', round(time.time() - t))
    for b in bad:
        print(b)
