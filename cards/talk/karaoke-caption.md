---
name: karaoke-caption
一句话: 逐词卡拉 OK 字幕:正在说的那个词变黄,出现时刻 = 该词开口时刻
类别: talk
适用: 口播视频的字幕;配合 talk-jumpcut,字幕时间已按剪辑后的时间线重算
时长: 随口播,每词一个状态
能量: 中
风格: T1
实现: svf/talk.py  lexical / make_lines / cap_png
参数: {"size": 72, "stroke": 7, "center_y": 1400, "max_chars": 10, "highlight": "#FFE000"}
---

## 意图
字幕"跟着嘴走",观众视线被引到正在说的词,信息接收更快,也让口播显得更有节奏。

## 参数表
| 参数 | 当前值 | 调节手感 |
|---|---|---|
| max_chars | 10 | 一行最多字数,超过按词边界换行 |
| highlight | #FFE000 | 与 caption-bold-outline / big-card-pop 同色,风格统一 |
| size / stroke | 72 / 7 | 比旁白字幕略大,口播画面干净,字幕是主视觉 |

## 已知坑
- 中文 whisper 的"词"多是 1~3 个字,**换行前先用 jieba 分词**(并加载项目的 `caption_words`),否则会把"国庆节"这类词劈开。
- 识别错字会直接上屏:有逐字文稿时用 `--script 文稿.txt`,按 difflib 对齐,**替换错字但保留时间**;没有文稿时建议 `--model medium` 以上并人工看一遍。
- 每个词一张整屏 PNG(1080×1920),长口播(>60 秒)会生成几百张图,磁盘和时间都会涨。
