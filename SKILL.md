---
name: jdhunter
description: "Given a job description (JD) pasted from BOSS直聘 or any recruiting site, parse it into a structured requirement profile (tech stack, business domain, responsibilities, bonus skills), search GitHub for the most relevant high-match projects, verify them against local source code, and generate a JD-aligned resume-writing package (Markdown + PDF). Use when a user pastes a JD and asks to find matching GitHub projects, build resume projects targeting a specific job, reverse-match projects to a posting, or turn a JD into resume bullets/interview talking points. Requires the user to paste JD text; if no JD is provided, ask for it before searching. Keeps the hard rule that final projects must be verified against locally cloned source code. Excludes thin wrappers, demos, frameworks/SDKs, awesome-lists, and IoT/hardware unless the JD requires them."
---

# JD 驱动的 GitHub 匹配项目选择器

## 能力范围

输入一份岗位 JD（用户从 BOSS 直聘或其他招聘网站复制粘贴的文本），解析成结构化「JD 需求画像」，再去 GitHub 反向搜索技术栈 / 业务域吻合度最高的项目，经本地源码验证后，生成与该 JD 对齐的简历写法包 `jd-match-resume-pack.md` 和对应 PDF。

与通用项目选择器的核心区别：搜索查询和打分都由这份 JD 的关键词驱动，最终产出额外包含「JD 匹配度报告」——逐条说明 JD 的每项要求由哪个项目、哪段功能命中。

## 必须遵守

- JD 文本是必填输入。如果用户发起找项目但没有提供 JD 文本，必须先用「缺少 JD 时的反问话术」索要完整 JD，不要凭岗位名称、印象或经验自行编造 JD 需求。
- 只接受用户粘贴的 JD 文本作为来源；不联网抓取 BOSS 直聘等招聘站（反爬且需登录）。如需读取在线页面，必须由用户自己复制粘贴。
- JD 解析只能基于用户实际给出的文本；不能把模型对该岗位的先验臆测当成 JD 要求。解析结果要回显给用户确认关键技术栈和业务域。
- 搜索查询必须由 JD 抽取的技术栈 + 业务域关键词驱动，覆盖至少 4 组查询；不要只用全局 `sort=stars`，要主动覆盖 1k-5k 中等热度的细分业务项目。
- star 数只作为社区验证弱信号：1k star 即可纳入候选池；超过 1k 后不因 star 更高显著加分，20k+ 不自动加分。
- 候选池阶段读取 README 前若干行做项目类型 probe 与 JD 覆盖初筛；README probe 只能用于筛选和匹配预估，不能支撑最终「负责功能 / 技术难点」。
- 构建候选池优先运行 `references/search_jd_candidates.py`，由它完成搜索、README probe、去重、JD 匹配打分、排除框架 / SDK / awesome / 脚手架 / 桌面壳，并默认排除 IoT / 硬件（除非 JD 明确要求）。
- 拉取源码前，必须先向用户展示 3-4 个短名单项目，每个都要给出「对这份 JD 的匹配点、JD 覆盖矩阵、主要淘汰理由」，并等待用户确认方向；确认后才能执行 `pull_github_repos.py`。
- 最终入选项目前必须运行 `references/pull_github_repos.py` 真实拉取仓库到本地；未经脚本成功拉取并写入 manifest（状态 `cloned`）的项目不得进入最终推荐。
- 源码验证只能基于 `pull_github_repos.py` 拉到本地的仓库目录进行；不能用 GitHub raw/API、README、网页、模型记忆替代本地源码验证。
- 脚本失败、仓库无法拉取、manifest 状态不是 `cloned`、本地源码不可读、或无法从源码提取至少 5 个证据点，该项目必须淘汰。
- 必须区分 `已有能力`、`建议改造`、`可写入简历`；建议改造默认写成「建议简历功能点（完成对应改造后可写）」，不能把未实现内容写成已完成成果。
- 项目亮点必须挖掘技术难度，不能只写「实现功能 / 接入组件 / 提供接口」；优先挖数据一致性、MQ 异步链路、缓存与高并发、并发控制与幂等、任务调度、流量治理、数据库优化、检索索引、权限安全、可观测性、状态机、交易链路、Agent 工程等机制。
- 简历条目要尽量复用 JD 的关键词和动词，让「负责功能」能直接对上 JD 的职责与加分项，但每条都必须有源码证据支撑，不能为贴合 JD 而编造。
- 默认使用中文输出，除非用户要求其他语言。

## 参考资料加载

按任务需要加载，不要一次性加载所有资料：

