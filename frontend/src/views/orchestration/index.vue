<template>
  <section class="page" data-module="orchestration">
    <header class="page-head">
      <div>
        <h2>试编排视图</h2>
        <p class="page-desc">
          采集计划启动前联合校验合规规则与代理节点，按风险分组给出可启动、需调整或已拒绝结论，
          并展示并发名额占用与预计日请求量。同一轮试编排的剩余名额来自同一次计算。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="reload">重新试编排</button>
        <button class="btn primary" type="button" @click="refresh">按最新规则/节点重算</button>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>按目标站点排列</span>
        <input v-model="siteFilter" placeholder="输入站点域名，审批角色可按来源查看" />
      </label>
      <button class="btn" type="submit">应用站点筛选</button>
      <button class="btn ghost" type="button" @click="clearSite">显示全部站点</button>
    </form>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">在线代理节点 / 全部节点</span>
        <strong class="stat-value">{{ proxyInfo.online_nodes ?? '—' }} / {{ proxyInfo.total_nodes ?? '—' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">代理总容量 / 已预留名额</span>
        <strong class="stat-value">{{ proxyInfo.capacity ?? '—' }} / {{ proxyInfo.used ?? 0 }}</strong>
      </article>
      <article v-for="group in riskGroups" :key="group.key" class="stat-card">
        <span class="stat-label">{{ group.label }}</span>
        <strong class="stat-value" :class="group.cls">{{ groups[group.key]?.length ?? 0 }}</strong>
      </article>
    </div>

    <h3 class="board-section-title">站点名额快照（同一次计算）</h3>
    <table class="data-table site-table">
      <thead>
        <tr>
          <th>目标站点</th><th>生效合规规则</th><th>站点并发总额</th>
          <th>已占用名额</th><th>剩余名额</th><th>计划数</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="site in siteSummaries" :key="site.site">
          <td>{{ site.site }}</td>
          <td>{{ site.compliance_rule_id ?? '无生效规则' }}</td>
          <td>{{ site.site_capacity }}</td>
          <td>{{ site.used_concurrency }}</td>
          <td>
            <strong :class="site.remaining_concurrency === 0 ? 'risk-reject' : 'risk-ready'">
              {{ site.remaining_concurrency }}
            </strong>
          </td>
          <td>{{ site.plan_count }}</td>
        </tr>
        <tr v-if="!siteSummaries.length">
          <td colspan="6" class="empty-state">当前筛选条件下没有站点数据</td>
        </tr>
      </tbody>
    </table>

    <div class="kanban">
      <div v-for="group in riskGroups" :key="group.key" class="kanban-column" :class="group.cls">
        <header class="kanban-head">
          <strong>{{ group.label }}</strong>
          <span class="kanban-count">{{ groups[group.key]?.length ?? 0 }}</span>
        </header>
        <div v-if="!groups[group.key]?.length" class="kanban-empty">暂无计划</div>
        <article v-for="item in groups[group.key]" :key="String(item.plan_id)" class="plan-card">
          <header class="plan-card-head">
            <div>
              <strong>{{ item['计划编号'] }}</strong>
              <span class="plan-site">{{ item['目标站点'] }}</span>
            </div>
            <span class="badge" :class="group.cls">{{ group.label }}</span>
          </header>
          <dl class="plan-meta">
            <div><dt>采集频率</dt><dd>{{ item['采集频率'] }}</dd></div>
            <div><dt>数据范围</dt><dd>{{ item['数据范围'] }}</dd></div>
            <div><dt>资源配额</dt><dd>{{ item['资源配额'] }}（优先级 {{ item['优先级'] }}）</dd></div>
            <div class="metric-row">
              <div><dt>占用并发名额</dt><dd class="metric">{{ item.requested_concurrency }}</dd></div>
              <div><dt>预计日请求量</dt><dd class="metric">{{ item.estimated_daily_requests }}</dd></div>
            </div>
            <div><dt>站点剩余 / 代理剩余</dt>
              <dd>{{ item.site_remaining }}（总额 {{ item.site_capacity }}） /
                {{ item.proxy_remaining }}（适配容量 {{ item.proxy_capacity }}）</dd>
            </div>
            <div v-if="item.reservation_held">
              <dt>预留状态</dt>
              <dd><span class="badge risk-wait">{{ item.hold_status }}</span></dd>
            </div>
          </dl>
          <ul v-if="item.compliance_limits.length" class="note-list compliance-note">
            <li v-for="(note, idx) in item.compliance_limits" :key="'c' + idx">合规限制：{{ note }}</li>
          </ul>
          <ul v-if="item.reasons.length" class="note-list reject-note">
            <li v-for="(note, idx) in item.reasons" :key="'r' + idx">{{ note }}</li>
          </ul>
          <ul v-if="item.proxy_gaps.length" class="note-list proxy-note">
            <li v-for="(note, idx) in item.proxy_gaps" :key="'p' + idx">代理缺口：{{ note }}</li>
          </ul>
          <ul v-if="item.conflict_sources.length" class="note-list adjust-note">
            <li v-for="(note, idx) in item.conflict_sources" :key="'f' + idx">冲突来源：{{ note }}</li>
          </ul>
          <footer class="plan-actions">
            <button
              class="btn primary"
              type="button"
              :disabled="item.decision !== '可启动' || item.reservation_held"
              @click="reserve(item.plan_id)"
            >
              {{ item.reservation_held ? '已预留名额' : '提交启动申请' }}
            </button>
            <button
              v-if="item.reservation_held"
              class="btn ghost"
              type="button"
              @click="release(item.plan_id)"
            >
              撤回预留
            </button>
          </footer>
        </article>
      </div>
    </div>

    <h3 class="board-section-title">待调整顺序看板（按优先级与计划编号排序）</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>顺序</th><th>计划编号</th><th>目标站点</th><th>优先级</th>
          <th>申请并发</th><th>站点剩余</th><th>冲突来源 / 代理缺口</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, index) in adjustQueue" :key="String(item.plan_id)">
          <td>{{ index + 1 }}</td>
          <td>{{ item['计划编号'] }}</td>
          <td>{{ item['目标站点'] }}</td>
          <td>{{ item['优先级'] }}</td>
          <td>{{ item.requested_concurrency }}</td>
          <td>{{ item.site_remaining }}</td>
          <td class="adjust-cell">
            <span v-for="(note, idx) in [...item.conflict_sources, ...item.proxy_gaps]" :key="idx">
              {{ note }}<br v-if="idx < item.conflict_sources.length + item.proxy_gaps.length - 1" />
            </span>
          </td>
        </tr>
        <tr v-if="!adjustQueue.length">
          <td colspan="7" class="empty-state">当前没有需要调整顺序的采集计划</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>试编排生成时间：{{ generatedAt || '—' }}</span>
      <span v-if="message" :class="messageError ? 'error-text' : 'ok-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Decision = '可启动' | '需调整' | '已拒绝'

type BoardItem = {
  plan_id: number
  计划编号: string
  目标站点: string
  采集频率: string
  数据范围: string
  资源配额: string
  优先级: string
  requested_concurrency: number
  estimated_daily_requests: number
  decision: Decision
  reasons: string[]
  compliance_rule_id: string | null
  compliance_limits: string[]
  proxy_gaps: string[]
  conflict_sources: string[]
  site_capacity: number
  site_remaining: number
  proxy_capacity: number
  proxy_remaining: number
  reservation_held: boolean
  hold_status: string | null
}

type BoardPayload = {
  generated_at: string
  proxy: {
    online_nodes: number
    total_nodes: number
    capacity: number
    capacity_by_site: Record<string, number>
    used: number
  }
  groups: Record<Decision, BoardItem[]>
  site_summaries: {
    site: string
    compliance_rule_id: string | null
    site_capacity: number
    used_concurrency: number
    remaining_concurrency: number
    plan_count: number
  }[]
  items: BoardItem[]
}

const riskGroups = [
  { key: '可启动' as Decision, label: '可启动', cls: 'risk-ready' },
  { key: '需调整' as Decision, label: '需调整', cls: 'risk-adjust' },
  { key: '已拒绝' as Decision, label: '已拒绝', cls: 'risk-reject' },
]

const board = ref<BoardPayload | null>(null)
const siteFilter = ref('')
const message = ref('')
const messageError = ref(false)

const groups = computed(() => board.value?.groups ?? ({} as Record<Decision, BoardItem[]>))
const siteSummaries = computed(() => board.value?.site_summaries ?? [])
const proxyInfo = computed(() => board.value?.proxy ?? ({} as BoardPayload['proxy']))
const generatedAt = computed(() => board.value?.generated_at ?? '')
const adjustQueue = computed(() =>
  [...(board.value?.groups['需调整'] ?? [])].sort((a, b) =>
    String(a['优先级']).localeCompare(String(b['优先级'])) ||
    a['计划编号'].localeCompare(b['计划编号']),
  ),
)

function clearSite() {
  siteFilter.value = ''
  void reload()
}

async function reload() {
  message.value = ''
  try {
    const query = siteFilter.value ? `?site=${encodeURIComponent(siteFilter.value)}` : ''
    const response = await request(`/api/orchestration/board${query}`)
    if (!response.ok) {
      throw new Error('试编排视图读取失败')
    }
    board.value = await response.json()
  } catch (error) {
    messageError.value = true
    message.value = error instanceof Error ? error.message : '试编排视图读取失败'
  }
}

async function reserve(planId: number) {
  messageError.value = false
  try {
    const response = await request(`/api/orchestration/plans/${planId}/reserve`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
    const payload = await response.json()
    message.value = payload.message ?? '启动申请已提交'
    messageError.value = !payload.ok
    await reload()
  } catch (error) {
    messageError.value = true
    message.value = error instanceof Error ? error.message : '启动申请提交失败'
  }
}

async function release(planId: number) {
  messageError.value = false
  try {
    const response = await request(`/api/orchestration/plans/${planId}/release`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
    const payload = await response.json()
    message.value = payload.message ?? '预留已撤回'
    messageError.value = !payload.ok
    await reload()
  } catch (error) {
    messageError.value = true
    message.value = error instanceof Error ? error.message : '撤回预留失败'
  }
}

async function refresh() {
  messageError.value = false
  try {
    const response = await request('/api/orchestration/refresh', {
      method: 'POST',
      body: JSON.stringify({}),
    })
    const payload = await response.json()
    message.value = payload.message ?? '已按最新规则与节点重算'
    await reload()
  } catch (error) {
    messageError.value = true
    message.value = error instanceof Error ? error.message : '重算失败'
  }
}

onMounted(reload)
</script>
