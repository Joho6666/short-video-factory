---
name: push-left
一句话: 画面向左推走的横向滑动转场,干净利落,用来切换"场景/话题"
类别: transition
适用: 句与句之间换场景(门店外 → 店内)、标题出现前;不适合同一场景内的连续镜头
时长: 0.17s(60fps ≈ 10 帧)
能量: 中
风格: S1,S2,S3,S4
实现: svf/render.py  XF['push_left'] → ffmpeg xfade=slideleft
参数: {"template_key": "push_left", "xfade": "slideleft", "duration_s": 0.17}
---

## 意图
把"换了一个地方"这件事用方向感表达出来。每条片里它是最常用的转场,
慢了像 PPT,快了看不清,0.17 秒是反复试出来的下限。

## 参数表
| 参数 | 当前值 | 调节手感 |
|---|---|---|
| duration_s | 0.17 | <0.12 读作闪断;>0.3 拖沓,像幻灯片翻页 |
| xfade | slideleft | 想右推改 slideright,同一条片里不要混用方向 |

## 已知坑
- 转场只在 `tin` 不是 cut 的镜头边界生成,**硬切段是直接拼接(concat copy)**,所以转场越多渲染越慢。
- 转场时长从前一镜头里"借"帧(`_xd_next`),镜头太短(<0.5s)时再借就吃掉画面,别连续用。
- 模板 JSON 里 `transitions.push_left.frames: 5` 只是历史记录,**渲染器实际读的是 XF 里的秒数**,改 JSON 不生效。
