#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦当劳点餐助手 CLI（Skill 用）。

只做一件事：把用户需求交给本机的规则引擎，把结果原样转述成可读文本。
不计算价格、不估算热量、不写入任何东西——所有数字都来自 /api/*。

用法：
    python scripts/plan.py health
    python scripts/plan.py stores --city 郑州 --keyword 七里河
    python scripts/plan.py menu --store 3560134 --mode lean
    python scripts/plan.py plan --store 3560134 --mode lean --text "1000千卡以内，预算40"
    python scripts/plan.py plan --store 3560134 --text "..." --cart "520689:1" --skip "A,B;A,C"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_HOST = os.environ.get("MCD_APP_HOST", "127.0.0.1")
DEFAULT_PORT = os.environ.get("MCD_APP_PORT", "8000")


def _out(text: str = "") -> None:
    print(text)


def _base(args) -> str:
    return f"http://{args.host}:{args.port}"


# 本机请求必须绕开系统代理：环境里存在 HTTP_PROXY 时，urllib 会把
# 127.0.0.1 也发给代理，得到 502 upstream connect failed。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _request(url: str, payload: dict | None = None, timeout: int = 180) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body).get("message") or body
        except json.JSONDecodeError:
            msg = body
        raise SystemExit(f"[{exc.code}] {msg}") from None
    except urllib.error.URLError as exc:
        raise SystemExit(
            "连接失败：{url}\n"
            "点餐服务没有运行。先启动：\n"
            "  cd D:/code/麦当劳点餐\n"
            "  MCD_TOKEN=<token> python app/server.py\n"
            "（token 只从环境变量读，不要写进文件）\n"
            "原始错误：{err}".format(url=url, err=exc.reason)
        ) from None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise SystemExit(f"返回不是 JSON：{body[:200]}") from None


# ---------- 子命令 ----------


def cmd_health(args) -> int:
    d = _request(f"{_base(args)}/api/health", timeout=10)
    _out(f"服务：{_base(args)}")
    _out(f"凭据：{'已配置' if d.get('hasToken') else '未配置（需要带 MCD_TOKEN 重启服务）'}")
    _out(f"判定配置：{d.get('taxonomyVersion')}")
    _out(f"详情缓存：{d.get('factsCached')} 个商品")
    # 凭据缺失不算执行失败：服务本身是通的，由调用方决定下一步
    return 0


def cmd_stores(args) -> int:
    qs = {}
    if args.city:
        qs["city"] = args.city
    if args.keyword:
        qs["keyword"] = args.keyword
    url = f"{_base(args)}/api/stores"
    if qs:
        url += "?" + urllib.parse.urlencode(qs)
    d = _request(url, timeout=60)
    stores = d.get("stores") or []
    if not stores:
        _out("没有查到门店。换一个城市或地标再试。")
        return 0
    for i, s in enumerate(stores, 1):
        dist = s.get("distance")
        dist_text = f" · {dist}m" if dist else ""
        status = "营业中" if s.get("businessStatus") else "休息中"
        _out(f"{i}. {s.get('storeName')}　{s.get('storeCode')}{dist_text} · {status}")
        if s.get("address"):
            _out(f"   {s['address']}")
    _out("\n把要用的 storeCode 交给用户确认，不要默认选第一家。")
    return 0


def cmd_menu(args) -> int:
    url = f"{_base(args)}/api/menu?" + urllib.parse.urlencode({"storeCode": args.store, "mode": args.mode})
    d = _request(url, timeout=90)
    items = {i["code"]: i for i in d.get("items") or []}
    _out(f"门店 {args.store} · {'减脂' if args.mode == 'lean' else '普通'}模式 · 可选 {len(items)} 项")
    for cat in d.get("categories") or []:
        name = (cat.get("name") or "").replace("\n", "")
        _out(f"\n[{name}] {len(cat.get('codes') or [])} 项")
        if not args.verbose:
            continue
        for code in cat.get("codes") or []:
            it = items.get(code)
            if not it:
                continue
            kcal = (it.get("kcal") or {}).get("unit")
            src = (it.get("kcal") or {}).get("source")
            m = it.get("macros")
            macro = (
                f" · 蛋白{m['protein']:g}/脂肪{m['fat']:g}/碳水{m['carbohydrate']:g}"
                if m
                else " · 营养素暂无官方数据"
            )
            sauce = "（已去酱）" if it.get("autoSauceRemoved") else ""
            _out(
                f"  {code} {it.get('name')}{sauce}　¥{it.get('price')}　约{kcal}千卡"
                f"（{'官方' if src == 'official' else '估算'}）{macro}"
            )
    return 0


def _parse_cart(text: str) -> list[dict]:
    cart = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        code, _, qty = part.partition(":")
        cart.append({"code": code.strip(), "quantity": int(qty or 1)})
    return cart


def _parse_skip(text: str) -> list[list[str]]:
    groups = []
    for group in (text or "").split(";"):
        codes = [c.strip() for c in group.split(",") if c.strip()]
        if codes:
            groups.append(codes)
    return groups


def _fmt_plan(idx: int, plan: dict) -> list[str]:
    lines = []
    kcal = plan.get("kcalText") or f"约 {plan.get('kcal')} 千卡"
    head = f"{idx}. ¥{plan.get('yuan'):.2f} · {kcal}"
    if plan.get("macrosText"):
        head += f" · {plan['macrosText']}"
    lines.append(head)
    parts = []
    for it in plan.get("items") or []:
        name = it.get("name") or ""
        qty = it.get("quantity") or 1
        tail = "（已去酱）" if it.get("sauceOff") else ""
        parts.append(f"{name} ×{qty}{tail}")
    lines.append("   " + " + ".join(parts))
    coupon = plan.get("coupon")
    lines.append(f"   券：{coupon}" if coupon else "   券：无可用券，按基础价")
    estimated = [it.get("name") for it in plan.get("items") or [] if it.get("kcalSource") in ("heuristic", "unknown")]
    if estimated:
        lines.append(f"   注：{'、'.join(estimated)} 热量为兜底估算，非官方值")
    return lines


def cmd_plan(args) -> int:
    payload = {
        "storeCode": args.store,
        "mode": args.mode,
        "text": args.text or "",
        "cart": _parse_cart(args.cart) if args.cart else [],
        "skip": _parse_skip(args.skip) if args.skip else [],
        "needTableware": True,
    }
    d = _request(f"{_base(args)}/api/plan", payload=payload, timeout=args.timeout)
    if args.json:
        _out(json.dumps(d, ensure_ascii=False, indent=1))
        return 0

    _out(f"门店 {args.store} · {'减脂' if args.mode == 'lean' else '普通'}模式")
    recognized = [r.get("label") for r in d.get("recognized") or []]
    _out("识别到：" + ("；".join(recognized) if recognized else "未指定条件，按默认结构搭配"))

    plans = d.get("plans") or []
    if plans:
        _out("")
        for i, plan in enumerate(plans, 1):
            for line in _fmt_plan(i, plan):
                _out(line)
    else:
        blocker = d.get("blocker") or {}
        _out("\n没有符合全部条件的方案。")
        if blocker.get("message"):
            _out(f"原因：{blocker['message']}")
        for s in blocker.get("suggestions") or []:
            _out(f"  · {s}")

    notes = []
    if d.get("note"):
        notes.append(d["note"])
    for u in d.get("unresolved") or []:
        notes.append(u)
    if notes:
        _out("\n提示：")
        for n in notes:
            _out(f"- {n}")
    if d.get("cartItems"):
        _out(
            f"\n购物车已有 {len(d['cartItems'])} 件（这些不计入上面的热量与金额，只是不会重复推荐）"
        )
    # 无方案是正常结果（has blocker），不是执行失败
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(description="麦当劳点餐助手 CLI（只读，不下单）")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("health", help="检查服务与凭据")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("stores", help="按城市/地标查门店")
    p.add_argument("--city", default="", help="城市名，如 郑州")
    p.add_argument("--keyword", default="", help="地标或路名，如 七里河")
    p.set_defaults(func=cmd_stores)

    p = sub.add_parser("menu", help="查看门店可选商品")
    p.add_argument("--store", required=True)
    p.add_argument("--mode", choices=("lean", "normal"), default="lean")
    p.add_argument("--verbose", action="store_true", help="列出商品明细")
    p.set_defaults(func=cmd_menu)

    p = sub.add_parser("plan", help="生成配餐方案")
    p.add_argument("--store", required=True)
    p.add_argument("--mode", choices=("lean", "normal"), default="lean")
    p.add_argument("--text", default="", help="用户原话，原样传入")
    p.add_argument("--cart", default="", help='购物车已有商品，如 "520689:1,1450:2"')
    p.add_argument("--skip", default="", help='上一套方案的 signature，如 "A,B;A,C"')
    p.add_argument("--json", action="store_true", help="输出原始 JSON")
    p.add_argument("--timeout", type=int, default=180, help="试算超时秒数")
    p.set_defaults(func=cmd_plan)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
