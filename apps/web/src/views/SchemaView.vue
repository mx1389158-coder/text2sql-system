<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { Catalog } from '../types'

const catalog = ref<Catalog | null>(null)
const filter = ref('')
const selected = ref<string | null>(null)
const tables = computed(() => catalog.value?.tables.filter(t => `${t.name}${t.description}${t.aliases.join('')}`.toLowerCase().includes(filter.value.toLowerCase())) || [])
const graphNodes = computed(() => (catalog.value?.tables || []).map((table, index, all) => ({
  ...table,
  x: 400 + Math.cos((index / all.length) * Math.PI * 2) * 315,
  y: 250 + Math.sin((index / all.length) * Math.PI * 2) * 195,
})))
const graphEdges = computed(() => graphNodes.value.flatMap(table => table.foreign_keys.map(fk => ({
  from: table, to: graphNodes.value.find(node => node.name === fk.referred_table), key: `${table.name}.${fk.column}`,
}))).filter(edge => edge.to))
onMounted(async () => { catalog.value = await api.catalog(); selected.value = catalog.value.tables[0]?.name || null })
</script>

<template>
  <section class="catalog-layout" v-if="catalog">
    <div class="panel schema-graph"><div class="section-heading"><div><span class="eyebrow">RELATIONSHIP GRAPH</span><h2>Schema 关系图</h2></div><span>点击节点查看字段</span></div>
      <svg viewBox="0 0 800 500" role="img" aria-label="数据库表关系图">
        <line v-for="edge in graphEdges" :key="edge.key" :x1="edge.from.x" :y1="edge.from.y" :x2="edge.to?.x" :y2="edge.to?.y" />
        <g v-for="node in graphNodes" :key="node.name" :transform="`translate(${node.x},${node.y})`" @click="selected=node.name">
          <circle r="26" :class="{ selected: selected === node.name }"/><text text-anchor="middle" y="42">{{ node.name }}</text>
        </g>
      </svg>
    </div>
    <div class="panel catalog-list"><div class="section-heading"><div><span class="eyebrow">{{ catalog.version }}</span><h2>{{ catalog.database_id }}</h2></div><b>{{ catalog.tables.length }} 表</b></div><input v-model="filter" placeholder="搜索表、业务别名…" />
      <button v-for="table in tables" :key="table.name" :class="{ active: selected === table.name }" @click="selected = table.name"><b>{{ table.name }}</b><span>{{ table.description }}</span></button>
    </div>
    <div class="panel schema-detail" v-for="table in catalog.tables.filter(t => t.name === selected)" :key="table.name">
      <span class="eyebrow">TABLE / {{ catalog.schema }}</span><h2>{{ table.name }}</h2><p>{{ table.description }}</p>
      <div class="chips"><span v-for="alias in table.aliases" :key="alias">{{ alias }}</span></div>
      <table><thead><tr><th>字段</th><th>类型</th><th>说明</th></tr></thead><tbody><tr v-for="column in table.columns" :key="column.name"><td><b>{{ column.name }}</b><em v-if="column.primary_key">PK</em></td><td>{{ column.data_type }}</td><td>{{ column.description }}</td></tr></tbody></table>
      <h3>关联关系</h3><div class="relation" v-for="fk in table.foreign_keys" :key="fk.column">{{ table.name }}.{{ fk.column }} <b>→</b> {{ fk.referred_table }}.{{ fk.referred_column }}</div><p v-if="!table.foreign_keys.length">没有外键关联</p>
    </div>
  </section>
</template>

