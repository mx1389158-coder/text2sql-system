<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api/client'
import type { QueryRecord, Strategy } from '../types'

const examples = [
  '列出产品型号、名称和价格',
  '不同型号的平均满意度是多少？',
  '哪些设备在首次报修后 7 天内再次报修？',
  '近三个月各型号的退换货率是多少？',
]
const question = ref(examples[0])
const loading = ref(false)
const error = ref('')
const record = ref<QueryRecord | null>(null)
const strategy = ref<Strategy>('optimized')
const feedbackSent = ref(false)
const resultMode = ref<'table' | 'chart'>('table')
const sqlCopied = ref(false)
const chart = computed(() => {
  const result = record.value?.result
  if (!result || result.columns.length < 2) return []
  const numeric = result.columns.find(column => result.rows.some(row => typeof row[column] === 'number'))
  const label = result.columns.find(column => column !== numeric)
  if (!numeric || !label) return []
  const rows = result.rows.slice(0, 12).map(row => ({ label: String(row[label]), value: Number(row[numeric]) || 0 }))
  const max = Math.max(...rows.map(row => Math.abs(row.value)), 1)
  return rows.map(row => ({ ...row, width: Math.abs(row.value) / max * 100, metric: numeric }))
})

const statusLabel = computed(() => ({
  completed: '执行完成', clarification_required: '需要澄清', rejected: '安全拒绝', failed: '执行失败', running: '处理中',
}[record.value?.status || 'running']))

async function submit() {
  if (!question.value.trim() || loading.value) return
  loading.value = true; error.value = ''; feedbackSent.value = false; resultMode.value = 'table'
  try { record.value = await api.query(question.value, strategy.value) }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { loading.value = false }
}

async function clarify(answer: string) {
  if (!record.value) return
  loading.value = true
  try { record.value = await api.clarify(record.value.query_id, answer) }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { loading.value = false }
}

async function feedback(rating: 'correct' | 'incorrect') {
  if (!record.value) return
  await api.feedback(record.value.query_id, rating)
  feedbackSent.value = true
}

async function copySql() {
  if (!record.value?.sql) return
  await navigator.clipboard.writeText(record.value.sql)
  sqlCopied.value = true
  window.setTimeout(() => { sqlCopied.value = false }, 1600)
}
</script>

