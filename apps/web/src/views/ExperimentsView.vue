<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api/client'
import type { EvalJob } from '../types'
const running = ref(false); const message = ref(''); const jobs = ref<EvalJob[]>([])
const evaluationDataset = ref('data/processed/smoke.jsonl')
const evaluationModel = ref('demo')
let timer: number | undefined
const cells = [
  ['E00','原始模型','完整 Schema / 单候选 / 无修正'],
  ['E10','微调模型','完整 Schema / 单候选 / 无修正'],
  ['E01','原始模型','Schema Linking / 候选 / 修正'],
  ['E11','微调模型','Schema Linking / 候选 / 修正'],
]
async function refresh() { try { jobs.value = (await api.evalJobs()).jobs } catch(e) { message.value = e instanceof Error ? e.message : String(e) } }
async function run() { running.value = true; try { const job = await api.startEval('optimized', evaluationDataset.value, evaluationModel.value); message.value = `评测任务已提交：${job.job_id}`; await refresh() } catch(e) { message.value = e instanceof Error ? e.message : String(e) } finally { running.value=false } }
onMounted(async () => {
  try {
    const system = await api.system()
    evaluationDataset.value = system.evaluation_dataset
    evaluationModel.value = system.model
  } catch(e) {
    message.value = e instanceof Error ? e.message : String(e)
  }
  await refresh()
  timer = window.setInterval(refresh, 1500)
})
onUnmounted(() => { if (timer) window.clearInterval(timer) })
const pct = (value?: number) => value === undefined ? '—' : `${(value * 100).toFixed(1)}%`
</script>

<template>
  <section class="experiments">
    <div class="hero-panel panel"><span class="eyebrow">REPRODUCIBLE EVALUATION</span><h2>模型能力与系统策略，分开测量</h2><p>固定盲测集、相同调用预算、完整记录延迟与资源。没有真实运行日志的数字不会出现在报告中。</p><button class="primary" :disabled="running" @click="run">{{ running ? '正在提交…' : '运行 Smoke 评测' }}</button><b v-if="message">{{ message }}</b></div>
    <div class="matrix"><article v-for="cell in cells" :key="cell[0]" class="panel"><span>{{ cell[0] }}</span><h3>{{ cell[1] }}</h3><p>{{ cell[2] }}</p><div class="empty-metric">尚未运行</div></article></div>
    <div class="panel section-card"><div class="section-heading"><div><span class="eyebrow">RUN HISTORY</span><h2>评测任务与结果</h2></div><button @click="refresh">刷新</button></div>
      <div v-if="!jobs.length" class="empty-metric">尚无评测任务</div>
      <article v-for="job in jobs" :key="job.job_id" class="eval-job">
        <div><b>{{ job.summary?.experiment_id || job.summary?.strategy || 'Smoke' }}</b><span :class="['badge', job.status]">{{ job.status }}</span><small>{{ job.job_id.slice(0, 8) }}</small></div>
        <p v-if="job.error" class="error">{{ job.error }}</p>
        <div v-if="job.summary" class="metric-strip">
          <span><small>EX</small><b>{{ pct(job.summary.execution_accuracy) }}</b></span>
          <span><small>{{ job.summary.test_suite_protocol === 'fixed_snapshot_proxy' ? 'FIXED SNAPSHOT' : 'TEST SUITE' }}</small><b>{{ pct(job.summary.test_suite_accuracy) }}</b></span>
          <span><small>TABLE R@K</small><b>{{ pct(job.summary.schema_recall_at_k) }}</b></span>
          <span><small>COLUMN R@K</small><b>{{ pct(job.summary.column_recall_at_k) }}</b></span>
          <span><small>P95</small><b>{{ job.summary.p95_latency_ms.toFixed(1) }} ms</b></span>
          <span><small>CALLS</small><b>{{ job.summary.model_calls }}</b></span>
        </div>
      </article>
    </div>
    <div class="panel section-card"><span class="eyebrow">QUALITY GATES</span><h2>报告必须包含</h2><div class="gate-grid"><div><b>SQL Valid Rate</b><span>解析与安全检查</span></div><div><b>Execution Accuracy</b><span>固定快照结果等价</span></div><div><b>Schema Recall@k</b><span>表与字段检索上限</span></div><div><b>Safety TPR / FPR</b><span>攻击拦截与误杀</span></div><div><b>Repair Gain</b><span>修好数减改坏数</span></div><div><b>p50 / p95</b><span>延迟与调用预算</span></div></div></div>
  </section>
</template>

