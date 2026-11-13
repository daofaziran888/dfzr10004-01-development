"""试编排回归测试。

运行：backend/.venv/bin/python -m pytest tests/test_orchestration.py -v
（无 pytest 时也可直接 .venv/bin/python tests/test_orchestration.py）
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.orchestration import (
    DECISION_ADJUST,
    DECISION_READY,
    DECISION_REJECT,
    HOLD_WAITING,
    orchestration,
)
from app.store import store


class OrchestrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        store.reset()
        orchestration.reset()
        self.client = TestClient(app)

    def board(self, site: str | None = None) -> dict:
        response = self.client.get("/api/orchestration/board", params={"site": site} if site else {})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def plan_id(self, code: str) -> int:
        for row in store.rows("taskplan"):
            if row.get("计划编号") == code:
                return int(row["id"])
        raise AssertionError(f"种子数据缺少 {code}")

    def compliance_id(self, code: str) -> int:
        for row in store.rows("compliance"):
            if row.get("规则编号") == code:
                return int(row["id"])
        raise AssertionError(f"种子数据缺少 {code}")

    def reserve(self, code: str):
        return self.client.post(f"/api/orchestration/plans/{self.plan_id(code)}/reserve", json={})

    def test_initial_board_groups_plans_by_risk(self) -> None:
        payload = self.board()
        groups = payload["groups"]
        self.assertEqual([i["计划编号"] for i in groups[DECISION_READY]], ["TASK-0001", "TASK-0002"])
        self.assertEqual([i["计划编号"] for i in groups[DECISION_ADJUST]], ["TASK-0004"])
        self.assertEqual(
            [i["计划编号"] for i in groups[DECISION_REJECT]], ["TASK-0003", "TASK-0005"]
        )
        # 结论必须带名额占用与预计日请求量
        ready = next(i for i in groups[DECISION_READY] if i["计划编号"] == "TASK-0002")
        self.assertEqual(ready["requested_concurrency"], 3)
        self.assertEqual(ready["estimated_daily_requests"], 48)
        # 无生效规则直接拒绝
        rejected_5 = next(i for i in groups[DECISION_REJECT] if i["计划编号"] == "TASK-0005")
        self.assertTrue(any("合规规则" in reason for reason in rejected_5["reasons"]))
        # 频率/日请求量违规拒绝
        rejected_3 = next(i for i in groups[DECISION_REJECT] if i["计划编号"] == "TASK-0003")
        self.assertTrue(any("访问间隔" in reason for reason in rejected_3["reasons"]))
        self.assertTrue(any("日请求" in reason for reason in rejected_3["reasons"]))

    def test_same_site_plans_share_one_calculation(self) -> None:
        """TASK-0002 与同站点的 TASK-0004 看到的剩余名额必须来自同一次计算。"""
        payload = self.board()
        task2 = next(i for i in payload["items"] if i["计划编号"] == "TASK-0002")
        task4 = next(i for i in payload["items"] if i["计划编号"] == "TASK-0004")
        self.assertEqual(task2["目标站点"], task4["目标站点"])
        self.assertEqual(task2["site_capacity"], task4["site_capacity"])
        self.assertEqual(task2["proxy_capacity"], task4["proxy_capacity"])
        # 同一次试编排内站点容量快照一致
        self.assertEqual(payload["generated_at"], payload["generated_at"])
        summary = next(s for s in payload["site_summaries"] if s["site"] == task2["目标站点"])
        self.assertEqual(summary["site_capacity"], task2["site_capacity"])

    def test_idempotent_reserve_holds_slot_once(self) -> None:
        first = self.reserve("TASK-0002")
        self.assertTrue(first.json()["ok"], first.json())
        second = self.reserve("TASK-0002")
        body = second.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["entry"]["hold_status"] == HOLD_WAITING)
        # 代理池已占用名额只计算一次
        payload = self.board()
        self.assertEqual(payload["proxy"]["used"], 3)

    def test_contention_only_first_plan_enters_waiting(self) -> None:
        """两份计划争抢最后一个名额：首个进入待启动，另一个说明冲突来源。"""
        first = self.reserve("TASK-0002")
        self.assertTrue(first.json()["ok"])
        second = self.reserve("TASK-0004")
        body = second.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["entry"]["hold_status"], "需调整")
        self.assertTrue(body["entry"]["conflict_sources"], "落选计划必须说明冲突来源")
        conflict_text = "；".join(body["entry"]["conflict_sources"])
        self.assertIn("www.example-b.com", conflict_text)
        # 站点剩余名额联动：TASK-0002 实际占 3 后只剩 1，TASK-0004 申请 2
        payload = self.board()
        task4 = next(i for i in payload["items"] if i["计划编号"] == "TASK-0004")
        self.assertEqual(task4["site_remaining"], 1)
        self.assertEqual(task4["decision"], DECISION_ADJUST)
        self.assertEqual(task4["projected_site_remaining"], 1)

    def test_compliance_withdrawal_revokes_eligibility_immediately(self) -> None:
        self.reserve("TASK-0001")
        hold = orchestration._holds[self.plan_id("TASK-0001")]
        self.assertEqual(hold["hold_status"], HOLD_WAITING)

        # 撤回合规规则
        response = self.client.post(
            f"/api/compliance/{self.compliance_id('COMP-0001')}/actions",
            json={"values": {"action": "废弃规则"}},
        )
        self.assertTrue(response.json()["ok"], response.json())
        self.assertIn("失去启动资格", response.json()["message"])

        # 预留立即失效、名额释放
        hold = orchestration._holds[self.plan_id("TASK-0001")]
        self.assertEqual(hold["hold_status"], "已拒绝")
        board = self.board()
        task1 = next(i for i in board["items"] if i["计划编号"] == "TASK-0001")
        self.assertEqual(task1["decision"], DECISION_REJECT)
        self.assertEqual(board["proxy"]["used"], 0)

        # 合规待处理清单能看到撤回规则与受影响计划（不只在计划页变按钮）
        worklist = self.client.get("/api/orchestration/worklist/compliance").json()
        self.assertGreaterEqual(worklist["total"], 1)
        entry = next(i for i in worklist["items"] if i["规则编号"] == "COMP-0001")
        self.assertIn("TASK-0001", entry["affected_plans"])

    def test_proxy_offline_revokes_and_proxy_worklist(self) -> None:
        self.reserve("TASK-0002")  # 占用站点 b 的 3 个名额（站点 b 在线容量 4）
        # 停用站点 b 上容量 2 的节点，站点 b 代理容量降到 2，TASK-0002 立即失格
        proxy_row = next(row for row in store.rows("proxy") if row["节点编号"] == "PROX-0002")
        response = self.client.post(
            f"/api/proxy/{proxy_row['id']}/actions",
            json={"values": {"action": "停用节点"}},
        )
        self.assertTrue(response.json()["ok"], response.json())
        self.assertEqual(proxy_row["节点状态"], "离线")
        self.assertIn("失去启动资格", response.json()["message"])

        worklist = self.client.get("/api/orchestration/worklist/proxy").json()
        offline = next(i for i in worklist["items"] if i["节点编号"] == "PROX-0002")
        self.assertEqual(offline["节点状态"], "离线")
        self.assertEqual(worklist["capacity_by_site"]["www.example-b.com"], 2)
        # 站点 b 需求 3+2=5，在线容量仅 2，缺口进入待处理清单
        gap = next(g for g in worklist["capacity_gaps"] if g["site"] == "www.example-b.com")
        self.assertEqual(gap["gap"], 3)

        board = self.board()
        task2 = next(i for i in board["items"] if i["计划编号"] == "TASK-0002")
        self.assertIn(task2["decision"], (DECISION_ADJUST, DECISION_REJECT))
        self.assertEqual(board["proxy"]["used"], 0)

        # 节点恢复在线后，资格可重新计算回来
        self.client.post(
            f"/api/proxy/{proxy_row['id']}/actions",
            json={"values": {"action": "启用节点"}},
        )
        recovered = self.reserve("TASK-0002").json()
        self.assertTrue(recovered["ok"], recovered)

    def test_task0003_keeps_plan_data_after_rule_revision(self) -> None:
        """TASK-0003 在合规规则修订后保留原计划数据，只重新计算启动资格。"""
        before = dict(store.find("taskplan", self.plan_id("TASK-0003")))
        initial_board = self.board()
        initial = next(i for i in initial_board["items"] if i["计划编号"] == "TASK-0003")
        self.assertEqual(initial["decision"], DECISION_REJECT)
        self.assertTrue(initial["reasons"], "修订前应因合规规则被拒绝")

        rule = store.find("compliance", self.compliance_id("COMP-0003"))
        # 修订规则：放宽访问间隔与日请求上限，使原计划的频率与配额重新合规
        rule["访问间隔"] = "5秒"
        rule["日请求上限"] = "10000"
        rule["并发上限"] = "4"
        refresh = self.client.post("/api/orchestration/refresh").json()
        self.assertTrue(refresh["ok"])

        after = store.find("taskplan", self.plan_id("TASK-0003"))
        for field in ("计划编号", "目标站点", "采集频率", "数据范围", "资源配额", "优先级"):
            self.assertEqual(before[field], after[field], f"{field} 含义与数据必须保留")

        board = self.board()
        task3 = next(i for i in board["items"] if i["计划编号"] == "TASK-0003")
        # 合规拒绝原因已消失：即便因全局代理争抢仍是需调整，也不再是合规拒绝
        self.assertNotEqual(task3["decision"], DECISION_REJECT)
        self.assertEqual(task3["reasons"], [])
        self.assertTrue(task3["compliance_limits"])

        # 无其他计划争抢时（清空预留并单独试算），规则修订后必须可启动
        orchestration.reset()
        single = self.client.post(
            f"/api/orchestration/plans/{self.plan_id('TASK-0003')}/reserve", json={}
        ).json()
        self.assertTrue(single["ok"], single)
        self.assertEqual(single["entry"]["decision"], DECISION_READY)

    def test_first_submitter_wins_regardless_of_priority(self) -> None:
        """低优先级计划先提交时同样先得名额：裁决按提交顺序串行，不被优先级抢占。"""
        # TASK-0004（P2）先提交，占站点 b 的 2 个名额
        first = self.reserve("TASK-0004")
        self.assertTrue(first.json()["ok"], first.json())
        # TASK-0002（P1）后提交，只剩 2 个名额而它申请 3，必须落选
        second = self.reserve("TASK-0002")
        self.assertFalse(second.json()["ok"])
        self.assertTrue(second.json()["entry"]["conflict_sources"])

    def test_concurrent_contention_only_one_waiting_hold(self) -> None:
        """并发争抢同站点名额：加锁串行裁决后，只允许一个计划进入待启动。"""
        import threading

        outcomes: dict[str, dict] = {}

        def submit(code: str) -> None:
            outcomes[code] = self.reserve(code).json()

        thread_2 = threading.Thread(target=submit, args=("TASK-0002",))
        thread_4 = threading.Thread(target=submit, args=("TASK-0004",))
        thread_2.start()
        thread_4.start()
        thread_2.join()
        thread_4.join()

        waiting = [code for code, body in outcomes.items() if body["entry"]["hold_status"] == HOLD_WAITING]
        adjusted = [code for code, body in outcomes.items() if body["entry"]["hold_status"] == "需调整"]
        self.assertEqual(len(waiting), 1, f"只应有一个待启动，实际：{waiting}")
        self.assertEqual(len(adjusted), 1)
        # 总占用名额不得超过站点容量
        board = self.board()
        self.assertLessEqual(board["proxy"]["used"], 4)

    def test_start_action_gated_by_orchestration(self) -> None:
        # 未通过试编排的计划不能直接启动
        response = self.client.post(
            f"/api/taskplan/{self.plan_id('TASK-0005')}/actions",
            json={"values": {"action": "启动计划"}},
        )
        self.assertFalse(response.json()["ok"])
        # 通过试编排的计划启动后名额继续占用
        ok = self.client.post(
            f"/api/taskplan/{self.plan_id('TASK-0002')}/actions",
            json={"values": {"action": "启动计划"}},
        )
        self.assertTrue(ok.json()["ok"], ok.json())
        self.assertEqual(self.board()["proxy"]["used"], 3)
        # 暂停后释放名额
        paused = self.client.post(
            f"/api/taskplan/{self.plan_id('TASK-0002')}/actions",
            json={"values": {"action": "暂停计划"}},
        )
        self.assertTrue(paused.json()["ok"])
        self.assertEqual(self.board()["proxy"]["used"], 0)

    def test_site_filter_for_approval_role(self) -> None:
        payload = self.board(site="www.example-b.com")
        self.assertEqual(
            sorted(i["计划编号"] for i in payload["items"]),
            ["TASK-0002", "TASK-0004"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
