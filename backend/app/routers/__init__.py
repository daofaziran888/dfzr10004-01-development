"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import taskplan as router_taskplan
from app.routers import orchestration as router_orchestration
from app.routers import verify as router_verify
from app.routers import pipeline as router_pipeline
from app.routers import transform as router_transform
from app.routers import dedup as router_dedup
from app.routers import retry as router_retry
from app.routers import audit as router_audit
from app.routers import compliance as router_compliance
from app.routers import proxy as router_proxy
from app.routers import storage as router_storage
from app.routers import alert as router_alert
from app.routers import report as router_report
from app.routers import throttle as router_throttle
from app.routers import tag as router_tag
from app.routers import version as router_version
from app.routers import sandbox as router_sandbox

ROUTERS = [router_taskplan, router_orchestration, router_verify, router_pipeline, router_transform, router_dedup, router_retry, router_audit, router_compliance, router_proxy, router_storage, router_alert, router_report, router_throttle, router_tag, router_version, router_sandbox]
