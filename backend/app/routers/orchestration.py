"""试编排接口：启动前联合裁决、名额预留、待处理清单与重算入口。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.orchestration import orchestration
from app.schemas import ActionResult, EntryPayload

router = APIRouter(prefix="/api/orchestration", tags=["试编排"])


@router.get("/board")
def board(site: str | None = Query(default=None, description="按目标站点过滤")) -> dict:
    """试编排视图：按可启动/需调整/已拒绝分组，并列明名额占用、合规限制与代理缺口。"""
    return orchestration.board(site=site)


@router.post("/plans/{plan_id}/reserve", response_model=ActionResult)
def reserve(plan_id: int, payload: EntryPayload | None = None) -> ActionResult:
    """提交启动申请：试编排通过则预留并发名额；条件未变化的重复提交只预留一次。"""
    result = orchestration.reserve(plan_id)
    return ActionResult(
        ok=bool(result["ok"]),
        message=result["message"],
        entry=result["entry"],
    )


@router.post("/plans/{plan_id}/release", response_model=ActionResult)
def release(plan_id: int) -> ActionResult:
    """撤回预留并归还并发名额。"""
    result = orchestration.release(plan_id)
    return ActionResult(
        ok=bool(result["ok"]),
        message=result["message"],
        entry=result["entry"],
    )


@router.post("/refresh", response_model=ActionResult)
def refresh() -> ActionResult:
    """合规规则撤回或代理节点掉线后触发全量重算，失格计划立即失去启动资格。"""
    result = orchestration.refresh()
    return ActionResult(
        ok=True,
        message=f"试编排已重算，{result['revoked_count']} 份计划失去启动资格",
        entry=result,
    )


@router.get("/worklist/compliance")
def compliance_worklist() -> dict:
    """合规模块待处理清单：未生效/被撤回规则及其影响的采集计划。"""
    return orchestration.compliance_worklist()


@router.get("/worklist/proxy")
def proxy_worklist() -> dict:
    """代理模块待处理清单：掉线/待校验节点与代理容量缺口。"""
    return orchestration.proxy_worklist()
