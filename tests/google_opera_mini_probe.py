"""Google Opera Mini 兼容模式探针。

只测试 GoogleEngine 当前的轻量请求路径,不走 ContentFetcher 和 LLM summarize。
用于确认当前代理/IP 是否能通过 ``client=ms-opera-mini`` 拿到基础 HTML SERP。

运行方式(在项目根目录 ``E:\\MaiM-with-u\\MaiBot``):

    uv run python -m plugins.google_search_plugin.tests.google_opera_mini_probe
    uv run python -m plugins.google_search_plugin.tests.google_opera_mini_probe "Python 3.13 新特性"

可选环境变量:
    GOOGLE_OPERA_PROBE_QUERY="Python 3.13 新特性"
    GOOGLE_OPERA_PROBE_MAX_RESULTS=5
    GOOGLE_OPERA_PROBE_TIMEOUT=20
    GOOGLE_OPERA_PROBE_LANGUAGE=zh-cn
    GOOGLE_OPERA_PROBE_PROXY=http://127.0.0.1:7890
    GOOGLE_OPERA_PROBE_PROXY=none  # 强制直连,不读取 HTTP_PROXY / HTTPS_PROXY
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import List

from bs4 import BeautifulSoup

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from plugins.google_search_plugin.search_engines.google import GoogleEngine  # noqa: E402


DEFAULT_QUERY = "Python 3.13 新特性"


def _truncate(text: str, limit: int = 100) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "..."


async def main(argv: List[str]) -> int:
    query = " ".join(argv).strip() or os.environ.get("GOOGLE_OPERA_PROBE_QUERY", DEFAULT_QUERY)
    max_results = int(os.environ.get("GOOGLE_OPERA_PROBE_MAX_RESULTS", "5"))
    timeout = int(os.environ.get("GOOGLE_OPERA_PROBE_TIMEOUT", "20"))
    language = os.environ.get("GOOGLE_OPERA_PROBE_LANGUAGE", "zh-cn")
    proxy_env = os.environ.get("GOOGLE_OPERA_PROBE_PROXY")
    if proxy_env and proxy_env.strip().lower() in {"none", "direct", "off"}:
        proxy = None
    else:
        proxy = proxy_env or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

    engine = GoogleEngine(
        {
            "language": language,
            "proxy": proxy or None,
            "timeout": timeout,
            "max_results": max_results,
        }
    )
    url = engine._build_url(query)  # noqa: SLF001 - diagnostic probe for this engine only.
    try:
        status, final_url, html = await engine._fetch(url)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        print(f"query={query!r} language={language!r} proxy={proxy!r} max_results={max_results}")
        print(f"url={url}")
        print(f"exception={type(exc).__name__}: {exc}")
        return 1

    soup = BeautifulSoup(html, "html.parser")
    parsed = engine._parse(html)  # noqa: SLF001

    print(f"query={query!r} language={language!r} proxy={proxy!r} max_results={max_results}")
    print(f"url={url}")
    print(f"status={status} final_url={final_url}")
    print(
        f"html_len={len(html)} h3={len(soup.select('h3'))} "
        f"captcha={engine._is_captcha(status, final_url, html)} "  # noqa: SLF001
        f"javascript_wall={engine._is_javascript_wall(status, html)}"  # noqa: SLF001
    )
    title = soup.title.string if soup.title and soup.title.string else ""
    if title:
        print(f"title={title}")

    print(f"parsed_results={len(parsed)}")
    for result in parsed[:max_results]:
        print(
            f"  - rank={result.rank} title={_truncate(result.title, 70)} "
            f"snippet={len(result.snippet or '')}ch url={_truncate(result.url, 120)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
