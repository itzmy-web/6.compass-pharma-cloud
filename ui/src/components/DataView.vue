<script setup lang="ts">
// 数据快览页：内嵌 pharma.sqlite 的只读浏览
// 统计概览 + 表切换 + 关键词过滤 + 行数选择 + 数据表格 + 字段说明 + 导出 CSV
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const emit = defineEmits<{
  (e: 'ask', q: string): void
  (e: 'open-reports'): void
}>()

interface TableInfo { name: string; rows: number }

const TABLE_LABELS: Record<string, string> = {
  drugs: '药品主数据',
  inventory: '库存记录',
  sales_records: '销售记录',
}
const TABLE_DESC: Record<string, string> = {
  drugs: '药品档案：通用名 / 商品名 / 批准文号 / 规格 / 剂型 / 厂家 / 治疗领域',
  inventory: '批次库存：在库数量 / 仓库库位 / 生产日期 / 有效期',
  sales_records: '销售流水：销售日期 / 数量 / 单价 / 金额 / 客户 / 区域 / 销售代表',
}
const TABLE_ICON: Record<string, string> = {
  drugs: 'M6 3h9l4 4v14H6V3z',
  inventory: 'M3 7l9-4 9 4v10l-9 4-9-4V7z',
  sales_records: 'M4 20V10M10 20V4M16 20v-8M22 20H2',
}

// ===== 字段说明（数据字典） =====
interface FieldDoc { name: string; type: string; note: string; pk?: boolean }
const DICT: Record<string, FieldDoc[]> = {
  drugs: [
    { name: 'drug_id', type: 'INT', note: '药品主键，其他两张表靠它关联', pk: true },
    { name: 'generic_name', type: 'VARCHAR(100)', note: '通用名（如「阿莫西林」），问数主要靠这个字段' },
    { name: 'brand_name', type: 'VARCHAR(100)', note: '商品名 / 品牌名' },
    { name: 'approval_number', type: 'VARCHAR(50)', note: '国药准字批准文号' },
    { name: 'specifications', type: 'VARCHAR(100)', note: '规格，如 0.25g×24 粒' },
    { name: 'dosage_form', type: 'VARCHAR(50)', note: '剂型：片剂 / 胶囊 / 注射剂等' },
    { name: 'manufacturer', type: 'VARCHAR(100)', note: '生产厂家' },
    { name: 'therapeutic_area', type: 'VARCHAR(50)', note: '治疗领域：抗生素 / 解热镇痛 / 心血管…' },
    { name: 'description', type: 'TEXT', note: '适应症等文字描述' },
    { name: 'created_at', type: 'TIMESTAMP', note: '建档时间' },
  ],
  inventory: [
    { name: 'inventory_id', type: 'INT', note: '库存记录主键', pk: true },
    { name: 'drug_id', type: 'INT', note: '关联 drugs.drug_id' },
    { name: 'batch_number', type: 'VARCHAR(50)', note: '批号，同一种药可能有多批' },
    { name: 'quantity_on_hand', type: 'INT', note: '在库数量，「库存最少」类问题看这个' },
    { name: 'warehouse_location', type: 'VARCHAR(50)', note: '仓库库位编码' },
    { name: 'production_date', type: 'DATE', note: '生产日期' },
    { name: 'expiry_date', type: 'DATE', note: '有效期至，「临期药品」类问题看这个' },
    { name: 'last_updated', type: 'TIMESTAMP', note: '最近一次更新时间' },
  ],
  sales_records: [
    { name: 'sale_id', type: 'INT', note: '销售流水主键', pk: true },
    { name: 'drug_id', type: 'INT', note: '关联 drugs.drug_id' },
    { name: 'sale_date', type: 'DATE', note: '销售日期，「上个月 / 近 7 天」类问题看这个' },
    { name: 'quantity_sold', type: 'INT', note: '销售数量' },
    { name: 'unit_price', type: 'DECIMAL(10,2)', note: '单价' },
    { name: 'total_amount', type: 'DECIMAL(15,2)', note: '销售额 = 单价 × 数量' },
    { name: 'customer_name', type: 'VARCHAR(100)', note: '客户名称' },
    { name: 'region', type: 'VARCHAR(50)', note: '销售区域' },
    { name: 'sales_rep', type: 'VARCHAR(50)', note: '销售代表' },
  ],
}

// ===== 状态 =====
const tables = ref<TableInfo[]>([])
const stats = ref<{ drugs: number; inventory: number; sales_records: number } | null>(null)
const activeTable = ref('')
const columns = ref<string[]>([])
const rows = ref<string[][]>([])
const loading = ref(false)
const keyword = ref('')
const limit = ref(20)
const error = ref('')

