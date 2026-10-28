<script setup lang="ts">
import { ref } from 'vue'
import QueryView from './views/QueryView.vue'
import SchemaView from './views/SchemaView.vue'
import ExperimentsView from './views/ExperimentsView.vue'
import BadcaseView from './views/BadcaseView.vue'

type Tab = 'query' | 'schema' | 'experiments' | 'badcases'
const active = ref<Tab>('query')
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
        <div class="mode"><i></i> 本地演示模式</div>
      </header>
      <QueryView v-if="active === 'query'" />
      <SchemaView v-else-if="active === 'schema'" />
      <ExperimentsView v-else-if="active === 'experiments'" />
      <BadcaseView v-else />
    </main>
  </div>
</template>

