<script setup lang="ts">
// 使用指南页：把「怎么用航策向标」讲清楚，并给可直接点的场景问题库
import { ref, computed } from 'vue'

const emit = defineEmits<{
  (e: 'ask', q: string): void
  (e: 'goto', key: string): void
}>()

// ===== 快速上手 =====
const STEPS = [
  {
    n: '01',
    title: '直接说你要什么',
    desc: '不用学语法。像跟同事交代任务一样描述目标，航策向标自己决定该查库、该搜索还是该翻知识库。',
    action: 'chat',
    actionText: '去提问 →',
  },
  {
    n: '02',
    title: '看它调用了哪些能力',
    desc: '右侧会实时显示子智能体调用链路（网络搜索 / 数据库查询 / 知识库检索）与耗时，全程可追溯。',
    action: 'stats',
    actionText: '看数据底表 →',
  },
  {
    n: '03',
    title: '把结果带走',
    desc: '生成的报告会落到会话产物里，可在线预览、单独下载，也能去报告中心跨会话打包。',
    action: 'files',
    actionText: '去报告中心 →',
  },
]

// ===== 能力矩阵 =====
const CAPS = [
  {
    name: '数据库查询',
    icon: 'M3 7l9-4 9 4v10l-9 4-9-4V7z',
    color: '#3aa878',
    desc: '对内嵌 SQLite 样例库做只读 SQL 聚合，能算库存、销售、效期等结构化问题。',
    sample: '查一下库存最少的 5 种药品',
  },
  {
    name: '网络搜索',
    icon: 'M11 4a7 7 0 100 14 7 7 0 000-14z M21 21l-4.3-4.3',
    color: '#9dc0ff',
    desc: '走 Tavily 实时检索公开网页，补外部政策、竞品、指南类信息。',
    sample: '最新的药品集采政策要点有哪些',
  },
  {
    name: '知识库检索',
    icon: 'M4 5h16v14H4z M4 9h16 M9 5v14',
    color: '#dcc489',
    desc: '对接 RAGFlow 做文档问答。当前云端版已熔断降级，本地部署恢复后自动启用。',
    sample: '帮我从知识库里找一下药品储存规范',
  },
  {
    name: '报告生成',
    icon: 'M6 3h9l4 4v14H6V3z M15 3v4h4',
    color: '#e7c977',
    desc: '把多步结论整理成 Markdown / 文档 / 数据表，落盘到 output/ 供下载与归档。',
    sample: '生成一份上月销售分析报告',
  },
]

// ===== 场景问题库 =====
const SCENES = [
  {
    key: 'inv',
    label: '库存管理',
    icon: 'M3 7l9-4 9 4v10l-9 4-9-4V7z',
    questions: [
      '查一下库存最少的 5 种药品',
      '哪些药品库存低于安全线？生成补货建议',
      '哪个仓库的库存占比最高',
      '统计各治疗领域的在库总量',
    ],
  },
  {
    key: 'sale',
    label: '销售分析',
    icon: 'M4 20V10M10 20V4M16 20v-8M22 20H2',
    questions: [
      '统计上个月销售额最高的 5 种药品',
      '按区域汇总销售额，哪个区域卖得最好',
      '近 7 天的销售趋势怎么样',
      '哪位销售代表的业绩排第一',
    ],
  },
  {
    key: 'drug',
    label: '药品档案',
    icon: 'M6 3h9l4 4v14H6V3z',
    questions: [
      '阿莫西林的商品名、厂家和批准文号是什么',
      '哪些药品是抗生素类，各有哪些规格',
      '列出所有注射剂剂型的药品',
      '一共有多少个治疗领域，各有多少种药',
    ],
  },
  {
    key: 'mix',
    label: '综合分析',
    icon: 'M12 3v18M3 12h18',
    questions: [
      '结合库存和销售，哪些药该补货、哪些该清库存',
      '找出卖得好但库存偏低的药品，给补货优先级',
      '生成一份经营月报，包含库存与销售两大部分',
      '效期临近的药品有哪些，建议怎么处理',
    ],
  },
]
const activeScene = ref('inv')
const activeQuestions = computed(() => SCENES.find((s) => s.key === activeScene.value)?.questions || [])

// ===== 数据表速查 =====
const TABLES = [
  { name: 'drugs', label: '药品主数据', fields: ['drug_id', 'generic_name', 'brand_name', 'specifications', 'dosage_form', 'manufacturer', 'therapeutic_area'] },
  { name: 'inventory', label: '库存记录', fields: ['inventory_id', 'drug_id', 'batch_number', 'quantity_on_hand', 'warehouse_location', 'expiry_date'] },
  { name: 'sales_records', label: '销售记录', fields: ['sale_id', 'drug_id', 'sale_date', 'quantity_sold', 'total_amount', 'region', 'sales_rep'] },
]

