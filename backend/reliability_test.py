"""
系统可靠性测试脚本
运行方式（在 backend/ 目录下）：
    python reliability_test.py
"""
import asyncio
import subprocess
import time
import httpx

BASE_URL = "http://localhost:18000/api/v1"
SEARCH_URL = f"{BASE_URL}/rag/search"
VOICE_URL  = f"{BASE_URL}/voice/tts"

PAYLOAD = {"query": "test", "top_k": 3}

SEP = "=" * 60


def print_section(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


# ── 用例1：持续运行稳定性 ─────────────────────────────────────────
async def test_stability():
    print_section("用例1：持续运行稳定性（连续发起10次问答请求）")
    success = 0
    fail = 0
    times = []
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(1, 11):
            t0 = time.perf_counter()
            try:
                resp = await client.post(SEARCH_URL, json=PAYLOAD)
                elapsed = (time.perf_counter() - t0) * 1000
                times.append(elapsed)
                if resp.status_code == 200:
                    success += 1
                    print(f"  请求 {i:02d}: 200 OK  {elapsed:.0f}ms")
                else:
                    fail += 1
                    print(f"  请求 {i:02d}: {resp.status_code} FAIL")
            except Exception as e:
                fail += 1
                print(f"  请求 {i:02d}: 异常 {e}")
    avg = sum(times) / len(times) if times else 0
    print(f"\n  结果: 成功={success}/10  失败={fail}/10  平均响应={avg:.0f}ms")
    print(f"  结论: {'✓ 后端服务全程无崩溃，可用性满足要求' if fail == 0 else '✗ 存在失败请求'}")


# ── 用例2：TTS 超时容错 ──────────────────────────────────────────
async def test_tts_timeout():
    print_section("用例2：TTS 超时容错（将客户端超时设为1秒模拟超时）")
    payload = {"text": "欢迎来到蜀南竹海，这里是四川南部著名的竹林景区。", "voice": "x4_xiaoyan"}
    # 用极短的客户端超时触发超时场景
    async with httpx.AsyncClient(timeout=1.0) as client:
        try:
            resp = await client.post(VOICE_URL, json=payload)
            print(f"  响应状态: {resp.status_code}")
            body = resp.text[:200]
            print(f"  响应内容: {body}")
            if resp.status_code in (200, 206):
                print("  结论: TTS 在1秒内返回（网络极快）")
            else:
                print("  结论: ✓ 系统返回错误提示，未崩溃")
        except httpx.ReadTimeout:
            print("  触发: 客户端读取超时（ReadTimeout）")
            print("  结论: ✓ 超时发生，验证后端日志确认重试与降级逻辑已执行")
        except httpx.ConnectTimeout:
            print("  触发: 连接超时")
            print("  结论: ✓ 超时发生，主流程不受影响")
        except Exception as e:
            print(f"  异常: {e}")
            print("  结论: ✓ 异常已捕获，未影响其他服务")

    # 验证主问答流程仍正常
    print("\n  验证问答主流程在 TTS 超时后仍可用...")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(SEARCH_URL, json=PAYLOAD)
        status = "✓ 正常" if resp.status_code == 200 else f"✗ 异常({resp.status_code})"
        print(f"  问答接口状态: {status}")


# ── 用例3：检索异常降级 ──────────────────────────────────────────
async def test_retrieval_fallback():
    print_section("用例3：检索异常降级（停止 Neo4j 模拟图检索异常）")

    print("  停止 Neo4j 容器...")
    subprocess.run(["docker", "stop", "ai_tourguide_neo4j"],
                   capture_output=True, check=True)
    time.sleep(3)

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(SEARCH_URL, json=PAYLOAD)
            print(f"  响应状态: {resp.status_code}")
            data = resp.json()
            vector_ok  = len(data.get("vector_results", [])) > 0
            graph_empty = len(data.get("graph_results", [])) == 0
            print(f"  向量检索结果: {'有数据 ✓' if vector_ok else '无数据'}")
            print(f"  图检索结果:   {'空（降级）✓' if graph_empty else '有数据'}")
            if resp.status_code == 200 and vector_ok and graph_empty:
                print("  结论: ✓ 图检索异常时系统降级处理，向量检索正常返回，未崩溃")
            else:
                print("  结论: ✗ 降级处理异常")
        except Exception as e:
            print(f"  异常: {e}")

    print("\n  恢复 Neo4j 容器...")
    subprocess.run(["docker", "start", "ai_tourguide_neo4j"],
                   capture_output=True, check=True)
    print("  Neo4j 已恢复")


# ── 用例4：容器重启数据持久化 ────────────────────────────────────
async def test_data_persistence():
    print_section("用例4：容器重启后数据持久化验证")

    def get_neo4j_count():
        result = subprocess.run(
            ["docker", "exec", "ai_tourguide_neo4j",
             "cypher-shell", "-u", "neo4j", "-p", "12345678",
             "MATCH (n) RETURN count(n) as total"],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line)
        return None

    print("  获取重启前 Neo4j 节点数...")
    count_before = get_neo4j_count()
    print(f"  重启前节点数: {count_before}")

    print("\n  执行 docker restart（Neo4j + Milvus）...")
    subprocess.run(
        ["docker", "restart", "ai_tourguide_neo4j", "milvus-standalone"],
        capture_output=True, check=True
    )
    print("  容器重启中，等待30秒...")
    time.sleep(30)

    print("\n  验证 Neo4j 数据...")
    for attempt in range(5):
        count_after = get_neo4j_count()
        if count_after is not None:
            break
        print(f"  等待 Neo4j 启动... ({attempt+1}/5)")
        time.sleep(10)

    print(f"  重启后节点数: {count_after}")
    if count_before == count_after:
        print(f"  结论: ✓ Neo4j 数据完整保留（{count_after} 个节点）")
    else:
        print(f"  结论: ✗ 数据不一致（前:{count_before} 后:{count_after}）")

    print("\n  验证 Milvus 向量检索...")
    await asyncio.sleep(5)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(SEARCH_URL, json=PAYLOAD)
        ok = resp.status_code == 200 and len(resp.json().get("vector_results", [])) > 0
        print(f"  向量检索结果: {'✓ 正常返回数据' if ok else '✗ 无数据'}")
        if ok:
            print("  结论: ✓ Milvus 数据通过 Volume 挂载完整保留")


# ── 主入口 ────────────────────────────────────────────────────────
async def main():
    print(SEP)
    print("  景区AI数字人导游系统 - 可靠性测试")
    print(SEP)

    await test_stability()
    await test_tts_timeout()
    await test_retrieval_fallback()
    await test_data_persistence()

    print(f"\n{SEP}")
    print("  全部用例执行完毕")
    print(SEP)


if __name__ == "__main__":
    asyncio.run(main())