<template>
  <section class="query-layout">
    <div class="composer panel">
      <div class="composer-top">
        <div><span class="composer-kicker">ASK YOUR DATA</span><h2>今天想了解什么？</h2><p>描述业务问题，系统会自动选择 Schema、生成并安全执行 SQL。</p></div>
        <label class="strategy-select"><span>生成策略</span><select v-model="strategy"><option value="optimized">优化策略</option><option value="baseline">基线策略</option></select></label>
      </div>
      <div class="question-input"><span class="spark">✦</span><textarea v-model="question" rows="3" placeholder="例如：近三个月各型号的退换货率是多少？" @keydown.ctrl.enter="submit" /><small>Ctrl + Enter</small></div>
      <div class="composer-footer">
        <div class="examples">
          <span>试试这样问</span><button v-for="item in examples" :key="item" @click="question = item">{{ item }}</button>
        </div>
        <button class="primary query-submit" :disabled="loading" @click="submit"><span v-if="loading" class="spinner"></span>{{ loading ? '正在分析' : '开始问数' }}<b v-if="!loading">→</b></button>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <template v-if="record">
      <div v-if="record.clarification" class="clarify panel">
        <span class="step-number">?</span>
        <div><h3>{{ record.clarification.question }}</h3><p>请选择一个口径，系统不会在不明确时擅自猜测。</p>
          <div class="choice-row"><button v-for="option in record.clarification.options" :key="option" @click="clarify(option)">{{ option }}</button></div>
        </div>
      </div>

      <div class="summary-grid">
        <article class="metric"><small>STATUS</small><strong>{{ statusLabel }}</strong><span :class="['badge', record.status]">{{ record.intent }}</span></article>
        <article class="metric"><small>TRACE</small><strong>{{ record.trace.length }} 个阶段</strong><span>{{ record.cached ? '缓存命中' : '实时处理' }}</span></article>
        <article class="metric"><small>SCHEMA</small><strong>{{ record.schema_evidence?.selected_tables.length || 0 }} 张候选表</strong><span>{{ record.schema_evidence?.estimated_tokens || 0 }} tokens</span></article>
        <article class="metric"><small>EXECUTION</small><strong>{{ record.result?.elapsed_ms?.toFixed(1) || '—' }} ms</strong><span>修正 {{ record.repair_rounds }} 轮</span></article>
      </div>

      <div v-if="record.error_message" class="error panel"><b>{{ record.error_code }}</b> · {{ record.error_message }}</div>

      <div v-if="record.schema_evidence || record.sql" class="result-workbench">
        <div v-if="record.schema_evidence" class="panel section-card evidence-card">
          <div class="section-heading"><div><span class="eyebrow">EVIDENCE</span><h2>Schema 证据</h2></div><span>{{ record.schema_evidence.estimated_tokens }} tokens</span></div>
          <p class="section-note">本次查询检索到的业务表与外键补全路径</p>
          <div class="chips"><span v-for="table in record.schema_evidence.selected_tables" :key="table" :class="{ path: record.schema_evidence.join_path_tables.includes(table) }">{{ table }}</span></div>
          <details><summary>查看精简 M-Schema</summary><pre>{{ record.schema_evidence.mschema }}</pre></details>
        </div>

        <div v-if="record.sql" class="panel section-card sql-card">
          <div class="section-heading"><div><span class="eyebrow">READ-ONLY SQL</span><h2>最终查询</h2></div><button class="ghost-button" @click="copySql">{{ sqlCopied ? '已复制' : '复制 SQL' }}</button></div>
          <div class="security-pass"><span>✓</span> AST 安全检查通过 · 只读事务</div>
          <pre class="sql"><code>{{ record.sql }}</code></pre>
          <div v-if="record.assumptions.length" class="assumptions"><b>假设与说明</b><span v-for="item in record.assumptions" :key="item">{{ item }}</span></div>
        </div>
      </div>

      <div v-if="record.result" class="panel section-card">
        <div class="section-heading"><div><span class="eyebrow">RESULT</span><h2>查询结果</h2></div><div class="view-tabs"><button :class="{ active: resultMode === 'table' }" @click="resultMode = 'table'">表格</button><button :disabled="!chart.length" :class="{ active: resultMode === 'chart' }" @click="resultMode = 'chart'">图表</button><span>{{ record.result.rows.length }} 行</span></div></div>
        <p class="explanation">{{ record.explanation }}</p>
        <div v-if="resultMode === 'table'" class="table-wrap"><table><thead><tr><th v-for="column in record.result.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in record.result.rows" :key="index"><td v-for="column in record.result.columns" :key="column">{{ row[column] ?? 'NULL' }}</td></tr></tbody></table></div>
        <div v-else-if="chart.length" class="result-chart"><h3>{{ chart[0].metric }}</h3><div v-for="bar in chart" :key="bar.label"><span>{{ bar.label }}</span><i><b :style="{ width: `${bar.width}%` }"></b></i><strong>{{ bar.value }}</strong></div></div>
        <div class="feedback"><span>这个结果正确吗？</span><template v-if="!feedbackSent"><button @click="feedback('correct')">正确</button><button @click="feedback('incorrect')">需修正</button></template><b v-else>反馈已进入 Badcase 候选池</b></div>
      </div>

      <div class="panel section-card">
        <div class="section-heading"><div><span class="eyebrow">TRACE</span><h2>执行轨迹</h2></div><span>{{ record.trace_id.slice(0, 8) }}</span></div>
        <div class="timeline"><div v-for="(event, index) in record.trace" :key="index"><i></i><b>{{ event.stage }}</b><span>{{ event.status }}</span><small>{{ event.elapsed_ms.toFixed(1) }} ms</small></div></div>
      </div>
    </template>
  </section>
</template>