const tableLabel = (n: string) => TABLE_LABELS[n] || n
const activeLabel = computed(() => tableLabel(activeTable.value))

// 关键词过滤（对当前已加载的行做本地筛选）
const filteredRows = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return rows.value
  return rows.value.filter((r) => r.some((v) => String(v).toLowerCase().includes(kw)))
})

const activeDict = computed(() => DICT[activeTable.value] || [])

const loadStats = async () => {
  try {
    const res = await axios.get('/api/db/stats')
    stats.value = res.data
  } catch { stats.value = null }
}

const loadTables = async () => {
  try {
    const res = await axios.get('/api/db/tables')
    tables.value = res.data.tables || []
  } catch { tables.value = [] }
}

const loadTable = async (name: string) => {
  activeTable.value = name
  keyword.value = ''
  loading.value = true
  error.value = ''
  rows.value = []
  columns.value = []
  try {
    const res = await axios.get('/api/db/table', { params: { name, limit: limit.value } })
    if (res.data.error) { error.value = res.data.error } else {
      columns.value = res.data.columns || []
      rows.value = res.data.rows || []
    }
  } catch {
    error.value = '读取失败，请稍后重试。'
  }
  loading.value = false
}

const refreshAll = async () => {
  await Promise.all([loadStats(), loadTables()])
  if (activeTable.value) await loadTable(activeTable.value)
}

const changeLimit = async () => { if (activeTable.value) await loadTable(activeTable.value) }

