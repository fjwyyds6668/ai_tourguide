import asyncio
import time
import statistics
import argparse
from collections import Counter

import httpx

DEFAULT_BASE_URL = "http://localhost:18000/api/v1"
DEFAULT_QUERIES = [
    "蜀南竹海有哪些主要景点？",
    "蜀南竹海的开放时间和票价是多少？",
    "帮我推荐一条蜀南竹海一日游路线",
]


def _pctl(values: list[float], p: float) -> float:
    if not values:
        raise ValueError("empty values")
    values_sorted = sorted(values)
    idx = int(round((len(values_sorted) - 1) * p))
    idx = max(0, min(idx, len(values_sorted) - 1))
    return values_sorted[idx]


async def bench_endpoint(
    client: httpx.AsyncClient, base_url: str, path: str, payload: dict, timeout_s: float
):
    url = f"{base_url}{path}"
    try:
        t0 = time.perf_counter()
        resp = await client.post(url, json=payload, timeout=timeout_s)
        dt = (time.perf_counter() - t0) * 1000.0  # ms
        return dt, resp.status_code
    except Exception as e:
        return None, f"EXC:{type(e).__name__}"


async def worker(
    worker_id: int,
    results: list,
    base_url: str,
    path: str,
    timeout_s: float,
    requests_per_user: int,
    queries: list[str],
    payload_builder,
):
    async with httpx.AsyncClient() as client:
        for i in range(requests_per_user):
            query = queries[(worker_id * requests_per_user + i) % len(queries)]
            payload = payload_builder(query)
            dt, code = await bench_endpoint(client, base_url, path, payload, timeout_s)
            results.append((dt, code))


def _build_generate_payload(scenic_name: str | None, character_id: str | None):
    def _builder(query: str):
        return {
            "query": query,
            "use_rag": True,
            "session_id": None,
            "character_id": character_id,
            "scenic_name": scenic_name,
        }

    return _builder


def _build_search_payload(top_k: int):
    def _builder(query: str):
        return {
            "query": query,
            "top_k": top_k,
        }

    return _builder


async def main():
    parser = argparse.ArgumentParser(description="单接口压测脚本（/rag/generate 或 /rag/search）")
    parser.add_argument(
        "--endpoint",
        choices=["generate", "search"],
        default="generate",
        help="选择要压测的接口",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base url，如 http://localhost:18000/api/v1")
    parser.add_argument("--concurrency", type=int, default=3, help="并发用户数")
    parser.add_argument("--requests-per-user", type=int, default=10, help="每个用户请求次数")
    parser.add_argument("--timeout", type=float, default=60.0, help="单请求超时（秒）")

    parser.add_argument("--top-k", type=int, default=5, help="search接口top_k（仅endpoint=search生效）")
    parser.add_argument("--scenic-name", default=None, help="generate接口scenic_name（可选）")
    parser.add_argument("--character-id", default=None, help="generate接口character_id（可选）")

    args = parser.parse_args()

    if args.endpoint == "generate":
        path = "/rag/generate"
        payload_builder = _build_generate_payload(args.scenic_name, args.character_id)
        label = "RAG generate"
    else:
        path = "/rag/search"
        payload_builder = _build_search_payload(args.top_k)
        label = "RAG search"

    results: list[tuple[float | None, int | str]] = []

    tasks = [
        worker(
            i,
            results,
            args.base_url,
            path,
            args.timeout,
            args.requests_per_user,
            DEFAULT_QUERIES,
            payload_builder,
        )
        for i in range(args.concurrency)
    ]

    t_start = time.perf_counter()
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - t_start

    def summarize(name: str, results: list[tuple[float | None, int | str]]):
        total = len(results)
        # 论文结论更建议按“2xx”为成功口径
        ok_times = [
            dt
            for dt, code in results
            if dt is not None and isinstance(code, int) and 200 <= code < 300
        ]
        ok = len(ok_times)
        fail = total - ok
        ok_rate = ok / total if total else 0.0
        tps = total / elapsed if elapsed > 0 else 0.0

        code_counter = Counter()
        exc_counter = Counter()
        for dt, code in results:
            if isinstance(code, int):
                code_counter[code] += 1
            else:
                exc_counter[code] += 1

        if ok_times:
            avg = statistics.mean(ok_times)
            p95 = _pctl(ok_times, 0.95)
            print(
                f"{name}: 总样本={total}, 成功(2xx)={ok}, 失败={fail}, 成功率={ok_rate:.2%}, "
                f"平均={avg:.1f} ms, 95%分位={p95:.1f} ms, 吞吐量={tps:.2f}/s"
            )
        else:
            print(
                f"{name}: 总样本={total}, 成功(2xx)={ok}, 失败={fail}, 成功率={ok_rate:.2%}, "
                f"吞吐量={tps:.2f}/s（无成功样本，无法统计耗时分位）"
            )

        # 打印失败分布，便于定位“超时/连接问题/后端500”等原因
        if code_counter:
            top_codes = ", ".join(f"{k}={v}" for k, v in code_counter.most_common(8))
            print(f"状态码分布(Top): {top_codes}")
        if exc_counter:
            top_excs = ", ".join(f"{k}={v}" for k, v in exc_counter.most_common(8))
            print(f"异常分布(Top): {top_excs}")

    summarize(label, results)


if __name__ == "__main__":
    asyncio.run(main())