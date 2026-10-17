# AGENTS.md — 给任何 AI 代理(Claude Code / Codex / 其他)

这个仓库是**批量短视频工作台**。先读 `skills/short-video-factory/SKILL.md`(完整流程与硬性规则),再动手。

## 一眼看懂
- 入口:`app.py`(GUI)或 `svf/batch.py`(出片)、`svf/talk.py`(口播)、`svf/ingest_*.py`(入库)、`svf/cards.py`(校验)。
- 项目数据不在仓库里:`SVF_PROJECT` 环境变量或 `config.json` 的 `project` 指向项目目录(`project.json`、`数据/`、`成片/`)。
- 风格是数据:`templates/skeletons/*.json`;动效参数与踩坑:`cards/*/*.md`;素材风险标签:`svf/risk.py` + `templates/tag_schema.json`。

## 必须遵守
1. 促销数字只来自项目 `number_whitelist`;禁用词 `banned_words`;不许为了通过检查去放宽。
2. 素材未打标不出片(`batch.py` 会拒绝);打标时拿不准的风险宁可标。
3. 改完代码跑:`python svf/cards.py check`;改骨架或渲染后先 `batch.py --dry`,再出 1~2 条看抽帧,再批量。
4. 并行渲染默认 `-j 1`(16GB 内存并行会合成失败)。
5. 项目目录、`.env`、`config.json`、媒体文件不进 git;推送/公开前先问用户。
6. 配音/音乐走剪映(经 jianying-editor skill),不要换成付费服务,除非用户同意。

## 验证命令
```bash
python svf/cards.py check                  # 卡 ↔ 骨架 ↔ 渲染器 一致
python svf/batch.py --list-styles          # 本项目可用/被跳过的风格
python svf/batch.py --n 10 --dry           # 文案重复度预演
```
