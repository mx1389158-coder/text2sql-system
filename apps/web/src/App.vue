<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, apiKeyAuth } from './api/client'
import QueryView from './views/QueryView.vue'
import SchemaView from './views/SchemaView.vue'
import ExperimentsView from './views/ExperimentsView.vue'
import BadcaseView from './views/BadcaseView.vue'

type Tab = 'query' | 'schema' | 'experiments' | 'badcases'
const active = ref<Tab>('query')
const runtimeMode = ref('连接中…')
const runtimeHealthy = ref(false)
const apiKey = ref(apiKeyAuth.get())
const authStatus = ref(apiKey.value ? '密钥已保存，尚未验证' : '未配置 API Key')
const pageMeta = computed(() => ({
  query: { eyebrow: 'DATA COPILOT', title: '智能问数', description: '用自然语言探索经营与售后数据' },
  schema: { eyebrow: 'SEMANTIC CATALOG', title: 'Schema 目录', description: '查看数据模型、字段定义与关联路径' },
  experiments: { eyebrow: 'EVALUATION LAB', title: '实验与评测', description: '对比模型能力、系统策略与运行成本' },
  badcases: { eyebrow: 'QUALITY LOOP', title: 'Badcase 分析', description: '沉淀人工反馈并治理训练候选数据' },
}[active.value]))

async function verifyAndSaveApiKey() {
  apiKeyAuth.set(apiKey.value)
  if (!apiKey.value.trim()) {
    authStatus.value = '已清除 API Key'
    return
  }
  try {
    await api.catalog()
    authStatus.value = 'API Key 已验证'
  } catch {
    authStatus.value = 'API Key 验证失败'
  }
}

onMounted(async () => {
  try {
    const info = await api.system()
    runtimeMode.value = info.mode === 'demo'
      ? '本地演示模式'
      : `${info.model} · ${info.database_engine}`
    runtimeHealthy.value = true
  } catch {
    runtimeMode.value = 'API 未连接'
  }
})
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark"><i></i><i></i><i></i></span>
        <div><strong>星云问数</strong><small>NEBULA DATA</small></div>
      </div>
      <p class="nav-label">工作空间</p>
      <nav>
        <button :class="{ active: active === 'query' }" @click="active = 'query'">
          <span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M8 10h8M8 14h5M5 19l2.2-3.2A7 7 0 1 1 19 12a7 7 0 0 1-7 7H5Z"/></svg></span>
          <span><b>智能问数</b><small>自然语言查询</small></span>
        </button>
        <button :class="{ active: active === 'schema' }" @click="active = 'schema'">
          <span class="nav-icon"><svg viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/></svg></span>
          <span><b>Schema 目录</b><small>语义与关联</small></span>
        </button>
        <button :class="{ active: active === 'experiments' }" @click="active = 'experiments'">
          <span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M9 3h6M10 3v5l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3M8 14h8"/></svg></span>
          <span><b>实验与评测</b><small>模型与策略</small></span>
        </button>
        <button :class="{ active: active === 'badcases' }" @click="active = 'badcases'">
          <span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M12 9v4M12 17h.01M10.3 4.6 3.8 16a2 2 0 0 0 1.7 3h13a2 2 0 0 0 1.7-3L13.7 4.6a2 2 0 0 0-3.4 0Z"/></svg></span>
          <span><b>Badcase 分析</b><small>反馈与治理</small></span>
        </button>
      </nav>
      <div class="system-card">
        <span class="shield-icon"><svg viewBox="0 0 24 24"><path d="M12 3 5 6v5c0 4.6 2.8 8.2 7 10 4.2-1.8 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-4"/></svg></span>
        <div><b>安全执行已启用</b><small>AST · 只读事务 · 资源预算</small></div>
      </div>
    </aside>
    <main class="workspace">
      <header class="topbar">
        <div class="page-heading">
          <span class="eyebrow">{{ pageMeta.eyebrow }}</span>
          <div><h1>{{ pageMeta.title }}</h1><p>{{ pageMeta.description }}</p></div>
        </div>
        <div class="header-actions">
          <form class="api-key-control" @submit.prevent="verifyAndSaveApiKey">
            <label><span>API KEY</span><input v-model="apiKey" type="password" autocomplete="current-password" placeholder="输入访问密钥" aria-label="API Key" /></label>
            <button type="submit">验证密钥</button>
            <small>{{ authStatus }}</small>
          </form>
          <div class="mode"><i :class="{ healthy: runtimeHealthy }"></i><span><small>运行环境</small>{{ runtimeMode }}</span></div>
        </div>
      </header>
      <div class="page-content">
        <QueryView v-if="active === 'query'" />
        <SchemaView v-else-if="active === 'schema'" />
        <ExperimentsView v-else-if="active === 'experiments'" />
        <BadcaseView v-else />
      </div>
    </main>
  </div>
</template>

