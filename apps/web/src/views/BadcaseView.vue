<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { Badcase } from '../types'

const items = ref<Badcase[]>([])
const loading = ref(true)
const error = ref('')
const filter = ref('')
const visible = computed(() => items.value.filter(item =>
  `${item.question}${item.category || ''}${item.comment || ''}`.toLowerCase().includes(filter.value.toLowerCase())))

async function load() {
  loading.value = true
  try { items.value = (await api.badcases()).items }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <section class="badcase-page">
    <div class="panel section-card">
      <div class="section-heading"><div><span class="eyebrow">HUMAN FEEDBACK</span><h2>Badcase 候选池</h2></div><button @click="load">刷新</button></div>
      <p>反馈只进入候选池；修正 SQL 通过审核、执行和防泄漏检查后才能进入训练集。</p>
      <input v-model="filter" placeholder="搜索问题、分类或备注…" />
      <p v-if="loading">正在加载…</p><p v-else-if="error" class="error">{{ error }}</p>
      <div v-else-if="!visible.length" class="empty-metric">暂无 Badcase</div>
      <article v-for="item in visible" :key="`${item.query_id}-${item.created_at}`" class="badcase-card">
        <div><span :class="['badge', item.rating]">{{ item.rating }}</span><small>{{ new Date(item.created_at).toLocaleString() }}</small></div>
        <h3>{{ item.question }}</h3>
        <pre v-if="item.predicted_sql" class="sql"><code>{{ item.predicted_sql }}</code></pre>
        <p v-if="item.comment">{{ item.comment }}</p>
        <small>Trace {{ item.trace_id.slice(0, 8) }} · {{ item.training_status }}</small>
      </article>
    </div>
  </section>
</template>