// ===== FAQ =====
const FAQS = [
  {
    q: '航策向标一次能处理多复杂的任务？',
    a: '主智能体会把任务拆成多步，按需调用 3 个子智能体，再汇总成结论。单轮里同时「查库 + 搜索 + 出报告」是支持的；链路与耗时右侧面板可实时看到。',
  },
  {
    q: '为什么有的问题它说要先查数据？',
    a: '涉及具体数字（库存、销量、金额）的问题必须走数据库才有依据，凭空编答案没有意义。航策向标会先跑 SQL 拿到真实结果，再据此写结论。',
  },
  {
    q: '生成的报告存在哪里，会不会丢？',
    a: '每个会话在 output/session_<id>/ 下独立存放，文件名带时间戳，不会被后续会话覆盖。可在「报告中心」跨会话查看、打包下载或删除。',
  },
  {
    q: '知识库检索为什么有时不可用？',
    a: '知识库子智能体依赖 RAGFlow 服务。云端演示环境为控制资源做了熔断降级，此时会明确提示「知识库暂不可用」，其余两条链路不受影响。这是有意设计的降级，不是故障。',
  },
  {
    q: '可以让它执行写操作（改数据、删数据）吗？',
    a: '不能，也不该。数据库以只读方式打开，SQL 白名单只放行查询语句并拦截危险词，写操作在设计上就不可能发生。',
  },
  {
    q: '支持哪些输出格式？',
    a: '常用的是 Markdown（可直接在线预览）、CSV / XLSX（数据表）、PNG / SVG（图表）。需要 Word 或 PDF 时直接在问题里说明即可。',
  },
]
const openFaq = ref<number | null>(0)
const toggleFaq = (i: number) => { openFaq.value = openFaq.value === i ? null : i }

// ===== 安全与边界 =====
const SAFETY = [
  { t: '只读数据库', d: 'SQLite 以 mode=ro 打开，物理上无法写入。' },
  { t: 'SQL 白名单', d: '仅放行 SELECT / SHOW / DESC / EXPLAIN，拦截 18 个危险关键字。' },
  { t: '表名校验', d: '先查 sqlite_master 确认表存在，非法表名直接拒绝。' },
  { t: '路径收敛', d: '文件下载 / 删除限制在 output/ 内，越界路径一律丢弃。' },
]

const VERSION = [
  { k: '应用版本', v: '航策向标医药智能体 · 云端演示版' },
  { k: '编排框架', v: 'DeepAgents / LangGraph 多智能体' },
  { k: '子智能体', v: '网络搜索 · 数据库查询 · 知识库检索' },
  { k: '数据源', v: '内嵌 SQLite 样例库（3 张表）' },
]
</script>

