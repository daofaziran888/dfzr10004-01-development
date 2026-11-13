"""试编排引擎：采集计划启动前的合规、代理与名额联合裁决。

设计要点
--------
1. 一次试编排内，站点合规快照、代理池总容量、各站点剩余名额只计算一次，
   同站点的多份计划共享同一次计算结果（回归要求：TASK-0002 与同站点计划一致）。
2. 预留按「计划指纹」幂等：目标站点、采集频率、数据范围、资源配额均未变化时，
   重复提交只保留同一份名额，不会重复占用。
3. 全部裁决在同一把锁内按「优先级 + 计划编号」串行执行，两个计划争抢最后一个
   名额时只有首个进入待启动，落选计划会记录明确的冲突来源。
4. 合规规则被撤回或代理节点掉线后调用 :meth:`OrchestrationEngine.refresh`，
   相关待启动计划立即失去启动资格并释放名额，同时沉淀到合规/代理模块的待处理清单。
5. 计划编号、目标站点、采集频率等既有字段的含义完全不动；规则修订只重算资格。
"""
from __future__ import annotations

import re
import threading
from datetime import datetime
from typing import Any

from app.store import store

TASKPLAN_MODULE = "taskplan"
COMPLIANCE_MODULE = "compliance"
PROXY_MODULE = "proxy"

# 试编排结论
DECISION_READY = "可启动"
DECISION_ADJUST = "需调整"
DECISION_REJECT = "已拒绝"
DECISION_ORDER = [DECISION_READY, DECISION_ADJUST, DECISION_REJECT]

# 预留/申请状态
HOLD_WAITING = "待启动"
HOLD_RUNNING = "运行占用"
HOLD_ADJUST = "需调整"
HOLD_REJECTED = "已拒绝"

# 计划指纹字段：这四个字段任一变化都视为新的试编排申请
FINGERPRINT_FIELDS = ["目标站点", "采集频率", "数据范围", "资源配额"]
ACTIVE_PLAN_STATUSES = {"草稿", "运行中", "已暂停"}

_SECONDS_PER_DAY = 86400


def _leading_int(value: Any, default: int = 0) -> int:
    """从「并发3」「2 个」这类混合文本里提取首个整数；提取不到时用默认值。"""
    if value is None:
        return default
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else default


def _interval_seconds(text: Any) -> int | None:
    """把「每10分钟一次」「30秒」之类的频率描述换算成秒；无法识别返回 None。"""
    if text is None:
        return None
    raw = str(text)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(秒|分钟|小时)", raw)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    factor = {"秒": 1, "分钟": 60, "小时": 3600}[unit]
    return max(int(number * factor), 1)


def _priority_rank(priority: Any, plan_code: str) -> tuple[int, int]:
    """排序键：P0<P1<P2，同级按计划编号数字升序，保证名额裁决可复现。"""
    match = re.search(r"(\d+)", str(priority or ""))
    level = int(match.group(1)) if match else 9
    code_match = re.search(r"(\d+)", str(plan_code or ""))
    code = int(code_match.group(1)) if code_match else 0
    return level, code


