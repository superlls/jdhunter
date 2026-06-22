# JDHunter：JD 驱动的 GitHub 简历项目匹配器

> **一句话**：把一份岗位 JD 丢进来，自动去 GitHub 反向找技术栈 / 业务域吻合度最高的开源项目，经本地源码验证后，产出与这份 JD 对齐的简历写法包（Markdown + PDF）。

> **致谢**：本项目的流程与脚本骨架参考自 `backend-agent-project-selector`（后端 / Agent 通用项目选择器），在其基础上改造为「按具体 JD 反向匹配」的形态。

---

## 项目简介

求职时最常见的痛点不是「找不到项目」，而是「找到的项目和目标岗位对不上」。JDHunter 反过来做：**先吃透一份具体 JD，再去 GitHub 找最匹配的项目**，最后给出的简历条目能直接对上这份 JD 的关键词和职责。

它解决三件事：

1. **解析 JD** —— 把你粘贴的招聘文本抽成结构化「需求画像」（技术栈、业务域、职责、加分项）。
2. **反向匹配** —— 用这些关键词驱动 GitHub 搜索和打分，技术栈重合度 + 业务域吻合度为核心，star 只是弱信号。
3. **可信落地** —— 强制把最终项目克隆到本地、从源码里验证，再写简历，杜绝「凭印象编功能点」。

适用人群：在校生 / 早期后端、Agent 方向求职者，想针对某个具体岗位准备简历项目和面试谈资。

## 核心特性

- **JD 驱动**：搜索查询和评分都由你这份 JD 的关键词动态生成，不是固定模板。
- **JD 匹配度报告**：逐条列出 JD 的每项要求由哪个项目、哪段功能命中，标注「已覆盖 / 需改造 / 未覆盖」。
- **本地源码验证（硬约束）**：最终项目必须经脚本克隆到本地、提取至少 5 个源码证据点，否则淘汰。
- **反水货**：默认排除框架 / SDK / awesome-list / 脚手架 / 桌面壳，以及 IoT / 硬件（除非 JD 要求）。
- **中文输出 + PDF**：默认产出中文简历包，并生成浅色、中文友好的 PDF。
- **不碰反爬**：只接受你粘贴的 JD 文本，不联网抓取 BOSS 直聘等招聘站。

## 安装

### 方法一：Git 克隆（推荐）

```bash
git clone https://github.com/superlls/jdhunter.git ~/.claude/skills/jdhunter
```

### 方法二：手动安装

1. 下载本仓库 ZIP 或克隆到本地。
2. 把 `jdhunter` 文件夹放到 Claude Code 的 skills 目录：
   - **macOS/Linux**：`~/.claude/skills/`
   - **Windows**：`%USERPROFILE%\.claude\skills\`
3. 确认目录结构如下：

   ```
   ~/.claude/skills/jdhunter/
   ├── SKILL.md                       # 技能定义
   ├── README.md                      # 本说明
   └── references/
       ├── JD解析.md                  # JD 抽取与关键词归一化
       ├── 匹配评分.md                # 匹配打分 + 覆盖矩阵
       ├── 输出模板.md                # 含 JD 匹配度报告
       ├── 简历写法.md                # 简历条目与面试问题
       ├── search_jd_candidates.py    # JD 关键词驱动的 GitHub 搜索
       ├── pull_github_repos.py       # 本地拉取源码并生成 manifest
       └── markdown_to_pdf.py         # 输出中文友好 PDF
   ```

### 依赖

- Python 3.9+（脚本零第三方依赖）。
- 生成 PDF 需要 `reportlab`：`python -m pip install reportlab`。
- 建议配置 `GITHUB_TOKEN` 环境变量以提高 GitHub 搜索配额（匿名会触发速率限制）。

### 验证安装

重启或重新加载 skills 后，在对话中输入：

```
/jdhunter
```

技能被激活即安装成功。

## 使用

### 基础用法

```
/jdhunter
<把 BOSS 直聘 / 招聘页面的 JD 整段粘贴进来>
```

JDHunter 会：先解析 JD 并回显技术栈和业务域让你确认 → 搜 GitHub 给短名单（等你确认方向）→ 拉源码做本地验证 → 生成 `jd-match-resume-pack.md` 和 PDF。

### 使用场景示例

**输入：** 一份「Java 后端开发实习」JD，要求 Spring Boot / Spring Cloud / Redis / Kafka / MySQL，业务是电商交易、订单支付。

**JDHunter 会：**

1. 解析回显：
   ```
   岗位：Java 后端开发实习（应届）
   硬技术栈：spring-boot, spring-cloud, redis, kafka, mysql
   业务域：ecommerce, order, payment, inventory
   职责重点：高并发、数据一致性、交易链路
   ```
2. 跑搜索脚本，召回技术栈对得上、有完整交易闭环的开源商城 / 交易系统候选池。
3. 给 3-4 个短名单，附 JD 覆盖矩阵（技术 X/Y、业务 X/Y、语言 ✓/✗）和淘汰理由。
4. 你确认后拉源码，从订单状态机、支付回调幂等、库存预占、分布式事务等机制里提取证据。
5. 产出含「JD 匹配度报告」的简历包：哪条 JD 要求由哪个项目哪段功能命中。

## 工作流程

```
粘贴 JD
  → 解析成「需求画像」并回显确认
  → search_jd_candidates.py 按关键词搜 GitHub、打匹配分、出短名单
  → 你确认短名单方向
  → pull_github_repos.py 克隆到本地（只认 manifest 中 cloned 状态）
  → 从本地源码提取 ≥5 个证据点（否则淘汰）
  → 生成 jd-match-resume-pack.md + PDF（含 JD 匹配度报告）
```

### 评分模型（简化）

```
匹配分 = 技术栈重合度（每命中一个 JD 硬技术栈 +3）
       + 业务域吻合度（每命中一个 JD 业务域 +2）
       + 主语言吻合（+3）
       + 1k+ star 弱加分（封顶）
       - 框架/工具/脚手架降权
       - 过热项目 / IoT 降权（JD 未要求时）
```

> 注：GitHub 的 language 字段按字节统计，Java 商城可能被标成 JavaScript，因此主语言只作加分、不作硬过滤。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `SKILL.md` | 技能定义、流程、必须遵守的规则 |
| `references/JD解析.md` | JD 字段抽取与中文→英文关键词归一化 |
| `references/匹配评分.md` | 匹配打分、JD 覆盖矩阵、短名单取舍 |
| `references/输出模板.md` | 简历包结构，含 JD 匹配度报告章节 |
| `references/简历写法.md` | 简历条目写法与面试问题 |
| `references/search_jd_candidates.py` | JD 关键词驱动的 GitHub 搜索与初筛 |
| `references/pull_github_repos.py` | 真实克隆仓库、生成本地源码 manifest |
| `references/markdown_to_pdf.py` | Markdown 转中文友好 PDF |

## 设计原则

- **JD 是唯一事实来源**：解析只基于你给的文本，不补充模型对岗位的先验臆测。
- **源码证据优先**：README / 网页 / 模型记忆只能用于初筛，最终「负责功能」必须来自本地源码。
- **诚实边界**：区分「已有能力 / 建议改造 / 可写入简历」，不把没实现的改造写成已完成成果。
- **反热门偏置**：对学生简历烂大街的复刻项目降权，优先业务闭环清晰、可二次改造的细分项目。

## 许可

MIT License。

---

**提示**：JDHunter 不是帮你「水简历」，而是帮你找到真能对上目标岗位、且讲得清工程难点的项目。最终简历条目都应有本地源码支撑，面试经得起追问。
