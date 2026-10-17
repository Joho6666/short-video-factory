---
name: short-video-factory
description: 批量剪辑竖屏短视频(抖音/视频号,30 秒左右):旁白型(实拍素材 + 活动"明白卡" → 自动写文案、剪映 SAMI 配音、选镜头、渲染 60fps 成片、自动质检)和口播型(真人口播原片 → 去静音跳切 + 逐词字幕 + 空镜插画面)。风格是 templates/skeletons 下的数据文件,可为新项目新增。用户说"批量剪视频/复刻爆款/按模板出片/照着这个视频剪 N 条/商场活动短视频/量产短视频/口播剪辑/加字幕/素材打标"时使用。代码仓库在 E:/short-video-factory(GUI: app.py)。
---

# Short Video Factory

把"一堆实拍素材 + 一张活动明白卡 + 一条参考爆款"变成**几十条内容各不相同、可直接交付**的 30 秒竖屏促销片。

仓库:`E:/short-video-factory`(Python,独立 `.venv`)。项目数据在单独的项目目录(`config.json` 的 `project`),代码里不放任何客户内容。

## 何时使用
- 用户要"照着某条爆款剪 N 条"、"批量出片"、"把这些素材剪成促销短视频"
- 已有项目要继续出片、改文案、改风格、修甲方反馈

## 硬性规则(违反就会交付事故)
1. **促销数字只能来自明白卡**:写在项目 `project.json` 的 `number_whitelist`。文案里出现白名单外的数字,生成器会拒绝——不许为了通过而把数字加进白名单,先问用户。
2. **禁用词**:`banned_words`(极限词 + 甲方点名不要的词,如"双节")。
3. **风险素材不用**:素材索引里带标记的(儿童/路人正脸、明星肖像、品牌自有折扣牌、拍摄者手指入镜、虚焦、汉堡节等非本档期招牌)。
4. **配音数字读法**:配音文本自动转中文(450团500 → 四百五十团五百),字幕仍显示阿拉伯数字。新增数字时同步补 `spoken_numbers`。
5. **不付费**:配音用剪映 SAMI(经 jianying-editor skill)、音乐用剪映云端曲库,本机渲染。要用付费配音/生成前先问用户。
6. **只动项目目录和仓库**,原始素材只读。
7. 看不到画面/听不到声音的结论要说明是"抽帧/转写核对",声音听感让用户判断。

## 标准流程
```bash
cd E:/short-video-factory
.venv/Scripts/python app.py                 # 图形工作台 http://127.0.0.1:7860
# 或命令行:
.venv/Scripts/python svf/batch.py --n 6 --start 601 --qc-sample 0.2   # 出 6 条(-j 默认 1:16GB 内存并行≥2 会合成失败)
.venv/Scripts/python svf/batch.py --n 70 --start 900 --dry                   # 只预演文案重复度
```
产出:`<项目>/成片/批次_bXXX-bYYY/`(mp4 + 抽帧 + 报告.md + 清单.csv)。每条也会生成剪映草稿(可人工精修后在剪映里导出)。

## 新项目接入(一次性)
1. 建项目目录,写 `project.json`(参考仓库 `projects/example/project.json`):品牌名、素材源 `sources`、白名单、禁用词、配音、音乐、博主口播片段。
2. `svf/ingest_mingbaika.py 明白卡.xlsx` → 列出明白卡里的数字,**和用户确认**后写白名单。
3. `svf/ingest_proxy.py` → 全部素材转 1080x1920/60fps 预览(HDR 自动色调映射)。
4. `svf/ingest_index.py` → 生成素材索引;再按上面"素材入库打标"一节打标。
5. `svf/ingest_transcribe.py` → 博主口播转写,挑可用原声句写进 `project.json` 的 `host_clips`。
6. 参考爆款:逐帧拆解(镜头时长、转场位置、字幕样式、花字),必要时用素材逐帧比对还原对方的剪辑清单;沉淀到 `templates/`。
7. 写 `数据/文案池.json`(每类 5–10 种说法),GUI"文案池"页检查通过后再出片。

