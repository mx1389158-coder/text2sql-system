<script setup lang="ts">
import { onMounted, ref } from 'vue'
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
        <span class="brand-mark">N</span>
        <div><strong>星云智家</strong><small>INTELLIGENCE LAB</small></div>
      </div>
      <nav>
        <button :class="{ active: active === 'query' }" @click="active = 'query'">
          <span>⌁</span> 智能问数
        </button>
        <button :class="{ active: active === 'schema' }" @click="active = 'schema'">
          <span>◎</span> Schema 目录
        </button>
        <button :class="{ active: active === 'experiments' }" @click="active = 'experiments'">
          <span>⌗</span> 实验与评测
        </button>
        <button :class="{ active: active === 'badcases' }" @click="active = 'badcases'">
          <span>!</span> Badcase 分析
        </button>
      </nav>
      <div class="system-card">
        <span class="status-dot"></span>
        <div><b>安全执行已启用</b><small>AST · 只读事务 · LIMIT</small></div>
      </div>
    </aside>
    <main>
      <header>
        <div><span class="eyebrow">NEBULA / DATA COPILOT</span><h1>智能问数工作台</h1></div>
        <div class="header-actions">
          <form class="api-key-control" @submit.prevent="verifyAndSaveApiKey">
            <input
              v-model="apiKey"
              type="password"
              autocomplete="current-password"
              placeholder="输入 API Key"
              aria-label="API Key"
            />
            <button type="submit">验证</button>
            <small>{{ authStatus }}</small>
          </form>
          <div class="mode"><i :class="{ healthy: runtimeHealthy }"></i> {{ runtimeMode }}</div>
        </div>
      </header>
      <QueryView v-if="active === 'query'" />
      <SchemaView v-else-if="active === 'schema'" />
      <ExperimentsView v-else-if="active === 'experiments'" />
      <BadcaseView v-else />
    </main>
  </div>
</template>

