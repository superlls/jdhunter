#!/usr/bin/env python3
"""根据 JD 抽取的技术栈 / 业务域关键词搜索 GitHub，构建匹配候选池。

本脚本无第三方依赖，是 JD 驱动找项目流程里"拉源码前"的一步：
先按 JD 关键词广搜，做 README probe、去重、初筛和匹配度打分，
再输出短名单预览供用户确认，确认后才用 pull_github_repos.py 拉源码。

与通用项目选择器的区别：查询和打分都由 JD 关键词驱动，
打分核心是"技术栈重合度 + 业务域吻合度"，而不是固定推荐模式。

用法示例：
    python search_jd_candidates.py \
        --tech spring-boot --tech redis --tech kafka --tech mysql \
        --domain ecommerce --domain order --domain payment \
        --language Java \
        --output jd-candidate-pool.json \
        --shortlist-output jd-shortlist-preview.md

也可追加原始 GitHub 查询：
    --query "spring-cloud order payment stars:1000..50000 pushed:>2024-01-01"
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_REPO_URL = "https://api.github.com/repos/{full_name}"


@dataclass(frozen=True)
class LabeledQuery:
    label: str
    query: str


# 硬排除：明显非业务系统的仓库类型，命中即淘汰。
COMMON_HARD_EXCLUDE = {
    "awesome",
    "tutorial",
    "boilerplate",
    "storefront",
    "ui kit",
    "browser extension",
    "chrome extension",
    "desktop companion",
    "skill collection",
    "prompt collection",
    "cheatsheet",
}

# 软降权：偏框架 / 工具 / 脚手架，不直接淘汰，但匹配分扣分。
COMMON_DOWNRANK = {
    "framework",
    "sdk",
    "library",
    "toolkit",
    "wrapper",
    "starter",
    "template",
    "demo",
    "example",
    "scaffold",
    "plugin",
}

# 默认排除的硬件 / IoT 方向，除非 JD 本身要求。
IOT_EXCLUDE = {
    "iot",
    "embedded",
    "firmware",
    "scada",
    "industrial control",
}


def normalize(term: str) -> str:
    return term.strip().lower()


def build_queries(
    tech: list[str],
    domain: list[str],
    raw_queries: list[str],
    min_stars: int,
    max_stars: int,
    pushed_after: str,
    max_queries: int,
) -> list[LabeledQuery]:
    """从 JD 关键词组合 GitHub 查询。

    策略：
    - 每个业务域词单独成查询（topic 与自由词各一），保证业务系统召回；
    - 业务域词 × 主要技术词 组合查询，召回技术栈吻合的业务项目；
    - 透传用户给定的原始查询。
    """
    star_range = f"{min_stars}..{max_stars}"
    suffix = f"stars:{star_range} pushed:>{pushed_after}"
    queries: list[LabeledQuery] = []
    seen: set[str] = set()

    def add(label: str, q: str) -> None:
        key = q.lower()
        if key in seen:
            return
        seen.add(key)
        queries.append(LabeledQuery(label, q))

    for raw in raw_queries:
        add("自定义查询", raw if "stars:" in raw else f"{raw} {suffix}")

    domain_terms = [normalize(d) for d in domain if d.strip()]
    tech_terms = [normalize(t) for t in tech if t.strip()]

    # 业务域单独查询：topic 命中 + 自由词命中。
    for d in domain_terms:
        add(f"业务域:{d}", f"topic:{d.replace(' ', '-')} {suffix}")
        add(f"业务域:{d}", f"{d} {suffix}")

    # 业务域 × 技术栈组合查询：召回技术栈对得上的业务系统。
    primary_tech = tech_terms[:4]
    for d in domain_terms[:4]:
        for t in primary_tech[:2]:
            add(f"{d}×{t}", f"{t} {d} {suffix}")

    # 若没有业务域，只能靠技术词撑召回。
    if not domain_terms:
        for t in tech_terms[:6]:
            add(f"技术:{t}", f"{t} {suffix}")

    return queries[:max_queries]


def repo_text(repo: dict) -> str:
    values = [
        repo.get("full_name", ""),
        repo.get("description") or "",
        repo.get("language") or "",
        " ".join(repo.get("topics") or []),
        repo.get("readme_probe") or "",
    ]
    return " ".join(values).lower()


def match_score(
    repo: dict,
    tech: list[str],
    domain: list[str],
    language: str | None,
    allow_iot: bool,
) -> tuple[int, list[str], dict]:
    """JD 匹配打分：技术栈重合 + 业务域吻合为核心。

    返回 (分数, 理由列表, 覆盖明细)。覆盖明细用于输出匹配矩阵。
    """
    text = repo_text(repo)
    reasons: list[str] = []
    score = 0

    tech_terms = [normalize(t) for t in tech if t.strip()]
    domain_terms = [normalize(d) for d in domain if d.strip()]

    hit_tech = [t for t in tech_terms if t in text]
    hit_domain = [d for d in domain_terms if d in text]

    # 技术栈：每命中一个 +3。
    score += 3 * len(hit_tech)
    if hit_tech:
        reasons.append(f"技术栈命中:{'/'.join(hit_tech[:5])}")
    # 业务域：每命中一个 +2。
    score += 2 * len(hit_domain)
    if hit_domain:
        reasons.append(f"业务域命中:{'/'.join(hit_domain[:5])}")

    # 主语言吻合 JD：额外加分。
    repo_lang = normalize(repo.get("language") or "")
    if language and repo_lang == normalize(language):
        score += 3
        reasons.append(f"主语言吻合:{repo.get('language')}")

    # 社区验证弱加分（1k 后封顶）。
    stars = int(repo.get("stars") or 0)
    if stars >= 1000:
        score += 2
        reasons.append("1k+ star 社区验证")
    if stars > 20000:
        score -= 1
        reasons.append("过热项目轻微降权")

    # 框架 / 工具 / 脚手架降权。
    downrank_hits = [w for w in COMMON_DOWNRANK if w in text]
    if downrank_hits:
        score -= 3 + len(downrank_hits)
        reasons.append(f"偏框架/工具降权:{'/'.join(downrank_hits[:3])}")

    # 非 JD 要求的 IoT 方向降权。
    if not allow_iot:
        iot_hits = [w for w in IOT_EXCLUDE if w in text]
        if iot_hits:
            score -= 5
            reasons.append(f"IoT/硬件方向降权:{'/'.join(iot_hits[:2])}")

    description = repo.get("description") or ""
    if 20 <= len(description) <= 220:
        score += 1
        reasons.append("描述信息较完整")

    coverage = {
        "tech_total": len(tech_terms),
        "tech_hit": hit_tech,
        "domain_total": len(domain_terms),
        "domain_hit": hit_domain,
        "language_match": bool(language and repo_lang == normalize(language)),
    }
    return score, reasons[:8], coverage


def is_filtered(repo: dict, allow_iot: bool) -> tuple[bool, str]:
    text = repo_text(repo)
    hard = set(COMMON_HARD_EXCLUDE)
    if not allow_iot:
        hard |= IOT_EXCLUDE
    for word in hard:
        if word in text:
            return True, f"硬排除关键词: {word}"
    return False, ""


def github_get(url: str, token: str | None, timeout: int) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "jdhunter",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_readme_probe(full_name: str, token: str | None, timeout: int, max_lines: int) -> tuple[str, str]:
    url = f"{GITHUB_REPO_URL.format(full_name=full_name)}/readme"
    try:
        payload = github_get(url, token, timeout)
        content = payload.get("content") or ""
        encoding = payload.get("encoding") or ""
        if encoding != "base64" or not content:
            return "", "README empty or unsupported encoding"
        raw = base64.b64decode(content, validate=False)
        text = raw.decode("utf-8", errors="ignore")
        lines = text.splitlines()[:max_lines]
        return "\n".join(lines), f"README probe {len(lines)} lines"
    except Exception as exc:  # noqa: BLE001 - README probe 仅尽力而为
        return "", f"README probe failed: {exc}"


def search_repositories(
    queries: Iterable[LabeledQuery],
    per_query: int,
    token: str | None,
    sleep_seconds: float,
    timeout: int,
    readme_lines: int,
) -> list[dict]:
    seen: dict[str, dict] = {}
    for item in queries:
        params = urllib.parse.urlencode(
            {"q": item.query, "sort": "updated", "order": "desc", "per_page": per_query}
        )
        url = f"{GITHUB_SEARCH_URL}?{params}"
        try:
            payload = github_get(url, token, timeout)
        except Exception as exc:  # noqa: BLE001 - 单条查询失败不影响其余
            print(f"QUERY_FAILED label={item.label!r} query={item.query!r} error={exc}", file=sys.stderr)
            time.sleep(sleep_seconds)
            continue

        total = payload.get("total_count", 0)
        print(f"QUERY label={item.label} total={total} query={item.query}")
        for raw in payload.get("items", []):
            full_name = raw.get("full_name", "")
            if not full_name:
                continue
            record = seen.setdefault(
                full_name,
                {
                    "full_name": full_name,
                    "url": raw.get("html_url"),
                    "stars": raw.get("stargazers_count", 0),
                    "language": raw.get("language"),
                    "pushed_at": raw.get("pushed_at"),
                    "description": raw.get("description"),
                    "topics": raw.get("topics", [])[:16],
                    "readme_probe": "",
                    "readme_probe_status": "not probed",
                    "labels": [],
                    "queries": [],
                },
            )
            if item.label not in record["labels"]:
                record["labels"].append(item.label)
            record["queries"].append(item.query)
        time.sleep(sleep_seconds)

    if readme_lines > 0:
        for record in seen.values():
            probe, status = fetch_readme_probe(record.get("full_name") or "", token, timeout, readme_lines)
            record["readme_probe"] = probe
            record["readme_probe_status"] = status
            time.sleep(max(0.05, sleep_seconds / 3))
    return list(seen.values())


def enrich(
    records: list[dict],
    tech: list[str],
    domain: list[str],
    language: str | None,
    allow_iot: bool,
) -> list[dict]:
    enriched = []
    for record in records:
        filtered, filter_reason = is_filtered(record, allow_iot)
        score, reasons, coverage = match_score(record, tech, domain, language, allow_iot)
        copy = dict(record)
        copy["match_score"] = score
        copy["filtered"] = filtered
        copy["filter_reason"] = filter_reason
        copy["match_reasons"] = reasons
        copy["coverage"] = coverage
        copy["label"] = " / ".join(copy.get("labels") or [])
        enriched.append(copy)
    enriched.sort(key=lambda item: (item["filtered"], -item["match_score"], item.get("full_name", "")))
    return enriched


def pick_shortlist(records: list[dict], limit: int) -> list[dict]:
    """优先挑技术栈+业务域覆盖广的，并尽量跨不同语言/标签保证多样性。"""
    shortlist: list[dict] = []
    used_langs: set[str] = set()
    for record in records:
        if record.get("filtered"):
            continue
        lang = (record.get("language") or "").lower()
        if lang in used_langs and len(shortlist) >= 1:
            continue
        shortlist.append(record)
        used_langs.add(lang)
        if len(shortlist) >= limit:
            break
    if len(shortlist) < limit:
        chosen = {item["full_name"] for item in shortlist}
        for record in records:
            if record.get("filtered") or record["full_name"] in chosen:
                continue
            shortlist.append(record)
            if len(shortlist) >= limit:
                break
    return shortlist


def coverage_cell(coverage: dict) -> str:
    t = f"技术 {len(coverage.get('tech_hit') or [])}/{coverage.get('tech_total', 0)}"
    d = f"业务 {len(coverage.get('domain_hit') or [])}/{coverage.get('domain_total', 0)}"
    lang = "语言✓" if coverage.get("language_match") else "语言✗"
    return f"{t}；{d}；{lang}"


def markdown_preview(
    tech: list[str],
    domain: list[str],
    language: str | None,
    records: list[dict],
    shortlist: list[dict],
    output: Path,
) -> None:
    filtered = [record for record in records if record.get("filtered")]
    lines = [
        "# JD 匹配项目短名单确认",
        "",
        f"> 生成时间：{datetime.now(timezone.utc).isoformat()}",
        f"> JD 技术栈：{', '.join(tech) or '（未提供）'}",
        f"> JD 业务域：{', '.join(domain) or '（未提供）'}",
        f"> 目标主语言：{language or '（不限）'}",
        "",
        "## 建议拉取短名单",
        "",
        "| 项目 | 链接 | 语言 | Star | 匹配分 | JD 覆盖 | 匹配理由 |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for item in shortlist:
        reasons = "；".join(item.get("match_reasons") or [])
        lines.append(
            f"| {item['full_name']} | {item.get('url')} | {item.get('language') or ''} | "
            f"{item.get('stars') or 0} | {item.get('match_score')} | "
            f"{coverage_cell(item.get('coverage') or {})} | {reasons} |"
        )

    lines.extend(
        [
            "",
            "## 初筛淘汰样例",
            "",
            "| 项目 | 链接 | 语言 | 淘汰 / 降权理由 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in filtered[:20]:
        lines.append(
            f"| {item['full_name']} | {item.get('url')} | {item.get('language') or ''} | {item.get('filter_reason')} |"
        )

    lines.extend(
        [
            "",
            "## 下一步",
            "",
            "请先确认短名单方向；确认后再运行 `pull_github_repos.py` 拉取源码并做本地源码验证。",
            "“JD 覆盖”仅来自 README probe 与描述，只能用于初筛，最终负责功能必须来自本地源码验证。",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 JD 关键词搜索 GitHub，构建匹配候选池。")
    parser.add_argument("--tech", action="append", default=[], help="JD 技术栈关键词，可重复传入。")
    parser.add_argument("--domain", action="append", default=[], help="JD 业务域关键词，可重复传入。")
    parser.add_argument("--query", action="append", default=[], dest="raw_queries", help="原始 GitHub 查询，可重复传入。")
    parser.add_argument("--language", default=None, help="目标主语言（用于加分与多样性），如 Java/Go/Python。")
    parser.add_argument("--allow-iot", action="store_true", help="JD 本身要求硬件/IoT 时放开默认排除。")
    parser.add_argument("--output", type=Path, default=Path("jd-candidate-pool.json"))
    parser.add_argument("--shortlist-output", type=Path, default=Path("jd-shortlist-preview.md"))
    parser.add_argument("--shortlist", type=int, default=4, help="短名单预览数量。")
    parser.add_argument("--per-query", type=int, default=10, help="每条查询返回数，建议 ≤20。")
    parser.add_argument("--min-stars", type=int, default=1000)
    parser.add_argument("--max-stars", type=int, default=50000)
    parser.add_argument("--pushed-after", default="2024-01-01")
    parser.add_argument("--max-queries", type=int, default=16, help="查询条数上限，控制速率与配额。")
    parser.add_argument("--sleep", type=float, default=1.2, help="查询之间的间隔秒数。")
    parser.add_argument("--timeout", type=int, default=35)
    parser.add_argument("--readme-lines", type=int, default=40, help="README probe 行数，0 表示跳过。")
    parser.add_argument("--token-env", default="GITHUB_TOKEN", help="读取 GitHub token 的环境变量名。")
    return parser.parse_args()


def main() -> int:
    import os

    args = parse_args()
    if not args.tech and not args.domain and not args.raw_queries:
        print("ERROR: 至少要提供 --tech / --domain / --query 之一", file=sys.stderr)
        return 2

    token = os.environ.get(args.token_env) or None
    queries = build_queries(
        args.tech,
        args.domain,
        args.raw_queries,
        args.min_stars,
        args.max_stars,
        args.pushed_after,
        args.max_queries,
    )
    if not queries:
        print("ERROR: 未能从输入构建任何查询", file=sys.stderr)
        return 2

    records = search_repositories(
        queries,
        per_query=args.per_query,
        token=token,
        sleep_seconds=args.sleep,
        timeout=args.timeout,
        readme_lines=args.readme_lines,
    )
    enriched = enrich(records, args.tech, args.domain, args.language, args.allow_iot)
    shortlist = pick_shortlist(enriched, args.shortlist)

    args.output.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_preview(args.tech, args.domain, args.language, enriched, shortlist, args.shortlist_output)

    print(f"CANDIDATES: {args.output} ({len(enriched)} repos)")
    print(f"SHORTLIST: {args.shortlist_output} ({len(shortlist)} repos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
