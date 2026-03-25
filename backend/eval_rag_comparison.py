"""
GraphRAG 三种检索方法对比评估脚本
======================================
运行方式（在 backend/ 目录下）：
    python eval_rag_comparison.py

结果输出：
    eval_results_<时间戳>.csv  —— 每行是一个问题×方法的结果，含检索上下文、回答、召回命中
    eval_summary_<时间戳>.txt  —— 汇总各类别各方法的信息召回率

评分说明：
    - 信息召回率：自动计算（期望关键词是否出现在检索上下文中）
    - 回答相关性：在 CSV 的 relevance_score 列手动填写 1-5 分

注意：运行前确保后端服务依赖（数据库/Milvus/Neo4j）均已启动。
"""

import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Tuple, Optional

# ── 路径设置 ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

# 加载 .env（如果有）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

# ── 测试问题集 ─────────────────────────────────────────────────────
# 格式: (问题文本, 期望关键词列表, 问题类别)
# 期望关键词：答案中至少应出现其中一个词才算"信息召回成功"
# ⚠ 请根据你的知识库实际内容修改/补充，凑满每类问题数量

TEST_QUESTIONS: List[Tuple[str, List[str], str]] = [
    # ────────── 景点详情（共20条）──────────
    ("蜀南竹海有哪些主要景点？",             ["翡翠长廊", "天宝寨", "仙寓洞", "龙吟寺", "忘忧谷"],    "景点详情"),
    ("翡翠长廊的特色是什么？",               ["翡翠", "竹", "长廊", "绿色"],                         "景点详情"),
    ("天宝寨的历史背景是什么？",             ["天宝寨", "历史", "古寨", "明朝", "清朝"],              "景点详情"),
    ("仙寓洞有什么传说或典故？",             ["仙寓洞", "传说", "道教", "仙人"],                     "景点详情"),
    ("蜀南竹海的竹子主要有哪些品种？",       ["楠竹", "竹", "品种", "毛竹"],                         "景点详情"),
    ("龙吟寺的建筑风格是怎样的？",           ["龙吟寺", "寺庙", "建筑", "佛教"],                     "景点详情"),
    ("忘忧谷的观光内容有哪些？",             ["忘忧谷", "竹", "峡谷", "溪流"],                       "景点详情"),
    ("蜀南竹海景区的面积有多大？",           ["面积", "公顷", "万亩", "平方"],                       "景点详情"),
    ("竹海的门票价格是多少？",               ["门票", "价格", "元", "票价"],                         "景点详情"),
    ("蜀南竹海景区的开放时间是什么？",       ["开放", "时间", "营业", "游览"],                       "景点详情"),
    ("万岭箐的景观有什么特点？",             ["万岭箐", "竹海", "景观", "竹林"],                     "景点详情"),
    ("蜀南竹海有哪些观景台？",               ["观景台", "观景", "高处", "俯瞰"],                     "景点详情"),
    ("青龙湖的特色是什么？",                 ["青龙湖", "湖", "水", "倒影"],                         "景点详情"),
    ("蜀南竹海景区内有哪些餐饮设施？",       ["餐饮", "餐厅", "美食", "饮食"],                       "景点详情"),
    ("蜀南竹海适合哪个季节游览？",           ["季节", "春", "夏", "秋", "四季", "全年"],             "景点详情"),
    ("飞瀑群的景观特色是什么？",             ["飞瀑", "瀑布", "水帘", "溪流"],                       "景点详情"),
    ("蜀南竹海的气候特点是什么？",           ["气候", "温度", "湿度", "凉爽"],                       "景点详情"),
    ("竹海内的竹林步道有多长？",             ["步道", "竹林", "公里", "米", "小径"],                 "景点详情"),
    ("蜀南竹海有哪些住宿选择？",             ["住宿", "酒店", "民宿", "客栈"],                       "景点详情"),
    ("蜀南竹海离宜宾市区有多远？",           ["宜宾", "距离", "公里", "车程"],                       "景点详情"),

    # ────────── 路线推荐（共15条）──────────
    ("蜀南竹海一日游推荐路线是什么？",       ["路线", "一日游", "景点", "建议"],                     "路线推荐"),
    ("从翡翠长廊到天宝寨怎么走？",           ["翡翠长廊", "天宝寨", "路线", "步行", "路程"],         "路线推荐"),
    ("竹海两日游怎么安排行程？",             ["两日游", "行程", "安排", "第一天", "第二天"],          "路线推荐"),
    ("带孩子游竹海推荐哪些景点？",           ["儿童", "孩子", "适合", "景点", "安全"],               "路线推荐"),
    ("老人游竹海应该走哪条路线？",           ["老人", "轻松", "平缓", "路线", "建议"],               "路线推荐"),
    ("竹海摄影打卡推荐去哪里？",             ["摄影", "拍照", "打卡", "景色"],                       "路线推荐"),
    ("从宜宾出发怎么去蜀南竹海？",           ["宜宾", "交通", "路线", "怎么去", "大巴", "自驾"],     "路线推荐"),
    ("蜀南竹海的核心景区怎么游览？",         ["核心景区", "游览", "路线", "主要"],                   "路线推荐"),
    ("想看瀑布应该去竹海哪里？",             ["瀑布", "飞瀑", "景点", "位置"],                       "路线推荐"),
    ("竹海半日游推荐路线是什么？",           ["半日游", "路线", "时间", "景点"],                     "路线推荐"),
    ("竹海骑行路线有哪些推荐？",             ["骑行", "路线", "自行车", "竹林"],                     "路线推荐"),
    ("春节期间游竹海有什么建议？",           ["春节", "节假日", "人流", "建议", "提前"],             "路线推荐"),
    ("从成都去蜀南竹海需要多久？",           ["成都", "时间", "小时", "交通"],                       "路线推荐"),
    ("竹海附近有哪些景点可以顺路游览？",     ["附近", "景点", "宜宾", "顺路", "周边"],               "路线推荐"),
    ("竹海雨天游览有哪些注意事项？",         ["雨天", "注意", "安全", "雨具", "防滑"],               "路线推荐"),

    # ────────── 历史文化（共15条）──────────
    ("蜀南竹海的历史渊源是什么？",           ["历史", "古代", "年", "发展"],                         "历史文化"),
    ("竹在中国传统文化中有什么象征意义？",   ["竹", "文化", "象征", "君子", "气节"],                 "历史文化"),
    ("蜀南竹海与哪些历史名人有关？",         ["名人", "历史", "诗人", "文化人", "典故"],             "历史文化"),
    ("竹海有哪些与竹文化相关的民俗活动？",   ["民俗", "活动", "文化", "节日", "传统"],               "历史文化"),
    ("当地居民如何利用竹子？",               ["竹", "竹制品", "编织", "建筑", "生活"],               "历史文化"),
    ("蜀南竹海的文化遗产有哪些？",           ["文化遗产", "历史", "保护", "遗址"],                   "历史文化"),
    ("竹林七贤与竹文化有什么关系？",         ["竹林七贤", "文化", "隐士", "竹", "历史"],             "历史文化"),
    ("四川竹文化有哪些特色？",               ["四川", "竹文化", "特色", "历史"],                     "历史文化"),
    ("蜀南竹海地区有哪些历史建筑？",         ["历史建筑", "古建筑", "庙宇", "寨子"],                 "历史文化"),
    ("蜀南竹海是什么时候开始开发旅游的？",   ["开发", "旅游", "年份", "历史"],                       "历史文化"),
    ("竹海地区的传统饮食文化是什么？",       ["饮食", "传统", "特色", "美食", "竹笋"],               "历史文化"),
    ("蜀南竹海获得过哪些荣誉称号？",         ["荣誉", "称号", "国家", "评级", "AAAA", "AAAAA"],      "历史文化"),
    ("蜀南竹海的生态保护情况如何？",         ["生态", "保护", "环境", "自然保护区"],                 "历史文化"),
    ("竹笋采集有哪些传统习俗？",             ["竹笋", "采集", "传统", "习俗", "季节"],               "历史文化"),
    ("蜀南竹海周边有哪些少数民族文化？",     ["少数民族", "文化", "民族", "习俗"],                   "历史文化"),
]


