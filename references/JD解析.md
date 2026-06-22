# JD 解析

把用户粘贴的岗位 JD 文本解析成结构化「JD 需求画像」，作为后续 GitHub 搜索和匹配打分的输入。

## 解析原则

- 只解析用户实际给出的文本，不补充模型对该岗位的先验臆测。
- 抽不到的字段标「JD 未写明」，不要编造。
- 解析完必须把技术栈和业务域回显给用户确认，再开始搜索。

## 需求画像字段

| 字段 | 含义 | 抽取来源 |
| --- | --- | --- |
| `岗位` | 岗位名称与方向，如「Java 后端开发实习」 | JD 标题 / 岗位名 |
| `经验年限` | 要求的经验或学历，如「应届 / 1-3 年」 | 任职要求 |
| `硬技术栈` | 必须掌握的语言 / 框架 / 中间件 / 数据库 | 任职要求里的强制项 |
| `加分技术` | 优先 / 加分掌握的技术 | 加分项 / 优先条件 |
| `业务域` | 岗位所属业务场景，如电商交易、支付结算、IM、风控 | 工作职责 / 公司业务描述 |
| `职责动词` | 职责里反复出现的动作，如「设计、优化、保障一致性、高并发」 | 工作职责 |
| `硬约束` | 是否要求硬件 / IoT / 特定云 / 特定行业 | 任职要求 |

## 关键词归一化

把 JD 原话归一成 GitHub 可搜索的英文关键词，供 `search_jd_candidates.py` 的 `--tech` / `--domain` 使用：

- 语言 / 框架：`Spring Boot → spring-boot`、`Spring Cloud → spring-cloud`、`Go/Golang → go`、`Django → django`、`FastAPI → fastapi`、`Gin → gin`、`Netty → netty`。
- 中间件 / 数据库：`Redis → redis`、`Kafka/RocketMQ/RabbitMQ → kafka/rocketmq/rabbitmq`、`MySQL → mysql`、`Elasticsearch/ES → elasticsearch`、`MongoDB → mongodb`、`分库分表/ShardingSphere → sharding`。
- 业务域：`电商/商城 → ecommerce`、`订单 → order`、`支付/收银/结算 → payment`、`库存 → inventory`、`即时通讯/IM → chat/im`、`工单/客服 → helpdesk/ticket`、`CRM → crm`、`内容/社区 → cms/community`、`网盘/文件 → file/storage`、`风控 → risk`、`搜索推荐 → search/recommendation`。
- 一个中文词可映射多个英文候选词，搜索时择优。

## 传给搜索脚本

把归一后的关键词作为参数：

```bash
python references/search_jd_candidates.py \
    --tech spring-boot --tech spring-cloud --tech redis --tech kafka --tech mysql \
    --domain ecommerce --domain order --domain payment --domain inventory \
    --language Java \
    --output jd-candidate-pool.json \
    --shortlist-output jd-shortlist-preview.md
```

- `--tech`：硬技术栈优先，加分技术补充，按重要性排前 4-6 个（脚本只用前几个做组合查询）。
- `--domain`：业务域词，决定召回哪些业务系统。
- `--language`：JD 主语言，用于加分和短名单多样性；GitHub 的 language 字段按字节统计，可能与项目实际主语言不符（例如 Java 商城被标成 JavaScript），所以语言只作加分，不作硬过滤。
- 若 JD 明确要求硬件 / IoT 方向，追加 `--allow-iot`，并在输出里标注偏硬件方向。

## 回显确认模板

解析后用类似格式回显给用户：

```text
我从这份 JD 解析出：
- 岗位：{岗位}（{经验年限}）
- 硬技术栈：{tech 列表}
- 加分技术：{加分技术}
- 业务域：{domain 列表}
- 职责重点：{职责动词}

我将按这些关键词去 GitHub 找匹配项目。需要增删哪些关键词吗？没问题我就开始搜索。
```
