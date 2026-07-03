"""全搜索引擎链路探针。

只调用各引擎的 search 层,不走 ContentFetcher 和 LLM summarize。用于快速确认
每个引擎在当前 config/proxy/API key 下是否可用、耗时和结果质量概况。

运行方式(在项目根目录 ``E:\\MaiM-with-u\\MaiBot``):

    uv run python -m plugins.google_search_plugin.tests.all_engines_probe
    uv run python -m plugins.google_search_plugin.tests.all_engines_probe "Python 3.13 新特性"

可选环境变量:
    ALL_ENGINES_PROBE_QUERY="Python 3.13 新特性"
    ALL_ENGINES_PROBE_MAX_RESULTS=5
    ALL_ENGINES_PROBE_TIMEOUT=45
    ALL_ENGINES_PROBE_FORCE_ENABLE=true
    ALL_ENGINES_PROBE_PROXY=http://127.0.0.1:7899
    ALL_ENGINES_PROBE_PROXY=none  # 强制直连,不使用 config.toml 里的 proxy
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from plugins.google_search_plugin.config import GoogleSearchPluginConfig  # noqa: E402
from plugins.google_search_plugin.pipelines.engine_chain import EngineChain  # noqa: E402

DEFAULT_QUERY = "Python 3.13 新特性"
DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT_SECONDS = 45


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_config() -> GoogleSearchPluginConfig:
    cfg_path = Path(__file__).resolve().parents[1] / "config.toml"
    with cfg_path.open("rb") as file:
        raw = tomllib.load(file)
    return GoogleSearchPluginConfig(**raw)


def _force_enable_all_engines(cfg: GoogleSearchPluginConfig) -> None:
    engines = cfg.engines
    engines.google_enabled = True
    engines.bing_enabled = True
    engines.sogou_enabled = True
    engines.duckduckgo_enabled = True
    engines.tavily_enabled = True
    engines.you_enabled = True
    engines.you_news_enabled = True


def _override_proxy(cfg: GoogleSearchPluginConfig) -> None:
    proxy_env = os.environ.get("ALL_ENGINES_PROBE_PROXY")
    if proxy_env is None:
        return
    if proxy_env.strip().lower() in {"none", "direct", "off"}:
        cfg.search_backend.proxy = ""
        return
    cfg.search_backend.proxy = proxy_env.strip()


def _engine_entries(chain: EngineChain) -> list[tuple[str, Any]]:
    return [
        ("google", chain.google),
        ("bing", chain.bing),
        ("sogou", chain.sogou),
        ("duckduckgo", chain.duckduckgo),
        ("tavily", chain.tavily),
        ("you", chain.you),
        ("you_news", chain.you_news),
    ]


def _truncate(text: str, limit: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "..."


async def _probe_engine(
    name: str,
    engine: Any,
    query: str,
    max_results: int,
    timeout_seconds: int,
) -> None:
    started = time.monotonic()
    try:
        results = await asyncio.wait_for(engine.search(query, max_results), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        print(f"\n[{name}] timeout (> {timeout_seconds}s)")
        return
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - started
        print(f"\n[{name}] {elapsed:.1f}s exception: {type(exc).__name__}: {exc}")
        return

    elapsed = time.monotonic() - started
    print(f"\n[{name}] {elapsed:.1f}s {len(results)} results")
    for result in results[:3]:
        title = _truncate(result.title or "<no title>", 45)
        snippet_len = len(result.snippet or "")
        print(f"  - {title} | snippet={snippet_len}ch | {_truncate(result.url or '', 70)}")
    if name == "tavily" and getattr(engine, "last_answer", None):
        print(f"  [answer] {_truncate(engine.last_answer, 120)!r}")


async def main(argv: list[str]) -> int:
    query = " ".join(argv).strip() or os.environ.get("ALL_ENGINES_PROBE_QUERY", DEFAULT_QUERY)
    max_results = int(os.environ.get("ALL_ENGINES_PROBE_MAX_RESULTS", str(DEFAULT_MAX_RESULTS)))
    timeout_seconds = int(os.environ.get("ALL_ENGINES_PROBE_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))
    force_enable = _env_bool("ALL_ENGINES_PROBE_FORCE_ENABLE", True)

    cfg = _load_config()
    _override_proxy(cfg)
    if force_enable:
        _force_enable_all_engines(cfg)

    chain = EngineChain(cfg.engines, cfg.search_backend)
    print(
        f"query={query!r} max_results={max_results} timeout={timeout_seconds}s "
        f"proxy={cfg.search_backend.proxy!r} force_enable={force_enable}"
    )
    print("=" * 80)

    for name, engine in _engine_entries(chain):
        if not getattr(cfg.engines, f"{name}_enabled", False):
            print(f"\n[{name}] disabled")
            continue
        await _probe_engine(name, engine, query, max_results, timeout_seconds)

    print("\n" + "=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