# ── 核心评估逻辑 ──────────────────────────────────────────────────

def keyword_recall(context: str, keywords: List[str]) -> Tuple[bool, List[str]]:
    """检查期望关键词中是否至少有一个出现在检索上下文中。"""
    if not context:
        return False, []
    hit = [kw for kw in keywords if kw in context]
    return len(hit) > 0, hit


async def run_vector_only(service, query: str, top_k: int = 5) -> Tuple[str, str]:
    """纯向量检索：只用 Milvus 向量结果构造上下文，不含图检索。"""
    try:
        results = await service.vector_search(query, top_k=top_k)
        if not results:
            return "", ""
        # 将向量结果拼接为上下文
        context_parts = []
        for item in results[:top_k]:
            text = item.get("text") or item.get("content") or str(item)
            if text:
                context_parts.append(text.strip())
        context = "\n".join(context_parts)
        return context, json.dumps(results, ensure_ascii=False)[:500]
    except Exception as e:
        return "", f"ERROR: {e}"


async def run_graph_only(service, query: str, top_k: int = 5) -> Tuple[str, str]:
    """纯图检索：只用 Neo4j 图检索结果构造上下文，不含向量检索。"""
    try:
        # 先做 hybrid_search 但只取 graph_results 部分
        result = await service.hybrid_search(query, top_k=top_k)
        graph_results = result.get("graph_results", [])
        if not graph_results:
            return "", "no graph results"
        context_parts = []
        for item in graph_results[:top_k]:
            text = item.get("text") or item.get("content") or item.get("summary") or str(item)
            if text:
                context_parts.append(str(text).strip())
        context = "\n".join(context_parts)
        return context, json.dumps(graph_results, ensure_ascii=False)[:500]
    except Exception as e:
        return "", f"ERROR: {e}"