## 风格 = 数据文件(templates/skeletons/*.json),不是代码
自带:S1 信息种草 · S2 博主口播(原声+口型同步加速)· S3 卡点混剪(镜头吸附音乐拍点)· S4 清单体(N 个理由)· S5 美陈氛围(慢节奏)· T1 口播剪辑(见下)。
- 骨架里每句写:用哪个文案池、要什么镜头(**通用角色名**如 storefront/interior,由项目 `batch.cat_alias` 映射到自己的素材分类;没配就用任意安全镜头)、转场、大字卡、标题。
- **新项目想要自己的款式**:在项目目录 `模板/skeletons/` 放一个 json(同 id 覆盖自带的),不用改代码。参考 `templates/skeletons/S1_信息种草.json`。
- 项目缺文案池/博主片段时,对应风格会被自动跳过并说明缺什么(`batch.py --list-styles` 可查)。
- 动效/字幕的参数、调节手感、踩坑记录在 `cards/*/*.md`(配方卡,13 张);`python svf/cards.py check` 校验卡与骨架/渲染器一致。

## 素材入库打标(新素材必做,否则 batch 会拒绝出片)
```bash
svf/ingest_proxy.py       # 转 60fps 预览(HDR 色调映射)
svf/ingest_index.py       # 生成/补全 数据/素材索引.json(内容先写"未分类")
svf/ingest_tag.py sheets  # 每段取首/中/尾三帧,12 段一张表 → 数据/tag_tasks/NN.jpg + manifest.json
# Claude 看每张表,按 templates/tag_schema.json 写 tags_NN.json:{label: {shot, brand, quality, position, risk, note}}
svf/ingest_tag.py apply 数据/tag_tasks/tags_*.json            # 先预演(校验+列出将新增的风险)
svf/ingest_tag.py apply 数据/tag_tasks/tags_*.json --write    # 确认后写回(自动备份)
```
- risk 只能取 `svf/risk.py` 的标签原文;项目可在 project.json 写 `risk_tags` **整体替换**默认(默认是商场促销类)。
- 打标靠缩略图,**拿不准的风险宁可标**(儿童/路人正脸、品牌折扣牌、明星肖像海报、手指入镜、其他档期招牌);标得多会让可用镜头变少,批量时重复率上升,要在两者间权衡。
- 视觉模型不绑定:默认由 Claude 在会话里看图;以后接 API 模型只要产出同格式 JSON。

## 口播剪辑(T1)
```bash
python svf/talk.py --video 口播原片.mp4 --name t001 [--script 正确文稿.txt] [--model medium] [--music 曲.m4a] [--no-broll]
```
逐词时间戳 → 去静音/口癖跳切(交替推近遮接缝)→ 逐词卡拉 OK 字幕(jieba 分词,不劈词)→ 空镜只换画面不换声音 → 合成。原声含禁用词时日志报"合规告警"(剪辑改不了声音)。**不处理重复拍(NG 重来)**,要先人工剪出完整一条。

## 甲方反馈的处理方式
- 改措辞 → 改文案池 / 禁用词,不要手改单条脚本(生成器会覆盖)
- 语速 → `project.json` 的 `batch.speed`(每风格)
- 画面抖/掉帧 → 已默认 60fps + 1.5 倍预放大;仍抖就查该镜头素材本身
- 字幕断句错 → 把词加进 `caption_words`(不会被劈开)

## 经验与坑
见仓库 `docs/经验教训.md`。最重要的几条:剪映 6.0+ 草稿加密、11.5 无法自动导出;SAMI 会把 500 读成"五零零";整段转写会漏句/重复(要逐句);并行渲染受 CPU/内存限制(默认 -j 1);素材 HDR 不做色调映射会发灰。