// 导出 CSV（当前筛选后的数据）
const exportCsv = () => {
  if (!columns.value.length) return
  const esc = (v: string) => `"${String(v).replace(/"/g, '""')}"`
  const lines = [columns.value.map(esc).join(','), ...filteredRows.value.map((r) => r.map(esc).join(','))]
  const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${activeTable.value}_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// 示例问题：按当前表给不同的追问
const SAMPLE_QUESTIONS = computed<Record<string, string[]>>(() => ({
  drugs: [
    '这 10 种药品分别属于哪些治疗领域？各有多少种',
    '列出所有片剂剂型的药品及其规格',
    '阿莫西林的商品名、厂家和批准文号是什么',
  ],
  inventory: [
    '查一下库存最少的 5 种药品',
    '哪些药品库存低于安全线？生成补货建议',
    '哪些批次的药品快到期了？按有效期排序',
  ],
  sales_records: [
    '统计上个月销售额最高的 5 种药品',
    '按区域汇总销售额，哪个区域卖得最好',
    '近 7 天的销售趋势怎么样',
  ],
}))

const activeSamples = computed(() => SAMPLE_QUESTIONS.value[activeTable.value] || [])

onMounted(async () => {
  await Promise.all([loadStats(), loadTables()])
  if (tables.value.length) await loadTable(tables.value[0]!.name)
})
</script>

<template>
  <div class="cp-page cp-data-page">
    <!-- 页头 -->
    <header class="cp-page-head">
      <div>
        <h1 class="cp-page-title">数据快览</h1>
        <p class="cp-page-desc">
          内嵌 <code>pharma.sqlite</code> 样例库的只读浏览：药品主数据 / 库存记录 / 销售记录三张表。
          可切换查看、按关键词过滤、调整行数、导出 CSV；要交叉分析或出结论，直接在对话框问航策向标。
        </p>
      </div>
      <div class="cp-page-head-acts">
        <button class="cp-btn" @click="refreshAll">↻ 刷新</button>
        <button class="cp-btn" :disabled="!filteredRows.length" @click="exportCsv">⬇ 导出 CSV</button>
        <button class="cp-btn cp-btn-primary" @click="emit('ask', `帮我分析一下${activeLabel}这张表`)">
          ✦ 用自然语言问数据
        </button>
      </div>
    </header>

    <!-- 概览统计 -->
    <div class="cp-grid cp-grid-4 stat-row">
      <div class="cp-stat-card">
        <span class="cp-stat-val">{{ stats?.drugs ?? '—' }}</span>
        <span class="cp-stat-label">药品主数据（种）</span>
        <span class="cp-stat-hint">drugs · 药品档案</span>
      </div>
      <div class="cp-stat-card">
        <span class="cp-stat-val">{{ stats?.inventory ?? '—' }}</span>
        <span class="cp-stat-label">库存记录（条）</span>
        <span class="cp-stat-hint">inventory · 批次级库存</span>
      </div>
      <div class="cp-stat-card">
        <span class="cp-stat-val">{{ stats?.sales_records ?? '—' }}</span>
        <span class="cp-stat-label">销售记录（条）</span>
        <span class="cp-stat-hint">sales_records · 销售流水</span>
      </div>
      <div class="cp-stat-card">
        <span class="cp-stat-val">{{ tables.length }}</span>
        <span class="cp-stat-label">可查业务表（张）</span>
        <span class="cp-stat-hint">SQLite · 只读白名单</span>
      </div>
    </div>

    <!-- 主体：表格 + 侧栏说明 -->
    <div class="data-layout">
      <section class="cp-card data-main">
        <!-- 表切换 -->
        <div class="table-tabs">
          <button
            v-for="t in tables"
            :key="t.name"
            class="table-tab"
            :class="{ active: activeTable === t.name }"
            @click="loadTable(t.name)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path :d="TABLE_ICON[t.name] || 'M4 6h16M4 12h16M4 18h16'" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span>{{ tableLabel(t.name) }}</span>
            <em>{{ t.rows }}</em>
          </button>
          <div v-if="tables.length === 0" class="cp-empty">未读取到数据表</div>
        </div>

        <div class="table-desc">{{ TABLE_DESC[activeTable] || '' }}</div>

        <!-- 工具栏 -->
        <div class="table-toolbar">
          <input v-model="keyword" class="table-search" type="text" placeholder="在当前数据里过滤（任意字段包含）…" />
          <select v-model.number="limit" class="table-select" @change="changeLimit">
            <option :value="10">10 行</option>
            <option :value="20">20 行</option>
            <option :value="50">50 行</option>
            <option :value="100">100 行</option>
          </select>
          <span class="table-count">
            显示 <b>{{ filteredRows.length }}</b> / {{ rows.length }} 行
            <template v-if="keyword">（已过滤）</template>
          </span>
        </div>

        <!-- 数据表格 -->
        <div class="table-wrap">
          <div v-if="loading" class="cp-empty">加载中…</div>
          <div v-else-if="error" class="cp-empty">{{ error }}</div>
          <table v-else-if="columns.length" class="data-grid">
            <thead>
              <tr>
                <th class="idx-col">#</th>
                <th v-for="c in columns" :key="c">{{ c }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in filteredRows" :key="i">
                <td class="idx-col">{{ i + 1 }}</td>
                <td v-for="(v, j) in r" :key="j" :title="v">{{ v }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="cp-empty">暂无数据</div>
        </div>

        <div class="table-foot">
          只读展示 · 表名走 <code>sqlite_master</code> 白名单校验 · 超过 100 行请直接向航策向标提问聚合
        </div>
      </section>

      <!-- 右栏：字段说明 + 示例问题 + 安全说明 -->
      <aside class="data-side">
        <div class="cp-card">
          <div class="cp-card-title">
            字段说明
            <span class="cp-mini-tag">{{ activeLabel }}</span>
          </div>
          <div class="dict-list">
            <div v-for="f in activeDict" :key="f.name" class="dict-item">
              <div class="dict-top">
                <code class="dict-name">{{ f.name }}</code>
                <span v-if="f.pk" class="dict-pk">PK</span>
                <span class="dict-type">{{ f.type }}</span>
              </div>
              <div class="dict-note">{{ f.note }}</div>
            </div>
          </div>
        </div>

        <div class="cp-card">
          <div class="cp-card-title">这张表可以这样问</div>
          <button
            v-for="q in activeSamples"
            :key="q"
            class="sample-btn"
            @click="emit('ask', q)"
          >
            <span class="sample-dot"></span>{{ q }}
          </button>
          <button class="cp-btn cp-btn-sm sample-more" @click="emit('open-reports')">
            去看已生成的报告 →
          </button>
        </div>

        <div class="cp-card safety-card">
          <div class="cp-card-title">只读与安全</div>
          <ul class="safety-list">
            <li>数据库以 <code>mode=ro</code> 只读方式打开，写操作不可能发生</li>
            <li>SQL 白名单只放行 SELECT / SHOW / DESC / EXPLAIN，拦截 18 个危险词</li>
            <li>表名先查 <code>sqlite_master</code> 校验存在性，非法表名直接 404</li>
            <li>前端只展示样例数据，真实业务库请在生产环境另行接入</li>
          </ul>
        </div>
      </aside>
    </div>
  </div>
</template>

<style>
.data-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 14px;
  align-items: start;
}
.data-main { display: flex; flex-direction: column; gap: 12px; padding: 16px 18px 14px; }
.data-side { display: flex; flex-direction: column; gap: 14px; }

.stat-row { margin-bottom: 16px; }

.table-tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.table-tab {
  display: flex; align-items: center; gap: 7px;
  background: var(--cp-surface-2); border: 1px solid var(--cp-border);
  color: var(--cp-text-2); font-size: 12.5px;
  border-radius: 10px; padding: 8px 13px; cursor: pointer; transition: all 0.15s;
}
.table-tab em {
  font-style: normal; font-size: 11px; font-weight: 800;
  background: rgba(201, 164, 92, 0.18); color: var(--cp-gold);
  border-radius: 999px; padding: 1px 7px;
}
.table-tab:hover { border-color: var(--cp-green); color: var(--cp-text); }
.table-tab.active {
  border-color: #c9a45c; color: var(--cp-gold);
  background: rgba(201, 164, 92, 0.13); font-weight: 700;
}
.table-desc { font-size: 12px; color: var(--cp-text-3); line-height: 1.7; }

.table-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.table-search {
  flex: 1; min-width: 180px;
  background: var(--cp-surface-2); border: 1px solid var(--cp-border);
  color: var(--cp-text); font-size: 12.5px;
  border-radius: 9px; padding: 8px 12px; outline: none;
}
.table-search:focus { border-color: #c9a45c; }
.table-select {
  background: var(--cp-surface-2); border: 1px solid var(--cp-border);
  color: var(--cp-text-2); font-size: 12.5px;
  border-radius: 9px; padding: 8px 10px; cursor: pointer; outline: none;
}
.table-count { font-size: 11.5px; color: var(--cp-text-3); }
.table-count b { color: var(--cp-gold); }

.table-wrap {
  overflow: auto; max-height: 52vh;
  border: 1px solid var(--cp-border); border-radius: 11px;
  background: var(--cp-surface-2);
}
.data-grid { border-collapse: collapse; width: 100%; font-size: 12px; }
.data-grid th {
  position: sticky; top: 0; z-index: 1;
  background: var(--cp-surface-3); color: var(--cp-gold);
  font-weight: 700; text-align: left;
  padding: 9px 12px; border-bottom: 1px solid var(--cp-border-2);
  white-space: nowrap;
}
.data-grid td {
  color: var(--cp-text-2); padding: 8px 12px;
  border-bottom: 1px solid var(--cp-border);
  white-space: nowrap; max-width: 260px;
  overflow: hidden; text-overflow: ellipsis;
}
.data-grid tbody tr:nth-child(even) td { background: rgba(58, 168, 120, 0.045); }
.data-grid tbody tr:hover td { background: rgba(58, 168, 120, 0.1); }
.idx-col {
  width: 44px; color: var(--cp-text-3) !important;
  font-variant-numeric: tabular-nums; text-align: right;
}
.table-foot { font-size: 11px; color: var(--cp-text-3); }
.table-foot code, .cp-page-desc code, .safety-list code {
  background: rgba(201, 164, 92, 0.14); color: var(--cp-gold);
  border-radius: 5px; padding: 1px 5px; font-size: 11px;
}

.dict-list { display: flex; flex-direction: column; gap: 9px; max-height: 420px; overflow-y: auto; padding-right: 2px; }
.dict-item { border-left: 2px solid var(--cp-border-2); padding-left: 10px; }
.dict-top { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.dict-name { font-size: 12px; color: var(--cp-gold); font-weight: 700; }
.dict-pk {
  font-size: 9px; font-weight: 800; letter-spacing: 0.5px;
  background: rgba(58, 168, 120, 0.2); color: #7fd8ac;
  border-radius: 4px; padding: 1px 5px;
}
.dict-type { font-size: 10px; color: var(--cp-text-3); font-family: monospace; }
.dict-note { font-size: 11.5px; color: var(--cp-text-2); line-height: 1.65; margin-top: 3px; }

.sample-btn {
  display: flex; align-items: center; gap: 8px; width: 100%;
  background: var(--cp-surface-2); border: 1px solid var(--cp-border);
  color: var(--cp-text-2); font-size: 12px; text-align: left;
  border-radius: 9px; padding: 9px 11px; margin-bottom: 7px;
  cursor: pointer; transition: all 0.15s;
}
.sample-btn:hover { border-color: #c9a45c; color: var(--cp-gold); }
.sample-dot {
  width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, #3aa878, #c9a45c);
}
.sample-more { width: 100%; justify-content: center; }

.safety-card { background: var(--cp-surface); }
.safety-list { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 7px; }
.safety-list li { font-size: 11.5px; color: var(--cp-text-2); line-height: 1.65; }

@media (max-width: 1100px) {
  .data-layout { grid-template-columns: minmax(0, 1fr); }
  .data-side { flex-direction: column; }
}
</style>