async def run_graphrag_hybrid(service, query: str, top_k: int = 5) -> Tuple[str, str]:
    """GraphRAG 混合检索：使用完整的 hybrid_search 增强上下文。"""
    try:
        result = await service.hybrid_search(query, top_k=top_k)
        context = result.get("enhanced_context", "") or ""
        debug = json.dumps({
            "intent": result.get("intent"),
            "strategy": result.get("strategy"),
            "vector_count": len(result.get("vector_results", [])),
            "graph_count": len(result.get("graph_results", [])),
        }, ensure_ascii=False)
        return context, debug
    except Exception as e:
        return "", f"ERROR: {e}"


async def generate_with_context(service, query: str, context: str) -> str:
    """用给定的上下文生成回答。"""
    try:
        result = await service.generate_answer(
            query=query,
            context=context if context else "无额外上下文信息",
            use_rag=False,  # 不再重新检索，直接用传入的 context
        )
        return result.get("answer", "")
    except Exception as e:
        return f"生成失败: {e}"


async def run_evaluation():
    # ── 延迟导入（等环境变量就位）──────────────────────────────────
    from app.services.rag_service import rag_service

    print("=" * 60)
    print("GraphRAG 三种检索方法对比评估")
    print("=" * 60)
    print(f"测试问题总数: {len(TEST_QUESTIONS)}")
    print("等待嵌入模型加载（最多 60s）...")

    # 等待模型就绪
    for _ in range(60):
        if rag_service._model_ready.is_set():
            break
        await asyncio.sleep(1)
    else:
        print("⚠ 模型加载超时，继续运行（部分结果可能为空）")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = f"eval_results_{timestamp}.csv"
    summary_path = f"eval_summary_{timestamp}.txt"

    METHODS = ["纯向量检索", "纯图检索", "GraphRAG混合"]

    rows = []
    # 统计结构: {类别: {方法: [recall_bool]}}
    stats: Dict[str, Dict[str, List[bool]]] = {}

    total = len(TEST_QUESTIONS) * len(METHODS)
    done = 0

    for q_text, keywords, category in TEST_QUESTIONS:
        if category not in stats:
            stats[category] = {m: [] for m in METHODS}

        print(f"\n[{category}] {q_text[:40]}...")

        for method in METHODS:
            done += 1
            print(f"  ({done}/{total}) {method} ...", end="", flush=True)

            t0 = time.monotonic()
            context = ""
            debug_info = ""

            try:
                if method == "纯向量检索":
                    context, debug_info = await run_vector_only(rag_service, q_text)
                elif method == "纯图检索":
                    context, debug_info = await run_graph_only(rag_service, q_text)
                else:  # GraphRAG混合
                    context, debug_info = await run_graphrag_hybrid(rag_service, q_text)

                # 生成回答（用各自的上下文）
                answer = await generate_with_context(rag_service, q_text, context)
            except Exception as e:
                context = ""
                answer = f"ERROR: {e}"
                debug_info = str(e)

            elapsed = time.monotonic() - t0
            recalled, hit_words = keyword_recall(context, keywords)

            print(f" 召回={'✓' if recalled else '✗'} ({elapsed:.1f}s)")

            stats[category][method].append(recalled)
            rows.append({
                "category":         category,
                "question":         q_text,
                "method":           method,
                "recalled":         "是" if recalled else "否",
                "hit_keywords":     "、".join(hit_words),
                "context_preview":  context[:300].replace("\n", " "),
                "answer_preview":   answer[:300].replace("\n", " "),
                "elapsed_s":        f"{elapsed:.2f}",
                "relevance_score":  "",   # ← 人工填写 1-5
                "debug":            debug_info[:200],
            })

    # ── 写 CSV ──────────────────────────────────────────────────
    fieldnames = ["category", "question", "method", "recalled", "hit_keywords",
                  "context_preview", "answer_preview", "elapsed_s",
                  "relevance_score", "debug"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n✅ 详细结果已保存: {csv_path}")

    # ── 计算汇总 ────────────────────────────────────────────────
    lines = ["GraphRAG 检索方法对比汇总", "=" * 50, ""]
    all_categories = list(stats.keys())
    for cat in all_categories:
        lines.append(f"【{cat}】共 {len([q for q,_,c in TEST_QUESTIONS if c==cat])} 题")
        for method in METHODS:
            recalls = stats[cat][method]
            if recalls:
                rate = sum(recalls) / len(recalls) * 100
                lines.append(f"  {method:12s}: 信息召回率 {rate:.0f}%  ({sum(recalls)}/{len(recalls)})")
        lines.append("")

    # 整体汇总
    lines.append("【整体汇总】")
    for method in METHODS:
        all_recalls = []
        for cat in all_categories:
            all_recalls.extend(stats[cat][method])
        if all_recalls:
            rate = sum(all_recalls) / len(all_recalls) * 100
            lines.append(f"  {method:12s}: 整体信息召回率 {rate:.0f}%  ({sum(all_recalls)}/{len(all_recalls)})")

    lines.append("")
    lines.append("注：回答相关性（1-5分）请打开 CSV 文件人工评分后统计。")

    summary_text = "\n".join(lines)
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)

    print("\n" + summary_text)
    print(f"\n✅ 汇总已保存: {summary_path}")
    print(f"\n📝 下一步：打开 {csv_path}，在 relevance_score 列填写 1-5 分，汇总各方法平均分。")


if __name__ == "__main__":
    asyncio.run(run_evaluation())