class OrchestrationEngine:
    """持有全部试编排预留记录，并对外提供试算、预留、释放与重算能力。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # plan_id -> 预留/申请记录
        self._holds: dict[int, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # 快照：一次试编排内只构建一次，保证同站点计划看到同一份剩余名额
    # ------------------------------------------------------------------
    def _build_snapshot(self) -> dict[str, Any]:
        compliance_rows = store.rows(COMPLIANCE_MODULE)
        proxy_rows = store.rows(PROXY_MODULE)

        # 每个站点取一条生效规则（同站点多条生效时取最近审查的一条）
        rules_by_site: dict[str, dict[str, Any]] = {}
        for row in compliance_rows:
            if row.get("status") != "已生效" or row.get("合规状态") not in (None, "已生效"):
                continue
            site = str(row.get("站点域名") or "").strip()
            if not site:
                continue
            current = rules_by_site.get(site)
            if current is None or str(row.get("最近审查") or "") > str(current.get("最近审查") or ""):
                rules_by_site[site] = row

        online_nodes = [
            row for row in proxy_rows
            if row.get("status") == "已启用" and str(row.get("节点状态") or "") == "在线"
        ]
        proxy_capacity = sum(max(_leading_int(row.get("节点容量"), 1), 1) for row in online_nodes)

        # 代理节点按「适配站点」做站点亲和：每个站点的代理容量只统计可服务该站点的在线节点
        proxy_capacity_by_site: dict[str, int] = {}
        for node in online_nodes:
            capacity = max(_leading_int(node.get("节点容量"), 1), 1)
            for site in self._node_sites(node):
                proxy_capacity_by_site[site] = proxy_capacity_by_site.get(site, 0) + capacity

        return {
            "rules_by_site": rules_by_site,
            "online_nodes": online_nodes,
            "proxy_capacity": proxy_capacity,
            "proxy_capacity_by_site": proxy_capacity_by_site,
            "proxy_total_nodes": len(proxy_rows),
            "proxy_online_nodes": len(online_nodes),
        }

    @staticmethod
    def _node_sites(node: dict[str, Any]) -> list[str]:
        raw = str(node.get("适配站点") or "")
        return [part.strip() for part in re.split(r"[,，;；]", raw) if part.strip()]

    def _site_caps(self, rule: dict[str, Any] | None, proxy_capacity: int) -> dict[str, int]:
        """站点可承载的并发名额：合规并发上限与该站点代理容量取较小者。"""
        compliance_cap = _leading_int(rule.get("并发上限"), 0) if rule else 0
        return {
            "compliance_cap": compliance_cap,
            "proxy_capacity": proxy_capacity,
            "site_capacity": min(compliance_cap, proxy_capacity) if compliance_cap else proxy_capacity,
        }

    # ------------------------------------------------------------------
    # 单计划静态评估：合规规则、访问间隔、日请求量、并发、代理缺口
    # ------------------------------------------------------------------
    def _evaluate_plan(
        self,
        plan: dict[str, Any],
        snapshot: dict[str, Any],
        actual_site_usage: dict[str, int],
        actual_proxy_used: list[int],
        projected_site_usage: dict[str, int],
        projected_proxy_used: list[int],
        held: bool,
    ) -> dict[str, Any]:
        site = str(plan.get("目标站点") or "").strip()
        rule = snapshot["rules_by_site"].get(site)
        site_proxy_capacity = snapshot["proxy_capacity_by_site"].get(site, 0)
        caps = self._site_caps(rule, site_proxy_capacity)
        site_capacity = caps["site_capacity"]

        requested = max(_leading_int(plan.get("资源配额"), 1), 1)
        interval_seconds = _interval_seconds(plan.get("采集频率"))
        estimated_daily = (
            min(_SECONDS_PER_DAY // interval_seconds, 100000)
            if interval_seconds
            else 0
        )

        reasons: list[str] = []
        compliance_limits: list[str] = []
        proxy_gaps: list[str] = []

        if rule is None:
            reasons.append(f"站点 {site} 没有已生效的合规规则，禁止启动采集")
        else:
            compliance_limits.append(
                f"规则 {rule.get('规则编号')}：访问间隔 {rule.get('访问间隔')}、"
                f"并发上限 {rule.get('并发上限')}、日请求上限 {rule.get('日请求上限')}"
            )
            rule_interval = _interval_seconds(rule.get("访问间隔"))
            if interval_seconds and rule_interval and interval_seconds < rule_interval:
                reasons.append(
                    f"采集频率 {plan.get('采集频率')} 短于合规访问间隔 {rule.get('访问间隔')}"
                )
            daily_cap = _leading_int(rule.get("日请求上限"), 0)
            if daily_cap and estimated_daily > daily_cap:
                reasons.append(
                    f"预计日请求量 {estimated_daily} 超过合规日请求上限 {daily_cap}"
                )
            compliance_cap = caps["compliance_cap"]
            if compliance_cap and requested > compliance_cap:
                reasons.append(
                    f"申请并发 {requested} 超过站点合规并发上限 {compliance_cap}"
                )

        if requested > site_proxy_capacity:
            proxy_gaps.append(
                f"申请并发 {requested} 大于站点 {site} 的在线代理容量 {site_proxy_capacity}"
            )
        if site_proxy_capacity == 0:
            proxy_gaps.append(f"代理池没有可服务站点 {site} 的在线节点")

        # 剩余名额分两层：已实际预留的余量（给排班员看），加上本轮试算模拟占用后的余量
        actual_remaining_site = max(site_capacity - actual_site_usage.get(site, 0), 0)
        actual_remaining_proxy = max(site_proxy_capacity - actual_proxy_used[0], 0)
        projected_remaining_site = max(site_capacity - projected_site_usage.get(site, 0), 0)
        projected_remaining_proxy = max(site_proxy_capacity - projected_proxy_used[0], 0)

        conflict_sources: list[str] = []
        if reasons:
            decision = DECISION_REJECT
        elif requested <= projected_remaining_site and requested <= projected_remaining_proxy:
            decision = DECISION_READY
        else:
            decision = DECISION_ADJUST
            if requested > projected_remaining_site:
                conflict_sources.append(
                    f"站点 {site} 剩余并发名额 {projected_remaining_site}（站点总额 {site_capacity}），"
                    f"本计划申请 {requested}"
                )
            if requested > projected_remaining_proxy:
                conflict_sources.append(
                    f"站点 {site} 代理剩余容量 {projected_remaining_proxy}"
                    f"（适配代理总容量 {site_proxy_capacity}），本计划申请 {requested}"
                )

        return {
            "plan_id": plan.get("id"),
            "计划编号": plan.get("计划编号"),
            "目标站点": site,
            "采集频率": plan.get("采集频率"),
            "数据范围": plan.get("数据范围"),
            "资源配额": plan.get("资源配额"),
            "优先级": plan.get("优先级"),
            "requested_concurrency": requested,
            "estimated_daily_requests": estimated_daily,
            "decision": decision,
            "reasons": reasons,
            "compliance_rule_id": rule.get("规则编号") if rule else None,
            "compliance_limits": compliance_limits,
            "proxy_gaps": proxy_gaps,
            "conflict_sources": conflict_sources,
            "site_capacity": site_capacity,
            "site_remaining": actual_remaining_site,
            "proxy_capacity": site_proxy_capacity,
            "proxy_remaining": actual_remaining_proxy,
            "projected_site_remaining": projected_remaining_site,
            "projected_proxy_remaining": projected_remaining_proxy,
            "reservation_held": held,
        }

    def _active_plans(self) -> list[dict[str, Any]]:
        plans = [
            row for row in store.rows(TASKPLAN_MODULE)
            if row.get("status") in ACTIVE_PLAN_STATUSES
        ]
        return sorted(plans, key=lambda row: _priority_rank(row.get("优先级"), row.get("计划编号")))

    def _occupying_holds(self) -> list[dict[str, Any]]:
        """当前实际占名额的预留：待启动与运行中的计划。"""
        return [
            hold for hold in self._holds.values()
            if hold.get("hold_status") in (HOLD_WAITING, HOLD_RUNNING)
        ]

    def _evaluate_all(self, snapshot: dict[str, Any], *, project_unheld: bool = True) -> list[dict[str, Any]]:
        """同一次计算内串行裁决全部计划。

        actual_* 只统计已经预留/运行的名额；projected_* 在此基础上叠加本轮试算中
        判定为可启动的计划，用于暴露同站点争抢。返回给排班员的剩余名额始终是
        actual_*，即同一次计算的真实余量。

        project_unheld=True（试编排看板）：把尚未提交的计划也纳入模拟占用，
        呈现「假如全部申请」的争抢全景。
        project_unheld=False（真实预留/重算）：只按已实际占有的名额裁决，
        没提交申请的计划不能挡住别人的启动申请。
        """
        occupying = {hold["plan_id"]: hold for hold in self._occupying_holds()}
        actual_site_usage: dict[str, int] = {}
        # 站点名额同时受合规上限与代理容量约束，因此站点与代理各按站点维度记账
        actual_proxy_used_by_site: dict[str, int] = {}
        for hold in occupying.values():
            site = hold.get("site")
            concurrency = int(hold.get("concurrency") or 0)
            actual_site_usage[site] = actual_site_usage.get(site, 0) + concurrency
            actual_proxy_used_by_site[site] = actual_proxy_used_by_site.get(site, 0) + concurrency
        projected_site_usage = dict(actual_site_usage)
        projected_proxy_used = dict(actual_proxy_used_by_site)

        results: list[dict[str, Any]] = []
        for plan in self._active_plans():
            hold = occupying.get(plan["id"])
            site = str(plan.get("目标站点") or "").strip()
            result = self._evaluate_plan(
                plan,
                snapshot,
                actual_site_usage,
                [actual_proxy_used_by_site.get(site, 0)],
                projected_site_usage,
                [projected_proxy_used.get(site, 0)],
                held=hold is not None,
            )
            result["hold_status"] = hold.get("hold_status") if hold else None
            # 只有看板模式，或本计划已实际占名额时，才驱动后续争抢判断
            if result["decision"] == DECISION_READY and (project_unheld or hold is not None):
                projected_site_usage[site] = (
                    projected_site_usage.get(site, 0) + result["requested_concurrency"]
                )
                projected_proxy_used[site] = (
                    projected_proxy_used.get(site, 0) + result["requested_concurrency"]
                )
                result["projected_site_remaining"] = max(
                    result["site_capacity"] - projected_site_usage[site], 0
                )
                result["projected_proxy_remaining"] = max(
                    result["proxy_capacity"] - projected_proxy_used[site], 0
                )
            results.append(result)
        return results

    def _fingerprint(self, plan: dict[str, Any]) -> str:
        return "|".join(str(plan.get(field) or "") for field in FINGERPRINT_FIELDS)

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def board(self, *, site: str | None = None) -> dict[str, Any]:
        """试编排视图：按风险分组返回全部计划的裁决结果与站点/代理余量。"""
        with self._lock:
            snapshot = self._build_snapshot()
            results = self._evaluate_all(snapshot)
            if site:
                results = [row for row in results if site in row["目标站点"]]

            groups = {label: [] for label in DECISION_ORDER}
            for row in results:
                groups[row["decision"]].append(row)

            site_summaries: dict[str, dict[str, Any]] = {}
            for row in results:
                name = row["目标站点"]
                summary = site_summaries.setdefault(name, {
                    "site": name,
                    "compliance_rule_id": row["compliance_rule_id"],
                    "site_capacity": row["site_capacity"],
                    "used_concurrency": 0,
                    "plan_count": 0,
                })
                summary["plan_count"] += 1
                if row["reservation_held"]:
                    summary["used_concurrency"] += row["requested_concurrency"]
            for summary in site_summaries.values():
                summary["remaining_concurrency"] = max(
                    summary["site_capacity"] - summary["used_concurrency"], 0
                )

            return {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "proxy": {
                    "online_nodes": snapshot["proxy_online_nodes"],
                    "total_nodes": snapshot["proxy_total_nodes"],
                    "capacity": snapshot["proxy_capacity"],
                    "capacity_by_site": snapshot["proxy_capacity_by_site"],
                    "used": sum(int(h.get("concurrency") or 0) for h in self._occupying_holds()),
                },
                "groups": groups,
                "site_summaries": sorted(site_summaries.values(), key=lambda item: item["site"]),
                "items": results,
            }

    def reserve(self, plan_id: int) -> dict[str, Any]:
        """提交启动申请：幂等预留名额，争抢时只有首个计划进入待启动。"""
        with self._lock:
            plan = store.find(TASKPLAN_MODULE, plan_id)
            if plan is None:
                return {"ok": False, "message": f"采集计划 {plan_id} 不存在或已归档", "entry": None}
            if plan.get("status") not in ACTIVE_PLAN_STATUSES:
                return {
                    "ok": False,
                    "message": f"采集计划 {plan.get('计划编号')} 当前状态 {plan.get('status')}，不接受启动申请",
                    "entry": None,
                }

            fingerprint = self._fingerprint(plan)
            existing = self._holds.get(plan_id)
            if (
                existing is not None
                and existing.get("fingerprint") == fingerprint
                and existing.get("hold_status") in (HOLD_WAITING, HOLD_RUNNING)
            ):
                # 试编排条件未变化：重复提交只预留一次名额
                return {
                    "ok": True,
                    "message": f"采集计划 {plan.get('计划编号')} 试编排条件未变化，沿用已有预留，不重复占用名额",
                    "entry": existing,
                    "idempotent": True,
                }

            snapshot = self._build_snapshot()
            # 真实预留只看已占名额：未提交申请的计划不能拦截本次启动
            results = self._evaluate_all(snapshot, project_unheld=False)
            result = next((row for row in results if row["plan_id"] == plan_id), None)
            if result is None:
                return {"ok": False, "message": "采集计划未进入试编排范围", "entry": None}

            hold = {
                "plan_id": plan_id,
                "计划编号": plan.get("计划编号"),
                "site": result["目标站点"],
                "fingerprint": fingerprint,
                "concurrency": result["requested_concurrency"],
                "estimated_daily_requests": result["estimated_daily_requests"],
                "decision": result["decision"],
                "reasons": list(result["reasons"]),
                "conflict_sources": list(result["conflict_sources"]),
                "compliance_rule_id": result["compliance_rule_id"],
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }

            if result["decision"] == DECISION_READY:
                hold["hold_status"] = HOLD_WAITING if plan.get("status") != "运行中" else HOLD_RUNNING
                self._holds[plan_id] = hold
                message = f"采集计划 {plan.get('计划编号')} 通过试编排，已预留 {hold['concurrency']} 个并发名额，进入待启动"
                ok = True
            else:
                # 落选也要留痕：排班员能在看板上看到冲突来源与拒绝原因
                hold["hold_status"] = (
                    HOLD_REJECTED if result["decision"] == DECISION_REJECT else HOLD_ADJUST
                )
                self._holds[plan_id] = hold
                detail = "；".join(result["reasons"] + result["conflict_sources"])
                message = f"采集计划 {plan.get('计划编号')} 试编排结论为{result['decision']}：{detail}"
                ok = False
            return {"ok": ok, "message": message, "entry": hold, "idempotent": False}

    def release(self, plan_id: int) -> dict[str, Any]:
        """释放预留：暂停/归档或排班员主动撤回时归还并发名额。"""
        with self._lock:
            hold = self._holds.pop(plan_id, None)
            if hold is None:
                return {"ok": False, "message": f"采集计划 {plan_id} 没有试编排预留记录", "entry": None}
            return {
                "ok": True,
                "message": f"采集计划 {hold.get('计划编号')} 的 {hold.get('concurrency')} 个并发名额已释放",
                "entry": hold,
            }

    def mark_running(self, plan_id: int) -> None:
        """计划正式启动后，预留记录转为运行占用，名额继续保留。"""
        with self._lock:
            hold = self._holds.get(plan_id)
            if hold is not None and hold.get("hold_status") == HOLD_WAITING:
                hold["hold_status"] = HOLD_RUNNING
                hold["updated_at"] = datetime.now().isoformat(timespec="seconds")

    def refresh(self) -> dict[str, Any]:
        """合规撤回或代理掉线后重算：失格计划立即释放名额并记录失效原因。"""
        with self._lock:
            snapshot = self._build_snapshot()
            # 重算的是真实启动资格：只承认已经预留/运行的名额占用
            results = {
                row["plan_id"]: row
                for row in self._evaluate_all(snapshot, project_unheld=False)
            }
            revoked: list[dict[str, Any]] = []
            for plan_id, hold in list(self._holds.items()):
                result = results.get(plan_id)
                if result is None:
                    continue
                if result["decision"] != DECISION_READY and hold.get("hold_status") == HOLD_WAITING:
                    hold["hold_status"] = (
                        HOLD_REJECTED if result["decision"] == DECISION_REJECT else HOLD_ADJUST
                    )
                    hold["decision"] = result["decision"]
                    hold["reasons"] = list(result["reasons"])
                    hold["conflict_sources"] = list(result["conflict_sources"])
                    hold["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    revoked.append({
                        "plan_id": plan_id,
                        "计划编号": hold.get("计划编号"),
                        "site": hold.get("site"),
                        "decision": result["decision"],
                        "reasons": hold["reasons"],
                        "conflict_sources": hold["conflict_sources"],
                    })
            return {
                "ok": True,
                "revoked_count": len(revoked),
                "revoked": revoked,
                "proxy_capacity": snapshot["proxy_capacity"],
            }

    # ------------------------------------------------------------------
    # 合规清单 / 代理清单各自的待处理清单（不只在计划页改按钮）
    # ------------------------------------------------------------------
    def compliance_worklist(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._build_snapshot()
            active_sites = {
                str(plan.get("目标站点") or "").strip()
                for plan in self._active_plans()
            }
            items: list[dict[str, Any]] = []
            for row in store.rows(COMPLIANCE_MODULE):
                site = str(row.get("站点域名") or "").strip()
                affected = self._plans_on_site(site)
                if row.get("status") != "已生效":
                    if site in active_sites or affected:
                        items.append({
                            "rule_id": row.get("id"),
                            "规则编号": row.get("规则编号"),
                            "站点域名": site,
                            "合规状态": row.get("合规状态") or row.get("status"),
                            "issue": "规则未生效，相关采集计划无法取得启动资格",
                            "affected_plans": [item["计划编号"] for item in affected],
                        })
                    continue
                # 已生效但约束与在排计划冲突的，也进入合规待处理清单
                for plan_info in affected:
                    result = self._evaluate_plan(
                        plan_info["_plan"], snapshot, {}, [0], {}, [0], held=False
                    )
                    hard_violations = [
                        reason for reason in result["reasons"]
                        if "合规" in reason or "访问间隔" in reason or "日请求" in reason
                    ]
                    if hard_violations:
                        items.append({
                            "rule_id": row.get("id"),
                            "规则编号": row.get("规则编号"),
                            "站点域名": site,
                            "合规状态": row.get("合规状态") or row.get("status"),
                            "issue": "；".join(hard_violations),
                            "affected_plans": [plan_info["计划编号"]],
                        })
            return {"module": "compliance", "total": len(items), "items": items}

    def proxy_worklist(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._build_snapshot()
            items: list[dict[str, Any]] = []
            for row in store.rows(PROXY_MODULE):
                if row.get("status") == "已启用" and str(row.get("节点状态") or "") == "在线":
                    continue
                node_sites = self._node_sites(row)
                affected = [
                    {"计划编号": plan.get("计划编号")}
                    for plan in self._active_plans()
                    if not node_sites or str(plan.get("目标站点") or "").strip() in node_sites
                ]
                items.append({
                    "node_id": row.get("id"),
                    "节点编号": row.get("节点编号"),
                    "代理地址": row.get("代理地址"),
                    "节点状态": row.get("节点状态") or row.get("status"),
                    "节点容量": _leading_int(row.get("节点容量"), 1),
                    "适配站点": "、".join(node_sites) if node_sites else "未配置",
                    "issue": "节点未在线，不参与试编排名额计算",
                    "affected_plans": [item["计划编号"] for item in affected],
                })

            # 按站点汇总需求与在线代理容量，缺口即代理资源不足的待处理项
            demand_by_site: dict[str, int] = {}
            for plan in self._active_plans():
                site = str(plan.get("目标站点") or "").strip()
                demand_by_site[site] = demand_by_site.get(site, 0) + max(
                    _leading_int(plan.get("资源配额"), 1), 1
                )
            site_gaps = [
                {
                    "site": site,
                    "demand": demand,
                    "online_capacity": snapshot["proxy_capacity_by_site"].get(site, 0),
                    "gap": max(demand - snapshot["proxy_capacity_by_site"].get(site, 0), 0),
                }
                for site, demand in sorted(demand_by_site.items())
                if demand > snapshot["proxy_capacity_by_site"].get(site, 0)
            ]
            return {
                "module": "proxy",
                "total": len(items),
                "items": items,
                "capacity": snapshot["proxy_capacity"],
                "capacity_by_site": snapshot["proxy_capacity_by_site"],
                "capacity_gaps": site_gaps,
            }

    def _plans_on_site(self, site: str) -> list[dict[str, Any]]:
        plans = []
        for plan in self._active_plans():
            if str(plan.get("目标站点") or "").strip() == site:
                plans.append({"计划编号": plan.get("计划编号"), "_plan": plan})
        return plans

    def reset(self) -> None:
        """清空全部预留记录：配合 store.reset 做回归测试。"""
        with self._lock:
            self._holds.clear()


# 全局单例：路由、合规/代理服务共享同一个试编排引擎
orchestration = OrchestrationEngine()
