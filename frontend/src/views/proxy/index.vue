<template>
  <section class="page" data-module="proxy">
    <header class="page-head">
      <div>
        <h2>代理池管理管理</h2>
        <p class="page-desc">维护代理池的节点配置、响应指标与切换策略，为采集网络资源管理提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记代理节点</button>
        <button class="btn" type="button" @click="exportRows">导出代理池管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无代理池管理数据，可先登记代理节点</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条代理池管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="worklist">
      <h3 class="worklist-title">
        试编排代理待处理清单
        <span class="worklist-badge">{{ worklist.total }} 个节点未在线</span>
      </h3>
      <p class="page-desc">节点掉线后立即退出试编排名额计算，受影响采集计划同步失去启动资格并在此留痕。</p>
      <table class="data-table">
        <thead>
          <tr><th>节点编号</th><th>代理地址</th><th>节点状态</th><th>适配站点</th><th>节点容量</th><th>受影响采集计划</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in worklist.items" :key="String(item.node_id)">
            <td>{{ item['节点编号'] }}</td>
            <td>{{ item['代理地址'] }}</td>
            <td>{{ item['节点状态'] }}</td>
            <td>{{ item['适配站点'] }}</td>
            <td>{{ item['节点容量'] }}</td>
            <td>{{ item.affected_plans.join('、') || '—' }}</td>
          </tr>
          <tr v-if="!worklist.items.length">
            <td colspan="6" class="empty-state">暂无代理待处理项，全部节点在线服务</td>
          </tr>
        </tbody>
      </table>
      <h4 class="worklist-title">站点代理容量缺口</h4>
      <table class="data-table">
        <thead>
          <tr><th>目标站点</th><th>计划需求并发</th><th>在线代理容量</th><th>缺口</th></tr>
        </thead>
        <tbody>
          <tr v-for="gap in worklist.capacity_gaps" :key="gap.site">
            <td>{{ gap.site }}</td>
            <td>{{ gap.demand }}</td>
            <td>{{ gap.online_capacity }}</td>
            <td :class="gap.gap > 0 ? 'risk-reject' : ''">{{ gap.gap }}</td>
          </tr>
          <tr v-if="!worklist.capacity_gaps.length">
            <td colspan="4" class="empty-state">各站点代理容量均满足在排计划需求</td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/proxy'
const columns = ["节点编号", "代理地址", "代理类型", "地理位置", "响应延迟", "可用率", "切换策略", "节点容量", "适配站点", "节点状态"]
const actions = ["提交校验", "启用节点", "停用节点"]
const statuses = ["草稿", "待校验", "已启用", "已停用"]
const stats = [{"label": "代理节点总数", "value": 0}, {"label": "待校验节点", "value": 0}, {"label": "已启用节点", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
type ProxyWorkItem = {
  node_id: number
  节点编号: string
  代理地址: string
  节点状态: string
  节点容量: number
  适配站点: string
  issue: string
  affected_plans: string[]
}

type CapacityGap = { site: string; demand: number; online_capacity: number; gap: number }

const worklist = ref<{
  total: number
  items: ProxyWorkItem[]
  capacity_gaps: CapacityGap[]
}>({ total: 0, items: [], capacity_gaps: [] })

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '代理节点登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('代理池管理动作未生效，请稍后重试')
    }
    await reload()
    await loadWorklist()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '代理池管理操作失败'
  }
}

async function loadWorklist() {
  try {
    const response = await request('/api/orchestration/worklist/proxy')
    if (response.ok) {
      worklist.value = await response.json()
    }
  } catch {
    worklist.value = { total: 0, items: [], capacity_gaps: [] }
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('代理节点列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '代理池管理列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadWorklist()
})
</script>
