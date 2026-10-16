---
name: flash-whitefade
一句话: 白闪淡入的转场,制造"咔"的一下强调,用在进入卖点段、折扣信息前
类别: transition
适用: 从引子切到核心卖点、价格/折扣大字卡出现前;一条片 1~2 次足够
时长: 0.20s(60fps ≈ 12 帧)
能量: 高
风格: S1,S2,S3,S4
实现: svf/render.py  XF['flash_zoomblur'] → ffmpeg xfade=fadewhite
参数: {"template_key": "flash_zoomblur", "xfade": "fadewhite", "duration_s": 0.2}
---

## 意图
白闪是视觉上的"重音"。放在信息重心前面,观众的注意力会被拉回来,
和大字卡配合最好:闪一下 → 大字卡弹出。

## 参数表
| 参数 | 当前值 | 调节手感 |
|---|---|---|
| duration_s | 0.20 | 再短只剩一帧白,像故障;再长变成柔光淡入,失去"咔"感 |
| xfade | fadewhite | 想要黑场闪用 fadeblack,但商场暖色素材配白闪更协调 |

## 已知坑
- 名字叫 `flash_zoomblur` 是历史遗留:早期想做"白闪 + 缩放模糊",实际只实现了白闪,**没有缩放模糊**。
- 一条片超过 2 次会显得闪烁、廉价;用得多了每次的重音效果都会被稀释。
- 素材本身偏亮(橱窗、灯带)时白闪不明显,可以考虑换 whip-blur。
