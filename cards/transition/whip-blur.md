---
name: whip-blur
一句话: 横向甩动模糊转场,像镜头快速摇走,用在"马上就到"这类有动感的句子
类别: transition
适用: 即时行动句(现在就去逛)、结尾召唤前;适合有人物走动、人流的画面接下一个镜头
时长: 0.20s(60fps ≈ 12 帧)
能量: 高
风格: S1,S3,S4
实现: svf/render.py  XF['whip_left'] → ffmpeg xfade=hblur
参数: {"template_key": "whip_left", "xfade": "hblur", "duration_s": 0.2}
---

## 意图
模拟"摇镜头甩过去"。比 push-left 更有速度感,但画面信息在转场里被模糊掉,
所以只用在节奏本来就快的位置。

## 参数表
| 参数 | 当前值 | 调节手感 |
|---|---|---|
| duration_s | 0.20 | 低于 0.15 模糊来不及出现,看起来就是硬切 |
| xfade | hblur | 横向模糊;想往下甩可换 vblur,不建议与横向混用 |

## 已知坑
- 转场处是 xfade 在整条链上计算,**转场多时滤镜链变长、CPU 吃紧**,是渲染慢的主因之一。
- 模板 JSON 里 `blur_px: 60` 不会被读取,实际模糊强度由 ffmpeg 内置效果决定,无法单独调。
- 和 flash-whitefade 相邻使用会"一闪一甩"太花,中间至少隔 3 个硬切镜头。
