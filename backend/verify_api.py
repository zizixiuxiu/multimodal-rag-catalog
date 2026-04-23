#!/usr/bin/env python3
"""端到端 API 验证脚本 —— 启动服务并验证所有端点。"""

import json
import subprocess
import sys
import time
import urllib.request
from urllib.error import HTTPError

BASE_URL = "http://localhost:8000"
PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"

results = []


def log(msg, level="info"):
    prefix = {"info": "  ", "pass": "  ", "fail": "  ", "warn": "  "}.get(level, "  ")
    print(f"{prefix}{msg}")


def check(name, condition, detail=""):
    if condition:
        results.append((name, True, detail))
        log(f"{PASS} {name}", "pass")
        return True
    else:
        results.append((name, False, detail))
        log(f"{FAIL} {name} — {detail}", "fail")
        return False


def http_get(path, timeout=15):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


def http_post(path, data, timeout=60):
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}


def http_post_file(path, fields, timeout=30):
    """Multipart file upload using pure stdlib."""
    import uuid
    boundary = uuid.uuid4().hex
    url = f"{BASE_URL}{path}"
    body_parts = []
    for name, (filename, content, mimetype) in fields.items():
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode())
        body_parts.append(f"Content-Type: {mimetype}\r\n\r\n".encode())
        body_parts.append(content if isinstance(content, bytes) else content.encode())
        body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(body_parts)
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}


def verify():
    print("=" * 60)
    print("Multimodal RAG Catalog — API 端到端验证")
    print("=" * 60)

    # ── 1. Health ──────────────────────────────────────────────
    print("\n▶ Health 检查")
    try:
        code, data = http_get("/api/health")
        check("/api/health 返回 200", code == 200)
        check("/api/health 包含 status", "status" in data)
        check("/api/health 包含 version", "version" in data)
    except Exception as e:
        check("/api/health 可访问", False, str(e))

    # ── 2. Chat / Query ────────────────────────────────────────
    print("\n▶ Chat 查询端点")

    # 2a 价格查询
    try:
        code, data = http_post("/api/chat/query", {"query": "MX-A01 咖啡灰 18mm 多少钱？"}, timeout=90)
        ok = check("价格查询返回 200", code == 200)
        if ok:
            check("价格查询包含 answer", "answer" in data and len(data["answer"]) > 0)
            check("价格查询 intent=query_price", data.get("intent") == "query_price")
            check("价格查询包含 model_no", data.get("model_no") is not None)
            # 验证价格数字在回答中
            has_price = any(ch.isdigit() for ch in data.get("answer", ""))
            check("价格查询回答含数字", has_price, f"answer={data.get('answer', '')[:80]}...")
    except Exception as e:
        check("价格查询可访问", False, str(e))

    # 2b 知识查询
    try:
        code, data = http_post("/api/chat/query", {"query": "有哪些饰面门板？"}, timeout=90)
        ok = check("知识查询返回 200", code == 200)
        if ok:
            check("知识查询包含 answer", "answer" in data and len(data["answer"]) > 0)
    except Exception as e:
        check("知识查询可访问", False, str(e))

    # 2c 空查询验证
    try:
        code, data = http_post("/api/chat/query", {"query": ""}, timeout=10)
        check("空查询返回 422", code == 422, f"实际返回 {code}")
    except Exception as e:
        check("空查询可访问", False, str(e))

    # 2d 图片查询占位
    try:
        code, data = http_post("/api/chat/query-with-image", {"query": "找相似门板"}, timeout=10)
        check("图片查询返回 501", code == 501, f"实际返回 {code}")
    except Exception as e:
        check("图片查询可访问", False, str(e))

    # ── 3. Products ────────────────────────────────────────────
    print("\n▶ 产品目录端点")

    try:
        code, data = http_get("/api/products?limit=5")
        ok = check("产品列表返回 200", code == 200)
        if ok:
            check("产品列表包含 total", isinstance(data.get("total"), int))
            check("产品列表包含 items", isinstance(data.get("items"), list))
            check("产品列表 items 非空", len(data.get("items", [])) > 0, "数据库中无产品数据")
            if data.get("items"):
                first = data["items"][0]
                check("产品 item 含 model_no", "model_no" in first)
                check("产品 item 含 family", "family" in first)
                check("产品 item 含 variants", "variants" in first)
    except Exception as e:
        check("产品列表可访问", False, str(e))

    try:
        code, data = http_get("/api/products?family=饰面门板")
        check("产品按 family 过滤返回 200", code == 200)
        if code == 200:
            items = data.get("items", [])
            all_match = all(p.get("family") == "饰面门板" for p in items)
            check("过滤结果 family 一致", all_match or len(items) == 0, f"返回 {len(items)} 条")
    except Exception as e:
        check("产品过滤可访问", False, str(e))

    try:
        code, data = http_get("/api/products/MX-A01")
        if code == 200:
            check("单产品 MX-A01 返回 200", True)
            check("单产品含 model_no", data.get("model_no") == "MX-A01")
            check("单产品含 variants", "variants" in data)
        else:
            check("单产品 MX-A01 存在", False, f"返回 {code}")
    except Exception as e:
        check("单产品 MX-A01 可访问", False, str(e))

    try:
        code, data = http_get("/api/products/NOT-EXIST")
        check("不存在产品返回 404", code == 404, f"实际返回 {code}")
    except Exception as e:
        check("不存在产品可访问", False, str(e))

    # ── 4. Documents ───────────────────────────────────────────
    print("\n▶ 文档上传端点")

    try:
        code, data = http_post_file(
            "/api/documents/upload",
            {"file": ("test.txt", b"not a pdf", "text/plain")},
        )
        check("非 PDF 上传返回 400", code == 400, f"实际返回 {code}")
    except Exception as e:
        check("非 PDF 上传可访问", False, str(e))

    # ── 5. Summary ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)
    print(f"验证结果: {passed}/{total} 通过, {failed}/{total} 失败")
    if failed == 0:
        print("\033[92m🎉 全部验证通过！系统运行正常。\033[0m")
        return 0
    else:
        print("\033[91m❌ 存在失败项，请检查上方详情。\033[0m")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
        return 1


if __name__ == "__main__":
    # 启动服务（如果未运行）
    import urllib.error

    print("检查服务状态...")
    try:
        http_get("/api/health", timeout=3)
        print("服务已在运行，直接开始验证。\n")
    except Exception:
        print("启动 FastAPI 服务...")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
            cwd="/Users/zizixiuixu/Code/kimi_code/multimodal-rag-catalog/backend",
        )
        time.sleep(4)
        # 二次确认
        try:
            http_get("/api/health", timeout=5)
            print("服务启动成功，开始验证。\n")
        except Exception as e:
            print(f"服务启动失败: {e}")
            proc.kill()
            sys.exit(1)
    else:
        proc = None

    try:
        exit_code = verify()
    finally:
        if proc is not None:
            print("\n停止临时服务...")
            proc.terminate()
            proc.wait(timeout=5)

    sys.exit(exit_code)