- `references/JD解析.md`：解析 JD、抽取技术栈 / 业务域 / 职责 / 加分项时加载。
- `references/匹配评分.md`：候选打分、JD 覆盖矩阵、短名单取舍时加载。
- `references/简历写法.md`：写简历条目和面试问题前加载。
- `references/输出模板.md`：生成最终 Markdown 文件前加载。
- `references/search_jd_candidates.py`：候选池搜索和短名单确认前优先执行；按 JD 关键词搜索 GitHub、README probe、去重、JD 匹配打分、排除框架 / SDK / awesome / 脚手架 / IoT，并生成候选池 JSON 与短名单预览 Markdown。
- `references/pull_github_repos.py`：最终候选源码验证前必须执行；真实拉取仓库并生成本地 manifest。
- `references/markdown_to_pdf.py`：最终交付必执行；将 Markdown 转成浅色、中文友好的 PDF。

## 高层流程

1. 检查用户是否粘贴了 JD 文本。
2. 如果没有 JD 文本，停止执行，用「缺少 JD 时的反问话术」索要完整 JD。
3. 解析 JD（见 `JD解析.md`），抽取 `岗位`、`硬技术栈`、`加分技术`、`业务域`、`职责动词`、`经验年限`，组装「JD 需求画像」，并回显给用户确认。
4. 运行 `python references/search_jd_candidates.py`，把技术栈作为 `--tech`、业务域作为 `--domain`、目标主语言作为 `--language` 传入，建立 JD 匹配候选池；候选池要含 1k+ star 的中等热度项目。
5. 按 `匹配评分.md` 过滤浅层项目并打 JD 匹配分，给每个候选算出 JD 覆盖矩阵。
6. 选 3-4 个短名单项目，输出短名单、对该 JD 的匹配点、JD 覆盖矩阵、主要淘汰理由和待拉取 URL，先让用户确认方向。
7. 用户确认后，执行 `python references/pull_github_repos.py --repo <url> ...` 拉取源码并生成 manifest。
8. 只读取 manifest 中状态为 `cloned` 的本地仓库目录做源码验证；README / 文档只是前置步骤。
9. 只保留能从本地源码提取至少 5 个证据点的项目；无法拉取或验证的候选淘汰。
10. 按 `输出模板.md` 和 `简历写法.md` 生成 `jd-match-resume-pack.md`，其中必须含「JD 匹配度报告」。
11. 默认同时生成 Markdown 和 PDF：执行 `python jdhunter/references/markdown_to_pdf.py jd-match-resume-pack.md --output jd-match-resume-pack.pdf --title "JD 匹配项目推荐报告"`。

## 缺少 JD 时的反问话术

如果用户没有粘贴 JD 文本，直接回复：

```text
请把目标岗位的 JD 完整文本粘贴给我（从 BOSS 直聘或招聘页面复制即可），包括：

- 岗位名称
- 任职要求 / 技术栈（语言、框架、中间件、数据库等）
- 工作职责
- 加分项 / 优先条件（如果有）

我不联网抓取 BOSS 直聘（反爬且需登录），所以需要你直接粘贴文本。
拿到 JD 后，我会先解析出技术栈和业务域并回显给你确认，再去 GitHub 找匹配项目。
```

## JD 匹配标准

- 优先召回技术栈对得上、且有完整业务闭环的项目：下单、支付、退款、库存、结算、审批、工单、内容发布、消息通知、搜索、推荐、权限、对账等。
- 技术栈重合度和业务域吻合度是主排序依据，star 数只是弱信号。
- 框架 / SDK / library / toolkit / 脚手架 / 模板 / 桌面壳 / awesome-list 默认降权或淘汰，除非 JD 明确要求该方向。
- 默认排除 IoT、嵌入式、硬件接入、设备管理、工业控制类项目；只有 JD 明确写硬件 / IoT / 物联网 / 边缘方向时，才用 `--allow-iot` 放开并在输出中标注偏硬件方向。
- 浅层 CRUD、教程复刻、无状态流转 / 异步链路 / 失败恢复 / 权限边界的项目淘汰。

## 输出约定

始终在当前工作区创建或更新 Markdown 与 PDF 两个交付物；Markdown 内容包括：

- 结论先行的推荐（每个项目说明它对这份 JD 命中了哪些硬要求）
- JD 需求画像（解析回显）
- JD 匹配度报告：逐条列出 JD 的关键要求，标注由哪个项目 / 哪段功能命中，哪些是「需改造后才能覆盖」
- 候选池与 JD 覆盖矩阵
- 多样性说明与可替换项目
- 每个推荐项目的详细分析
- 简历写法：先给 80-120 字项目简介，再给代码验证摘要，然后给 5-6 条「负责功能 / 技术难点」（必须来自源码验证、并尽量贴合 JD 用词），最后给「建议简历功能点（完成对应改造后可写）」
- 下一步落地或改造计划
- PDF 必须生成：用 `references/markdown_to_pdf.py` 输出 `jd-match-resume-pack.pdf`，浅色背景块、清晰标题层级，不加「阅读导航」，内联代码按普通正文渲染以避免中文段落异常换行。
