<script setup lang="ts">
// 报告中心页：跨会话汇总 output/ 下的全部产物文件
// 统计概览 + 三层筛选（类型 / 会话 / 关键词）+ 批量打包下载 + 删除 + 单个预览下载
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const emit = defineEmits<{
  (e: 'ask', q: string): void
  (e: 'open-data'): void
  (e: 'preview', f: { name: string; url: string }): void
  (e: 'changed'): void
}>()

interface ReportFile {
  name: string; path: string; rel: string; url: string
  session: string; ext: string; size: number; mtime: number
}
interface SessionInfo { id: string; count: number; size: number }

const EXT_TAG: Record<string, string> = {
  md: 'MD', docx: 'DOCX', doc: 'DOC', pdf: 'PDF', csv: 'CSV', xlsx: 'XLSX', xls: 'XLS',
  txt: 'TXT', json: 'JSON', log: 'LOG', html: 'HTML',
  png: 'PNG', jpg: 'JPG', jpeg: 'JPG', svg: 'SVG', gif: 'GIF', zip: 'ZIP',
}
const extTag = (e: string) => EXT_TAG[e] || (e ? e.toUpperCase().slice(0, 4) : 'FILE')

const fmtSize = (n: number) =>
  n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`

const fmtTime = (t: number) => {
  const d = new Date(t * 1000)
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// ===== 筛选项 =====
const EXT_GROUPS = [
  { key: '', label: '全部', exts: [] as string[] },
  { key: 'md', label: 'Markdown', exts: ['md'] },
  { key: 'doc', label: '文档', exts: ['docx', 'doc', 'pdf'] },
  { key: 'data', label: '数据表', exts: ['csv', 'xlsx', 'xls', 'json'] },
  { key: 'img', label: '图片', exts: ['png', 'jpg', 'jpeg', 'svg', 'gif'] },
  { key: 'text', label: '文本', exts: ['txt', 'log', 'html'] },
]

// ===== 状态 =====
const files = ref<ReportFile[]>([])
const sessions = ref<SessionInfo[]>([])
const totalSize = ref(0)
const loading = ref(false)
const extGroup = ref('')
const sessionFilter = ref('')
const keyword = ref('')
const selected = ref<Set<string>>(new Set())
const busy = ref('')

const loadReports = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/reports')
    files.value = res.data.files || []
    sessions.value = res.data.sessions || []
    totalSize.value = res.data.totalSize || 0
  } catch {
    files.value = []
    sessions.value = []
    totalSize.value = 0
  }
  loading.value = false
  // 清掉已经不存在的选中项
  const alive = new Set(files.value.map((f) => f.rel))
  selected.value = new Set([...selected.value].filter((k) => alive.has(k)))
}

const filtered = computed(() => {
  let list = files.value
  const group = EXT_GROUPS.find((g) => g.key === extGroup.value)
  if (group && group.exts.length) {
    const want = new Set(group.exts)
    list = list.filter((f) => want.has(f.ext))
  }
  if (sessionFilter.value) list = list.filter((f) => f.session === sessionFilter.value)
  const kw = keyword.value.trim().toLowerCase()
  if (kw) list = list.filter((f) => f.name.toLowerCase().includes(kw) || f.session.toLowerCase().includes(kw))
  return list
})

const filteredSize = computed(() => filtered.value.reduce((s, f) => s + f.size, 0))

// ===== 统计卡片 =====
const recent7d = computed(() => {
  const line = Date.now() / 1000 - 7 * 86400
  return files.value.filter((f) => f.mtime >= line).length
})
const sessionCount = computed(() => sessions.value.filter((s) => s.id !== '根目录').length)

// 类型分布（按分组统计，用于右栏可视化）
const groupStats = computed(() =>
  EXT_GROUPS.filter((g) => g.exts.length).map((g) => {
    const want = new Set(g.exts)
    const hit = files.value.filter((f) => want.has(f.ext))
    return { label: g.label, key: g.key, count: hit.length, size: hit.reduce((s, f) => s + f.size, 0) }
  }),
)
const maxGroupCount = computed(() => Math.max(1, ...groupStats.value.map((g) => g.count)))

// ===== 选择 =====
const isSel = (f: ReportFile) => selected.value.has(f.rel)
const toggleSel = (f: ReportFile) => {
  const s = new Set(selected.value)
  s.has(f.rel) ? s.delete(f.rel) : s.add(f.rel)
  selected.value = s
}
const allChecked = computed(() => filtered.value.length > 0 && filtered.value.every((f) => selected.value.has(f.rel)))
const toggleAll = () => {
  const s = new Set(selected.value)
  if (allChecked.value) filtered.value.forEach((f) => s.delete(f.rel))
  else filtered.value.forEach((f) => s.add(f.rel))
  selected.value = s
}
const clearSel = () => { selected.value = new Set() }

const selectedFiles = computed(() => filtered.value.filter((f) => selected.value.has(f.rel)))
const selectedSize = computed(() => selectedFiles.value.reduce((s, f) => s + f.size, 0))

// ===== 动作 =====
const downloadOne = (f: ReportFile) => {
  const a = document.createElement('a')
  a.href = f.url
  a.download = f.name
  document.body.appendChild(a)
  a.click()
  a.remove()
}

const downloadZip = async () => {
  const list = selectedFiles.value.length ? selectedFiles.value : filtered.value
  if (!list.length) return
  busy.value = 'zip'
  try {
    const res = await axios.post('/api/reports/zip', { paths: list.map((f) => f.rel) }, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `罗盘报告_${new Date().toISOString().slice(0, 10)}.zip`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    alert('打包失败，请稍后重试。')
  }
  busy.value = ''
}

const removeFiles = async (list: ReportFile[]) => {
  if (!list.length) return
  const names = list.slice(0, 5).map((f) => f.name).join('、')
  const more = list.length > 5 ? ` 等 ${list.length} 个文件` : ''
  if (!window.confirm(`确定删除「${names}」${more}？此操作不可恢复。`)) return
  busy.value = 'del'
  try {
    await axios.post('/api/reports/delete', { paths: list.map((f) => f.rel) })
    list.forEach((f) => selected.value.delete(f.rel))
    selected.value = new Set(selected.value)
    await loadReports()
    emit('changed')
  } catch {
    alert('删除失败，请稍后重试。')
  }
  busy.value = ''
}

const removeAll = () => removeFiles(filtered.value)

// ===== 引导：怎么让罗盘生成报告 =====
const GEN_TIPS = [
  { q: '生成一份上月销售分析报告（Markdown）', tag: '分析类' },
  { q: '哪些药品库存低于安全线？生成补货建议报告', tag: '运营类' },
  { q: '把近 7 天销售趋势整理成一份图表报告', tag: '趋势类' },
  { q: '汇总各区域的销售额并生成对比报告', tag: '区域类' },
]

const EXT_ICON = 'M6 3h9l4 4v14H6V3z M15 3v4h4'

onMounted(loadReports)

defineExpose({ reload: loadReports })
</script>

<template>
  <div class="cp-page cp-report-page">
    <!-- 页头 -->
    <header class="cp-page-head">
      <div>
        <h1 class="cp-page-title">报告中心</h1>
        <p class="cp-page-desc">
          跨会话汇总罗盘生成的全部产物：查询结果、分析报告、数据表、图表。
          支持按类型 / 会话筛选、关键词检索，多选后可一键打包下载或批量删除。
        </p>
      </div>
      <div class="cp-page-head-acts">
        <button class="cp-btn" :disabled="loading" @click="loadReports">↻ 刷新</button>
        <button class="cp-btn" :disabled="!filtered.length" @click="downloadZip">
          ⬇ {{ selectedFiles.length ? `打包选中（${selectedFiles.length}）` : `打包全部（${filtered.length}）` }}
        </button>
        <button
          class="cp-btn cp-btn-danger"
          :disabled="!selectedFiles.length || busy === 'del'"
          @click="removeFiles(selectedFiles)"
        >
          🗑 删除选中（{{ selectedFiles.length }}）
        </button>
      </div>
    </header>

    <!-- 概览 -->
    <div class="cp-grid cp-grid-4 stat-row">
      <div class="cp-stat-card">
        <span class="cp-stat-val">{{ files.length }}</span>
        <span class="cp-stat-label">产物文件（个）</span>
        <span class="cp-stat-hint">output/ 目录下全部文件</span>
      </div>
      <div class="cp-stat-card">
        <span class="cp-stat-val">{{ fmtSize(totalSize) }}</span>
        <span class="cp-stat-label">合计体积</span>
        <span class="cp-stat-hint">全部产物的磁盘占用</span>
      </div>
      <div class="cp-stat-card">
        <span class="cp-stat-val">{{ sessionCount }}</span>
        <span class="cp-stat-label">覆盖会话（个）</span>
        <span class="cp-stat-hint">每次对话生成一个 session 目录</span>
      </div>
      <div class="cp-stat-card">
        <span class="cp-stat-val">{{ recent7d }}</span>
        <span class="cp-stat-label">近 7 天新增（个）</span>
        <span class="cp-stat-hint">按文件修改时间统计</span>
      </div>
    </div>

    <!-- 工具栏：类型分组 + 会话 + 关键词 -->
    <div class="cp-card toolbar">
      <div class="tb-row">
        <div class="tb-chips">
          <button
            v-for="g in EXT_GROUPS"
            :key="g.key"
            class="tb-chip"
            :class="{ on: extGroup === g.key }"
            @click="extGroup = g.key"
          >
            {{ g.label }}
            <em>{{ g.key ? files.filter((f) => g.exts.includes(f.ext)).length : files.length }}</em>
          </button>
        </div>
        <select v-model="sessionFilter" class="tb-select">
          <option value="">全部会话</option>
          <option v-for="s in sessions" :key="s.id" :value="s.id">
            {{ s.id }}（{{ s.count }} 个）
          </option>
        </select>
        <input v-model="keyword" class="tb-search" type="text" placeholder="搜索文件名 / 会话名…" />
      </div>
      <div class="tb-row tb-meta">
        <button class="tb-check" :class="{ on: allChecked }" @click="toggleAll">
          <span class="cp-rep-checkbox" :class="{ on: allChecked }"></span>
          全选当前 {{ filtered.length }} 个
        </button>
        <span class="tb-count">
          共 <b>{{ filtered.length }}</b> 个文件 · {{ fmtSize(filteredSize) }}
          <template v-if="selectedFiles.length">　已选 <b>{{ selectedFiles.length }}</b> 个（{{ fmtSize(selectedSize) }}）</template>
        </span>
        <button v-if="selectedFiles.length" class="tb-clear" @click="clearSel">清空选择</button>
        <button v-if="filtered.length" class="tb-clear tb-danger" @click="removeAll">删除当前筛选全部</button>
      </div>
    </div>

    <!-- 主体 -->
    <div class="report-layout">
      <!-- 文件列表 -->
      <section class="cp-card report-main">
        <div v-if="loading" class="cp-empty">加载中…</div>

        <!-- 空态：告诉用户怎么产出报告 -->
        <div v-else-if="!files.length" class="cp-empty gen-empty">
          <svg class="cp-empty-ico" width="46" height="46" viewBox="0 0 24 24" fill="none">
            <path :d="EXT_ICON" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
          </svg>
          <div class="gen-empty-title">还没有生成任何报告</div>
          <div class="gen-empty-sub">在对话框里直接说出你要的成果，罗盘会跑完子智能体并把文件落到这里。</div>
          <div class="gen-empty-btns">
            <button v-for="t in GEN_TIPS" :key="t.q" class="sample-btn" @click="emit('ask', t.q)">
              <span class="sample-dot"></span>
              <span class="sample-q">{{ t.q }}</span>
              <span class="sample-tag">{{ t.tag }}</span>
            </button>
          </div>
        </div>

        <!-- 筛选后为空 -->
        <div v-else-if="!filtered.length" class="cp-empty">
          当前筛选条件下没有文件
          <button class="cp-btn cp-btn-sm" @click="extGroup = ''; sessionFilter = ''; keyword = ''">重置筛选</button>
        </div>

        <!-- 列表 -->
        <div v-else class="rep-list">
          <div v-for="f in filtered" :key="f.rel" class="cp-rep-row" :class="{ sel: isSel(f) }">
            <span class="cp-rep-checkbox" :class="{ on: isSel(f) }" @click="toggleSel(f)"></span>
            <span class="cp-rep-tag" :data-ext="f.ext">{{ extTag(f.ext) }}</span>
            <div class="cp-rep-meta" @click="emit('preview', { name: f.name, url: f.url })">
              <div class="cp-rep-fname" :title="f.name">{{ f.name }}</div>
              <div class="cp-rep-fsub">
                {{ f.session }} · {{ fmtSize(f.size) }} · {{ fmtTime(f.mtime) }}
              </div>
            </div>
            <div class="cp-rep-row-act">
              <button class="cp-rep-mini" @click="emit('preview', { name: f.name, url: f.url })">预览</button>
              <button class="cp-rep-mini" @click="downloadOne(f)">下载</button>
              <button class="cp-rep-mini cp-rep-mini-del" @click="removeFiles([f])">删除</button>
            </div>
          </div>
        </div>
      </section>

      <!-- 右栏 -->
      <aside class="report-side">
        <div class="cp-card">
          <div class="cp-card-title">产出类型分布</div>
          <div v-if="!files.length" class="side-dim">暂无数据</div>
          <div v-else class="dist-list">
            <div v-for="g in groupStats" :key="g.key" class="dist-item">
              <div class="dist-top">
                <span class="dist-label">{{ g.label }}</span>
                <span class="dist-num">{{ g.count }} 个 · {{ fmtSize(g.size) }}</span>
              </div>
              <div class="dist-bar">
                <i :style="{ width: (g.count / maxGroupCount) * 100 + '%' }"></i>
              </div>
            </div>
          </div>
        </div>

        <div class="cp-card">
          <div class="cp-card-title">
            怎么让罗盘写报告
            <span class="cp-mini-tag">点一下就直接问</span>
          </div>
          <button v-for="t in GEN_TIPS" :key="t.q" class="sample-btn" @click="emit('ask', t.q)">
            <span class="sample-dot"></span>{{ t.q }}
          </button>
        </div>

        <div class="cp-card">
          <div class="cp-card-title">文件落在哪里</div>
          <ul class="path-list">
            <li><code>output/session_&lt;id&gt;/</code> 每次对话一个目录</li>
            <li>主智能体 + 3 个子智能体（网络搜索 / 数据库 / 知识库）都会往里写</li>
            <li>删除操作只作用于 <code>output/</code> 内，越界路径直接丢弃</li>
            <li>打包下载同名文件会自动加序号，不会互相覆盖</li>
          </ul>
          <button class="cp-btn cp-btn-sm side-more" @click="emit('open-data')">去数据快览查底层数据 →</button>
        </div>
      </aside>
    </div>
  </div>
</template>

<style>
.stat-row { margin-bottom: 16px; }

.toolbar { display: flex; flex-direction: column; gap: 10px; padding: 13px 15px; margin-bottom: 14px; }
.tb-row { display: flex; gap: 9px; align-items: center; flex-wrap: wrap; }
.tb-chips { display: flex; gap: 7px; flex-wrap: wrap; }
.tb-chip {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--cp-surface-2); border: 1px solid var(--cp-border);
  color: var(--cp-text-2); font-size: 12px; border-radius: 8px;
  padding: 6px 11px; cursor: pointer; transition: all 0.15s;
}
.tb-chip em {
  font-style: normal; font-size: 10.5px; font-weight: 800;
  background: rgba(201, 164, 92, 0.16); color: var(--cp-gold);
  border-radius: 999px; padding: 1px 6px;
}
.tb-chip:hover { border-color: var(--cp-green); color: var(--cp-text); }
.tb-chip.on { border-color: #c9a45c; color: var(--cp-gold); background: rgba(201, 164, 92, 0.13); font-weight: 700; }

.tb-select, .tb-search {
  background: var(--cp-surface-2); border: 1px solid var(--cp-border);
  color: var(--cp-text); font-size: 12.5px; border-radius: 9px;
  padding: 8px 11px; outline: none;
}
.tb-select { cursor: pointer; color: var(--cp-text-2); }
.tb-search { flex: 1; min-width: 160px; }
.tb-search:focus, .tb-select:focus { border-color: #c9a45c; }

.tb-meta { font-size: 11.5px; color: var(--cp-text-3); }
.tb-check {
  display: inline-flex; align-items: center; gap: 7px;
  background: transparent; border: none; color: var(--cp-text-2);
  font-size: 12px; cursor: pointer; padding: 2px 0;
}
.tb-count { margin-left: auto; }
.tb-count b { color: var(--cp-gold); }
.tb-clear {
  background: transparent; border: none; color: var(--cp-text-3);
  font-size: 11.5px; cursor: pointer; text-decoration: underline; padding: 0;
}
.tb-clear:hover { color: var(--cp-gold); }
.tb-danger:hover { color: var(--cp-red); }

.report-layout { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 14px; align-items: start; }
.report-main { padding: 12px; }
.report-side { display: flex; flex-direction: column; gap: 14px; }

.rep-list { display: flex; flex-direction: column; gap: 7px; }

.gen-empty { padding: 34px 20px; }
.gen-empty-title { font-size: 15px; font-weight: 700; color: var(--cp-text); }
.gen-empty-sub { font-size: 12.5px; color: var(--cp-text-3); max-width: 460px; }
.gen-empty-btns { display: flex; flex-direction: column; gap: 7px; width: 100%; max-width: 460px; margin-top: 8px; }

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
.gen-empty-btns .sample-btn { margin-bottom: 0; }
.sample-q { flex: 1; min-width: 0; }
.sample-tag {
  flex-shrink: 0; font-size: 10px; font-weight: 700;
  background: rgba(201, 164, 92, 0.14); color: var(--cp-gold);
  border-radius: 999px; padding: 1px 7px;
}

.dist-list { display: flex; flex-direction: column; gap: 10px; }
.dist-top { display: flex; justify-content: space-between; font-size: 11.5px; margin-bottom: 5px; }
.dist-label { color: var(--cp-text-2); }
.dist-num { color: var(--cp-text-3); }
.dist-bar { height: 6px; border-radius: 999px; background: var(--cp-surface-3); overflow: hidden; }
.dist-bar i { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #2f8a63, #3aa878, #c9a45c); }
.side-dim { font-size: 12px; color: var(--cp-text-3); }

.path-list { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 7px; }
.path-list li { font-size: 11.5px; color: var(--cp-text-2); line-height: 1.65; }
.path-list code {
  background: rgba(201, 164, 92, 0.14); color: var(--cp-gold);
  border-radius: 5px; padding: 1px 5px; font-size: 11px;
}
.side-more { width: 100%; justify-content: center; margin-top: 12px; }

@media (max-width: 1100px) {
  .report-layout { grid-template-columns: minmax(0, 1fr); }
}
</style>