<template>
  <div class="cp-page cp-guide-page">
    <!-- 页头 -->
    <header class="cp-page-head">
      <div>
        <h1 class="cp-page-title">使用指南</h1>
        <p class="cp-page-desc">
          航策向标是一个能自己动手的医药数据助手：你把目标说清楚，它负责查库、搜索、写报告。
          这一页告诉你它有哪些能力、怎么问效果最好，以及有哪些边界。
        </p>
      </div>
      <div class="cp-page-head-acts">
        <button class="cp-btn cp-btn-primary" @click="emit('goto', 'chat')">✦ 开始提问</button>
        <button class="cp-btn" @click="emit('goto', 'stats')">数据快览</button>
        <button class="cp-btn" @click="emit('goto', 'files')">报告中心</button>
      </div>
    </header>

    <!-- 快速上手 -->
    <div class="cp-grid cp-grid-3 step-row">
      <div v-for="s in STEPS" :key="s.n" class="cp-card step-card">
        <span class="step-n">{{ s.n }}</span>
        <div class="step-title">{{ s.title }}</div>
        <div class="step-desc">{{ s.desc }}</div>
        <button class="cp-btn cp-btn-sm step-btn" @click="emit('goto', s.action)">{{ s.actionText }}</button>
      </div>
    </div>

    <!-- 能力矩阵 + 安全边界 -->
    <div class="guide-layout">
      <section class="cp-card">
        <div class="cp-card-title">
          它能做什么
          <span class="cp-mini-tag">点示例直接问</span>
        </div>
        <div class="cap-list">
          <div v-for="c in CAPS" :key="c.name" class="cap-item">
            <svg class="cap-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" :style="{ color: c.color }">
              <path :d="c.icon" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <div class="cap-body">
              <div class="cap-head">
                <span class="cap-name">{{ c.name }}</span>
                <span class="cap-dot" :style="{ background: c.color }"></span>
              </div>
              <div class="cap-desc">{{ c.desc }}</div>
              <button class="cap-sample" @click="emit('ask', c.sample)">
                <span class="sample-dot"></span>{{ c.sample }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <aside class="guide-side">
        <div class="cp-card">
          <div class="cp-card-title">安全与边界</div>
          <div v-for="s in SAFETY" :key="s.t" class="safety-item">
            <span class="safety-t">{{ s.t }}</span>
            <span class="safety-d">{{ s.d }}</span>
          </div>
        </div>

        <div class="cp-card">
          <div class="cp-card-title">版本信息</div>
          <div v-for="v in VERSION" :key="v.k" class="ver-row">
            <span class="ver-k">{{ v.k }}</span>
            <span class="ver-v">{{ v.v }}</span>
          </div>
        </div>
      </aside>
    </div>

    <!-- 场景问题库 -->
    <section class="cp-card scene-card">
      <div class="cp-card-title">
        场景问题库
        <span class="cp-mini-tag">共 {{ SCENES.reduce((s, x) => s + x.questions.length, 0) }} 条</span>
      </div>
      <div class="scene-tabs">
        <button
          v-for="s in SCENES"
          :key="s.key"
          class="scene-tab"
          :class="{ on: activeScene === s.key }"
          @click="activeScene = s.key"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
            <path :d="s.icon" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          {{ s.label }}
          <em>{{ s.questions.length }}</em>
        </button>
      </div>
      <div class="scene-qs">
        <button v-for="q in activeQuestions" :key="q" class="scene-q" @click="emit('ask', q)">
          <span class="sample-dot"></span>
          <span class="scene-q-text">{{ q }}</span>
          <span class="scene-q-go">去问 →</span>
        </button>
      </div>
    </section>

    <!-- 数据表速查 -->
    <section class="cp-card">
      <div class="cp-card-title">
        内嵌数据表速查
        <span class="cp-mini-tag">3 张表</span>
      </div>
      <div class="cp-grid cp-grid-3 tbl-row">
        <div v-for="t in TABLES" :key="t.name" class="tbl-card">
          <div class="tbl-head">
            <code class="tbl-name">{{ t.name }}</code>
            <span class="tbl-label">{{ t.label }}</span>
          </div>
          <div class="tbl-fields">
            <span v-for="f in t.fields" :key="f" class="tbl-field">{{ f }}</span>
          </div>
        </div>
      </div>
      <button class="cp-btn cp-btn-sm tbl-more" @click="emit('goto', 'stats')">查看完整数据与字段说明 →</button>
    </section>

    <!-- FAQ -->
    <section class="cp-card">
      <div class="cp-card-title">常见问题</div>
      <div class="faq-list">
        <div v-for="(f, i) in FAQS" :key="i" class="faq-item" :class="{ open: openFaq === i }">
          <button class="faq-q" @click="toggleFaq(i)">
            <span class="faq-mark">{{ openFaq === i ? '−' : '+' }}</span>
            <span>{{ f.q }}</span>
          </button>
          <div v-show="openFaq === i" class="faq-a">{{ f.a }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<style>
.step-row { margin-bottom: 16px; }
.step-card { position: relative; display: flex; flex-direction: column; gap: 8px; overflow: hidden; }
.step-n {
  font-size: 30px; font-weight: 900; line-height: 1;
  color: transparent; -webkit-text-stroke: 1.4px rgba(201, 164, 92, 0.55);
  letter-spacing: 1px;
}
.step-title { font-size: 14.5px; font-weight: 700; color: var(--cp-text); }
.step-desc { font-size: 12.5px; color: var(--cp-text-3); line-height: 1.75; flex: 1; }
.step-btn { align-self: flex-start; margin-top: 4px; }

.guide-layout { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 14px; align-items: start; margin-bottom: 16px; }
.guide-side { display: flex; flex-direction: column; gap: 14px; }

.cap-list { display: flex; flex-direction: column; gap: 12px; }
.cap-item {
  display: flex; gap: 11px; padding: 12px;
  background: var(--cp-surface-2); border: 1px solid var(--cp-border);
  border-radius: 11px; transition: all 0.15s;
}
.cap-item:hover { border-color: var(--cp-border-2); }
.cap-ico { flex-shrink: 0; margin-top: 2px; }
.cap-body { flex: 1; min-width: 0; }
.cap-head { display: flex; align-items: center; gap: 7px; }
.cap-name { font-size: 13.5px; font-weight: 700; color: var(--cp-text); }
.cap-dot { width: 6px; height: 6px; border-radius: 50%; }
.cap-desc { font-size: 12px; color: var(--cp-text-2); line-height: 1.7; margin: 5px 0 8px; }
.cap-sample {
  display: inline-flex; align-items: center; gap: 7px;
  background: transparent; border: 1px dashed var(--cp-border-2);
  color: var(--cp-gold); font-size: 11.5px;
  border-radius: 8px; padding: 6px 11px; cursor: pointer; transition: all 0.15s;
}
.cap-sample:hover { border-color: #c9a45c; background: rgba(201, 164, 92, 0.1); }
.sample-dot {
  width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, #3aa878, #c9a45c);
}

.safety-item { display: flex; flex-direction: column; gap: 3px; padding: 8px 0; border-bottom: 1px solid var(--cp-border); }
.safety-item:last-child { border-bottom: none; padding-bottom: 0; }
.safety-t { font-size: 12.5px; font-weight: 700; color: var(--cp-gold); }
.safety-d { font-size: 11.5px; color: var(--cp-text-2); line-height: 1.65; }

.ver-row { display: flex; justify-content: space-between; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--cp-border); font-size: 11.5px; }
.ver-row:last-child { border-bottom: none; padding-bottom: 0; }
.ver-k { color: var(--cp-text-3); flex-shrink: 0; }
.ver-v { color: var(--cp-text-2); text-align: right; }

.scene-card { margin-bottom: 16px; }
.scene-tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.scene-tab {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--cp-surface-2); border: 1px solid var(--cp-border);
  color: var(--cp-text-2); font-size: 12.5px; border-radius: 9px;
  padding: 8px 13px; cursor: pointer; transition: all 0.15s;
}
.scene-tab em {
  font-style: normal; font-size: 10.5px; font-weight: 800;
  background: rgba(201, 164, 92, 0.16); color: var(--cp-gold);
  border-radius: 999px; padding: 1px 6px;
}
.scene-tab:hover { border-color: var(--cp-green); color: var(--cp-text); }
.scene-tab.on { border-color: #c9a45c; color: var(--cp-gold); background: rgba(201, 164, 92, 0.13); font-weight: 700; }

.scene-qs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
.scene-q {
  display: flex; align-items: center; gap: 9px;
  background: var(--cp-surface-2); border: 1px solid var(--cp-border);
  color: var(--cp-text-2); font-size: 12.5px; text-align: left;
  border-radius: 10px; padding: 11px 13px; cursor: pointer; transition: all 0.15s;
}
.scene-q:hover { border-color: #c9a45c; color: var(--cp-text); }
.scene-q-text { flex: 1; min-width: 0; }
.scene-q-go { font-size: 11px; color: var(--cp-gold); opacity: 0; transition: opacity 0.15s; flex-shrink: 0; }
.scene-q:hover .scene-q-go { opacity: 1; }

.tbl-row { margin-bottom: 12px; }
.tbl-card { background: var(--cp-surface-2); border: 1px solid var(--cp-border); border-radius: 11px; padding: 12px 13px; }
.tbl-head { display: flex; align-items: center; gap: 8px; margin-bottom: 9px; }
.tbl-name {
  font-size: 12px; font-weight: 700; color: var(--cp-gold);
  background: rgba(201, 164, 92, 0.14); border-radius: 6px; padding: 2px 7px;
}
.tbl-label { font-size: 12.5px; color: var(--cp-text-2); }
.tbl-fields { display: flex; flex-wrap: wrap; gap: 5px; }
.tbl-field { font-size: 10.5px; font-family: monospace; color: var(--cp-text-3); background: var(--cp-surface-3); border-radius: 5px; padding: 2px 6px; }
.tbl-more { }

.faq-list { display: flex; flex-direction: column; gap: 8px; }
.faq-item { background: var(--cp-surface-2); border: 1px solid var(--cp-border); border-radius: 10px; overflow: hidden; transition: all 0.15s; }
.faq-item.open { border-color: #c9a45c; }
.faq-q {
  display: flex; align-items: center; gap: 10px; width: 100%;
  background: transparent; border: none; color: var(--cp-text);
  font-size: 13px; font-weight: 600; text-align: left;
  padding: 12px 14px; cursor: pointer;
}
.faq-mark {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: rgba(201, 164, 92, 0.16); color: var(--cp-gold);
  font-size: 14px; font-weight: 700; line-height: 1;
}
.faq-a { padding: 0 14px 13px 42px; font-size: 12.5px; color: var(--cp-text-2); line-height: 1.8; }

@media (max-width: 1100px) {
  .guide-layout { grid-template-columns: minmax(0, 1fr); }
  .scene-qs { grid-template-columns: minmax(0, 1fr); }
  .cp-guide-page .cp-grid-3 { grid-template-columns: minmax(0, 1fr); }
}
</style>
