# 🎬 Short Video Factory

**一条命令,把实拍素材 + 活动明白卡,批量剪成几十条内容各不相同的 30 秒竖屏促销短视频。**

面向商场 / 门店 / 品牌活动的"信息种草型"抖音、视频号短片:照着一条爆款的节奏,自动写文案、剪映配音、选镜头、加转场花字、渲染 60fps 成片、自动质检,并附剪映草稿供人工精修。

- 🖥️ 本地图形工作台(Gradio),素材不出本机
- 🤖 附带 Claude Code skill,可由 AI 代理驱动整条流程
- 🎙️ 配音 / 音乐用剪映 SAMI 与云端曲库(经 [jianying-editor skill](https://github.com/luoluoluo22/jianying-editor-skill)),无付费 API
- ✅ 数字只来自明白卡(白名单)、禁用词拦截、风险素材排除、逐句转写核对

## 效果与速度(RTX 4060 笔记本)
- 60fps、1080×1920,单条渲染约 45 秒;6 条一批约 6~8 分钟(含质检)
- 5 种风格:信息种草 / 博主口播 / 卡点混剪 / 清单体 / 美陈氛围
- 同批 10 条两两镜头重合平均 9%;70 条预演开头句 44 种、文案整条重复 0

## 快速开始
```bash
git clone <本仓库> && cd short-video-factory
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
copy config.example.json config.json      # 填项目目录 / ffmpeg / jianying-editor skill 路径
.venv\Scripts\python app.py               # 打开 http://127.0.0.1:7860
```
依赖:Python 3.11、ffmpeg(含 NVENC 更快,没有会退回 CPU)、[jianying-editor skill](https://github.com/luoluoluo22/jianying-editor-skill)(配音与音乐)。

## 新项目接入
见 [docs/工作流.md](docs/工作流.md) 与 `projects/example/`:
1. `project.json`:品牌、素材源、**明白卡数字白名单**、禁用词、配音、音乐
2. `svf/ingest_mingbaika.py` → `svf/ingest_proxy.py` → `svf/ingest_sheets.py` → 给素材分类打标(可让 Claude 看联系表完成)
3. 编辑 `数据/文案池.json` → 工作台"批量出片"

## 目录
```
app.py                  图形工作台
svf/                    流水线:batch(生成) render(渲染) qc(质检) run_batch(并行) jy_draft(剪映草稿) ingest_*(入库)
templates/              风格模板参数
skills/short-video-factory/SKILL.md   给 Claude Code 的 skill
docs/                   工作流、经验教训
projects/example/       示例项目配置(真实项目数据不进仓库)
```

## 经验教训
实战踩过的坑(剪映 11.5 无法自动导出、SAMI 数字读法、字幕劈词、zoompan 抖动、HDR 发灰、转写质检误报……)见 [docs/经验教训.md](docs/经验教训.md)。

## 注意
- 剪映配音与曲库的商用授权、素材与出镜人员的授权,请使用者自行确认。
- 本项目不包含任何素材、音乐或客户数据。
