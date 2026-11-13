import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
const Taskplan = () => import('@/views/taskplan/index.vue')
const Orchestration = () => import('@/views/orchestration/index.vue')
const Verify = () => import('@/views/verify/index.vue')
const Pipeline = () => import('@/views/pipeline/index.vue')
const Transform = () => import('@/views/transform/index.vue')
const Dedup = () => import('@/views/dedup/index.vue')
const Retry = () => import('@/views/retry/index.vue')
const Audit = () => import('@/views/audit/index.vue')
const Compliance = () => import('@/views/compliance/index.vue')
const Proxy = () => import('@/views/proxy/index.vue')
const Storage = () => import('@/views/storage/index.vue')
const Alert = () => import('@/views/alert/index.vue')
const Report = () => import('@/views/report/index.vue')
const Throttle = () => import('@/views/throttle/index.vue')
const Tag = () => import('@/views/tag/index.vue')
const Version = () => import('@/views/version/index.vue')
const Sandbox = () => import('@/views/sandbox/index.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    { path: '/taskplan', name: 'taskplan', component: Taskplan },
    { path: '/orchestration', name: 'orchestration', component: Orchestration },
    { path: '/verify', name: 'verify', component: Verify },
    { path: '/pipeline', name: 'pipeline', component: Pipeline },
    { path: '/transform', name: 'transform', component: Transform },
    { path: '/dedup', name: 'dedup', component: Dedup },
    { path: '/retry', name: 'retry', component: Retry },
    { path: '/audit', name: 'audit', component: Audit },
    { path: '/compliance', name: 'compliance', component: Compliance },
    { path: '/proxy', name: 'proxy', component: Proxy },
    { path: '/storage', name: 'storage', component: Storage },
    { path: '/alert', name: 'alert', component: Alert },
    { path: '/report', name: 'report', component: Report },
    { path: '/throttle', name: 'throttle', component: Throttle },
    { path: '/tag', name: 'tag', component: Tag },
    { path: '/version', name: 'version', component: Version },
    { path: '/sandbox', name: 'sandbox', component: Sandbox },
  ],
})

export default router
