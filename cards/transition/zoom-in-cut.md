---
name: zoom-in-cut
一句话: 放大冲入下一镜头的转场,最短最猛,像"砸"进下一个画面
类别: transition
适用: 片尾收口(进入最后一句召唤行动前),配合 zoom_in_fast 运镜;也可用于卡点重拍
时长: 0.17s(60fps ≈ 10 帧)
能量: 高
风格: S1,S2,S3,S4,S5
实现: svf/render.py  XF['zoom_blur'] → ffmpeg xfade=zoomin
参数: {"template_key": "zoom_blur", "xfade": "zoomin", "duration_s": 0.17}
---

## 意图
画面像被"吸"进去再弹出新镜头,冲击力在几种转场里最强,所以现在只放在
片尾召唤行动之前当"收口"。连续使用会盖过旁白内容,一条片 ≤2 次。

## 参数表
| 参数 | 当前值 | 调节手感 |
|---|---|---|
| duration_s | 0.17 | 卡点时可压到 0.12 更狠,但再短就和硬切没区别 |
| xfade | zoomin | ffmpeg 的 zoomin 是放大后淡入下一镜,没有真正的径向模糊 |

## 已知坑
- 当前五种风格都把它用在**片尾最后一句之前**(S5 里用在第 5 句),其余位置用 push-left / flash-whitefade / whip-blur;用在中段重拍点还没试过。
- 模板 JSON 里 `scale: 1.25` 不会被读取;名字叫 zoom_blur 但并没有模糊。
- 镜头太短(<0.4s)时转场几乎占满镜头,观众看不清内容。
