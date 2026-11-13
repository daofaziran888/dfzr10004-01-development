"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None



class TaskplanEntry(BaseModel):
    """采集计划明细结构。"""

    field_0: str | None = None  # 计划编号
    field_1: str | None = None  # 目标站点
    field_2: str | None = None  # 采集频率
    field_3: str | None = None  # 数据范围
    field_4: str | None = None  # 优先级
    field_5: str | None = None  # 资源配额
    field_6: str | None = None  # 预计用时
    field_7: str | None = None  # 计划状态

class VerifyEntry(BaseModel):
    """校验规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 校验对象
    field_2: str | None = None  # 校验类型
    field_3: str | None = None  # 校验表达式
    field_4: str | None = None  # 阈值配置
    field_5: str | None = None  # 采样比例
    field_6: str | None = None  # 阻断级别
    field_7: str | None = None  # 最近校验

class PipelineEntry(BaseModel):
    """链路节点明细结构。"""

    field_0: str | None = None  # 节点编号
    field_1: str | None = None  # 节点名称
    field_2: str | None = None  # 上游节点
    field_3: str | None = None  # 下游节点
    field_4: str | None = None  # 处理耗时
    field_5: str | None = None  # 吞吐速率
    field_6: str | None = None  # 错误数量
    field_7: str | None = None  # 节点状态

class TransformEntry(BaseModel):
    """转换模板明细结构。"""

    field_0: str | None = None  # 模板编号
    field_1: str | None = None  # 输入格式
    field_2: str | None = None  # 输出格式
    field_3: str | None = None  # 映射规则
    field_4: str | None = None  # 编码设置
    field_5: str | None = None  # 分隔符
    field_6: str | None = None  # 换行策略
    field_7: str | None = None  # 是否启用

class DedupEntry(BaseModel):
    """去重策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 业务键列
    field_2: str | None = None  # 排序字段
    field_3: str | None = None  # 保留策略
    field_4: str | None = None  # 时间窗口
    field_5: str | None = None  # 相似阈值
    field_6: str | None = None  # 比对字段
    field_7: str | None = None  # 是否启用

class RetryEntry(BaseModel):
    """重试规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 异常类型
    field_2: str | None = None  # 重试上限
    field_3: str | None = None  # 退避策略
    field_4: str | None = None  # 冷却时间
    field_5: str | None = None  # 告警阈值
    field_6: str | None = None  # 降级方案
    field_7: str | None = None  # 是否启用

class AuditEntry(BaseModel):
    """审计记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 操作类型
    field_2: str | None = None  # 采集计划
    field_3: str | None = None  # 执行人
    field_4: str | None = None  # 执行时间
    field_5: str | None = None  # 结果摘要
    field_6: str | None = None  # 变更内容
    field_7: str | None = None  # 复核状态

class ComplianceEntry(BaseModel):
    """合规规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 站点域名
    field_2: str | None = None  # 协议标识
    field_3: str | None = None  # 访问间隔
    field_4: str | None = None  # 并发上限
    field_5: str | None = None  # 请求头模板
    field_6: str | None = None  # 合规状态
    field_7: str | None = None  # 最近审查
    field_8: str | None = None  # 日请求上限（试编排裁决依据）

class ProxyEntry(BaseModel):
    """代理节点明细结构。"""

    field_0: str | None = None  # 节点编号
    field_1: str | None = None  # 代理地址
    field_2: str | None = None  # 代理类型
    field_3: str | None = None  # 地理位置
    field_4: str | None = None  # 响应延迟
    field_5: str | None = None  # 可用率
    field_6: str | None = None  # 切换策略
    field_7: str | None = None  # 节点状态
    field_8: str | None = None  # 节点容量（试编排名额计算依据）
    field_9: str | None = None  # 适配站点（站点亲和，决定可服务的目标站点）

class StorageEntry(BaseModel):
    """存储配置明细结构。"""

    field_0: str | None = None  # 配置编号
    field_1: str | None = None  # 存储路径
    field_2: str | None = None  # 文件格式
    field_3: str | None = None  # 分片大小
    field_4: str | None = None  # 压缩算法
    field_5: str | None = None  # 保留天数
    field_6: str | None = None  # 归档策略
    field_7: str | None = None  # 是否启用

class AlertEntry(BaseModel):
    """告警规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 监控指标
    field_2: str | None = None  # 告警级别
    field_3: str | None = None  # 触发条件
    field_4: str | None = None  # 通知渠道
    field_5: str | None = None  # 静默时间
    field_6: str | None = None  # 升级策略
    field_7: str | None = None  # 是否启用

class ReportEntry(BaseModel):
    """统计报表明细结构。"""

    field_0: str | None = None  # 报表编号
    field_1: str | None = None  # 统计维度
    field_2: str | None = None  # 统计周期
    field_3: str | None = None  # 指标集合
    field_4: str | None = None  # 数据来源
    field_5: str | None = None  # 生成时间
    field_6: str | None = None  # 报表格式
    field_7: str | None = None  # 分发方式

class ThrottleEntry(BaseModel):
    """频率策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 目标站点
    field_2: str | None = None  # 请求间隔
    field_3: str | None = None  # 日请求上限
    field_4: str | None = None  # 并发数量
    field_5: str | None = None  # 排队策略
    field_6: str | None = None  # 优先级权重
    field_7: str | None = None  # 是否启用

class TagEntry(BaseModel):
    """标注记录明细结构。"""

    field_0: str | None = None  # 标注编号
    field_1: str | None = None  # 数据记录
    field_2: str | None = None  # 标注类型
    field_3: str | None = None  # 标注标签
    field_4: str | None = None  # 标注批次
    field_5: str | None = None  # 复核状态
    field_6: str | None = None  # 标注人
    field_7: str | None = None  # 标注时间

class VersionEntry(BaseModel):
    """配置版本明细结构。"""

    field_0: str | None = None  # 版本编号
    field_1: str | None = None  # 配置名称
    field_2: str | None = None  # 版本号
    field_3: str | None = None  # 变更说明
    field_4: str | None = None  # 变更内容
    field_5: str | None = None  # 回滚标识
    field_6: str | None = None  # 发布状态
    field_7: str | None = None  # 发布时间

class SandboxEntry(BaseModel):
    """沙箱实例明细结构。"""

    field_0: str | None = None  # 实例编号
    field_1: str | None = None  # 测试脚本
    field_2: str | None = None  # 目标站点
    field_3: str | None = None  # 测试参数
    field_4: str | None = None  # 预期结果
    field_5: str | None = None  # 实际结果
    field_6: str | None = None  # 测试耗时
    field_7: str | None = None  # 实例状态
