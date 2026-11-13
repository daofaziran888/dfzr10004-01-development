<template>
  <section class="page" data-module="compliance">
    <header class="page-head">
      <div>
        <h2>采集合规配置管理</h2>
        <p class="page-desc">维护采集合规的协议配置、访问限制与请求规范，为采集行为合规管理提供可审计的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记合规规则</button>
        <button class="btn" type="button" @click="exportRows">导出采集合规配置清单</button>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无采集合规配置数据，可先登记合规规则</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条采集合规配置记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="worklist">
      <h3 class="worklist-title">
        试编排合规待处理清单
        <span class="worklist-badge">{{ worklist.total }} 项</span>
      </h3>
      <p class="page-desc">规则撤回或未生效时，相关采集计划会立即失去启动资格并在此留痕，而不只是计划页按钮变化。</p>
      <table class="data-table">
        <thead>
          <tr><th>规则编号</th><th>站点域名</th><th>合规状态</th><th>待处理原因</th><th>受影响采集计划</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in worklist.items" :key="String(item.rule_id)">
            <td>{{ item['规则编号'] }}</td>
            <td>{{ item['站点域名'] }}</td>
            <td>{{ item['合规状态'] }}</td>
            <td>{{ item.issue }}</td>
            <td>{{ item.affected_plans.join('、') || '—' }}</td>
          </tr>
          <tr v-if="!worklist.items.length">
            <td colspan="5" class="empty-state">暂无合规待处理项，生效规则均满足在排计划要求</td>
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

const ENDPOINT = '/api/compliance'
const columns = ["规则编号", "站点域名", "协议标识", "访问间隔", "并发上限", "日请求上限", "请求头模板", "合规状态", "最近审查"]
const actions = ["提交审批", "发布规则", "废弃规则"]
const statuses = ["草稿", "待审批", "已生效", "已废弃"]
const stats = [{"label": "合规规则总数", "value": 0}, {"label": "已生效规则", "value": 0}, {"label": "待审批规则", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
type ComplianceWorkItem = {
  rule_id: number
  规则编号: string
  站点域名: string
  合规状态: string
  issue: string
  affected_plans: string[]
}

const worklist = ref<{ total: number; items: ComplianceWorkItem[] }>({ total: 0, items: [] })

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '合规规则登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('采集合规配置动作未生效，请稍后重试')
    }
    await reload()
    await loadWorklist()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '采集合规配置操作失败'
  }
}

async function loadWorklist() {
  try {
    const response = await request('/api/orchestration/worklist/compliance')
    if (response.ok) {
      worklist.value = await response.json()
    }
  } catch {
    worklist.value = { total: 0, items: [] }
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('合规规则列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '采集合规配置列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadWorklist()
})
</script>
