<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">智能采集质量管控平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向数据采集团队的质量管控与效率优化平台。覆盖采集任务编排、抓取结果校验、采集链路监控、数据格式转换、去重比对、异常重试、采集审计与合规管理的完整采集质控链路。</span>
        <span class="head-user">当前值班：{{ store.operator }} · {{ store.shiftLabel }}</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "采集任务编排", path: "/taskplan" }, { label: "试编排视图", path: "/orchestration" }, { label: "采集结果校验", path: "/verify" }, { label: "采集链路监控", path: "/pipeline" }, { label: "采集格式转换", path: "/transform" }, { label: "采集去重比对", path: "/dedup" }, { label: "异常重试管理", path: "/retry" }, { label: "采集审计日志", path: "/audit" }, { label: "采集合规配置", path: "/compliance" }, { label: "代理池管理", path: "/proxy" }, { label: "采集存储策略", path: "/storage" }, { label: "采集告警中心", path: "/alert" }, { label: "采集统计报表", path: "/report" }, { label: "采集频率控制", path: "/throttle" }, { label: "采集数据标注", path: "/tag" }, { label: "采集配置版本", path: "/version" }, { label: "采集沙箱测试", path: "/sandbox" }]
</script>
