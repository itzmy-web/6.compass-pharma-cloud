<script setup lang="ts">
import { ref, onMounted, nextTick, computed } from 'vue'
import axios from 'axios'
import { marked } from 'marked'
import LoginGate from './components/LoginGate.vue'
import DataView from './components/DataView.vue'
import ReportCenter from './components/ReportCenter.vue'
import GuideView from './components/GuideView.vue'

// Types
interface Message {
  role: 'user' | 'ai' | 'system'
  content: string
  displayContent?: string  // 打字机效果：渐进显示的内容；打完后等于 content
  logs?: LogItem[]
  files?: FileItem[]
  timestamp?: number
}

interface LogItem {
  type: string
  title: string
  details: any
  timestamp: string
}

interface FileItem {
  name: string
  path: string
  url: string
}

// State
const inputQuery = ref('')
const messages = ref<Message[]>([])
const status = ref<'idle' | 'running'>('idle')
const socket = ref<WebSocket | null>(null)
const currentSessionPath = ref('')
const currentSessionUrl = ref('')
const messagesEndRef = ref<HTMLElement | null>(null)
const isWelcomeScreen = computed(() => messages.value.length === 0)
const isSidebarOpen = ref(false)
const fileList = ref<any[]>([])
// 生成一个持久的会话ID，如果页面不刷新，ID不变
const currentThreadId = ref<string>(crypto.randomUUID())

// ========== 页面路由：每个导航项一个独立页面 ==========
// chat=对话工作台 / data=数据快览 / reports=报告中心 / guide=使用指南
const activeView = ref<'chat' | 'data' | 'reports' | 'guide'>('chat')

// ========== 登录门禁 ==========
// 每次打开（刷新）都先显示登录页；登录成功才进入任务工作台。
// localStorage 只保存账号信息用于"快捷进入"与问候语，不保存"已跳过登录"状态。
const isLoggedIn = ref(false)
const authInfo = ref<{ channel: string; phone: string } | null>(null)
const handleLoggedIn = (info: { channel: string; phone: string }) => {
  authInfo.value = info
  isLoggedIn.value = true
  try { localStorage.setItem('compass_auth', JSON.stringify(info)) } catch {}
}
const maskedUser = computed(() => {
  const p = authInfo.value?.phone
  return p ? `${p.slice(0, 3)}****${p.slice(7)}` : 'User'
})

// ========== 增强功能：断线提示 / 历史会话 / 时间线 / 快捷提问 ==========
const wsStatus = ref<'connecting' | 'open' | 'closed'>('connecting')
const isHistoryOpen = ref(false)

interface HistoryItem {
  threadId: string
  title: string
  time: number
  messages: Message[]
}
const historyList = ref<HistoryItem[]>([])

const loadHistory = () => {
  try {
    historyList.value = JSON.parse(localStorage.getItem('compass_history') || '[]')
  } catch { historyList.value = [] }
}

// 任务结束时把当前消息流快照存入 localStorage（按 threadId 去重，最多 20 条）
const saveHistory = () => {
  try {
    const firstUser = messages.value.find(m => m.role === 'user')
    if (!firstUser) return
    const item: HistoryItem = {
      threadId: currentThreadId.value,
      title: firstUser.content.slice(0, 40),
      time: Date.now(),
      messages: JSON.parse(JSON.stringify(messages.value))
    }
    historyList.value = [item, ...historyList.value.filter(h => h.threadId !== item.threadId)].slice(0, 20)
    localStorage.setItem('compass_history', JSON.stringify(historyList.value))
  } catch { /* 存储失败不影响主流程 */ }
}

const restoreHistory = (h: HistoryItem) => {
  if (status.value === 'running') return
  messages.value = JSON.parse(JSON.stringify(h.messages))
  currentThreadId.value = h.threadId
  currentSessionPath.value = ''
  currentSessionUrl.value = ''
  fileList.value = []
  isHistoryOpen.value = false
}

const deleteHistory = (threadId: string) => {
  historyList.value = historyList.value.filter(h => h.threadId !== threadId)
  try { localStorage.setItem('compass_history', JSON.stringify(historyList.value)) } catch {}
}

const handleLogout = () => {
  // 只切换到登录页；保留 compass_auth 以便登录页"快捷进入"
  isLoggedIn.value = false
}

// 快捷提问：点 chip 直接填入并发送
const quickAsk = (q: string) => {
  if (status.value === 'running') return
  inputQuery.value = q
  sendMessage()
}

// 本机累计提问数（演示用，localStorage 计数）
const qaCount = ref(Number(localStorage.getItem('compass_qa_count') || '0'))

const QUICK_PROMPTS = [
  '查询阿莫西林的库存和价格',
  '统计上个月销售额最高的 5 种药品',
  '哪些药品库存低于安全线？生成补货建议报告',
  '搜索阿莫西林近期的行业资讯，生成一份 Markdown 摘要',
]

// 运行中浮条：显示最新执行步骤与累计步数
const timelineText = computed(() => {
  const lastAi = messages.value[messages.value.length - 1]
  const logs = lastAi?.logs
  if (!logs || logs.length === 0) return '正在思考…'
  return logs[logs.length - 1]?.title || '正在执行…'
})
const timelineSteps = computed(() => {
  const lastAi = messages.value[messages.value.length - 1]
  return lastAi?.logs?.length || 0
})

// ========== ⑥ 打字机效果 ==========
// 完结撒花：任务结果打字完成后全屏彩带（纯 canvas，无依赖）
const fireConfetti = () => {
  const canvas = document.createElement('canvas')
  canvas.className = 'cp-confetti'
  canvas.width = window.innerWidth
  canvas.height = window.innerHeight
  document.body.appendChild(canvas)
  const ctx = canvas.getContext('2d')
  if (!ctx) { canvas.remove(); return }
  const colors = ['#2f8a63', '#3aa878', '#c9a45c', '#ffd166', '#5fd4a0', '#7ec699']
  const parts = Array.from({ length: 140 }, () => ({
    x: Math.random() * canvas.width,
    y: -20 - Math.random() * canvas.height * 0.4,
    w: 5 + Math.random() * 6,
    h: 8 + Math.random() * 9,
    c: colors[Math.floor(Math.random() * colors.length)] ?? '#2f8a63',
    vy: 2.2 + Math.random() * 3.4,
    vx: -1.6 + Math.random() * 3.2,
    rot: Math.random() * Math.PI,
    vr: -0.12 + Math.random() * 0.24,
  }))
  let frames = 0
  const tick = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    for (const p of parts) {
      p.y += p.vy; p.x += p.vx; p.rot += p.vr
      ctx.save()
      ctx.translate(p.x, p.y)
      ctx.rotate(p.rot)
      ctx.fillStyle = p.c
      ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h)
      ctx.restore()
    }
    frames++
    if (frames < 230) requestAnimationFrame(tick)
    else canvas.remove()
  }
  requestAnimationFrame(tick)
}

const typewrite = (msg: Message, full: string) => {
  msg.content = full
  msg.displayContent = ''
  const step = Math.max(3, Math.ceil(full.length / 160))  // 约 160 帧打完
  let i = 0
  const timer = setInterval(() => {
    i += step
    if (!messages.value.includes(msg)) { clearInterval(timer); return }
    msg.displayContent = full.slice(0, i)
    scrollToBottom()
    if (i >= full.length) {
      clearInterval(timer)
      msg.displayContent = full
      saveHistory()
      fireConfetti()
    }
  }, 16)
}

// ========== ⑦ 代码高亮 + 复制按钮 ==========
const SQL_KEYWORDS = [
  'SELECT', 'FROM', 'WHERE', 'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT', 'JOIN',
  'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'OUTER JOIN', 'ON', 'AS', 'AND', 'OR',
  'NOT', 'NULL', 'LIKE', 'IN', 'BETWEEN', 'UNION', 'DISTINCT', 'INSERT INTO',
  'INSERT', 'UPDATE', 'DELETE', 'CREATE TABLE', 'CREATE', 'DROP', 'ALTER', 'SHOW',
  'DESCRIBE', 'DESC', 'EXPLAIN', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'CASE',
  'WHEN', 'THEN', 'ELSE', 'END', 'VALUES', 'SET', 'TABLES', 'PRAGMA',
]
const escapeHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

const highlightSql = (code: string): string => {
  // 顺序：字符串 → 注释 → 关键词 → 数字（先转义再着色）
  let out = escapeHtml(code)
  const store: string[] = []
  const stash = (html: string) => { store.push(html); return `\u0000${store.length - 1}\u0000` }
  // 字符串字面量
  out = out.replace(/'[^'\n]*'|"[^"\n]*"/g, m => stash(`<span class="cp-tok-str">${m}</span>`))
  // 注释
  out = out.replace(/(--[^\n<]*)/g, m => stash(`<span class="cp-tok-comment">${m}</span>`))
  // 关键词（词边界）
  const kwPattern = new RegExp(`\\b(${SQL_KEYWORDS.join('|')})\\b`, 'gi')
  out = out.replace(kwPattern, m => stash(`<span class="cp-tok-kw">${m}</span>`))
  // 数字
  out = out.replace(/\b(\d+(\.\d+)?)\b/g, m => stash(`<span class="cp-tok-num">${m}</span>`))
  // 还原被 stash 的片段（其内部不再处理）
  out = out.replace(/\u0000(\d+)\u0000/g, (_, idx) => store[Number(idx)] ?? '')
  return out
}

const enhanceMarkdown = (html: string): string => {
  // 给每个 <pre><code> 加高亮（sql）+ 复制按钮 + 语言标签
  return html.replace(/<pre><code(?:\s+class="language-(\w+)")?>([\s\S]*?)<\/code><\/pre>/g, (_, lang: string | undefined, body: string | undefined) => {
    const code = body ?? ''
    const isSql = lang && /sql/i.test(lang)
    const inner = isSql ? highlightSql(code) : code
    return `<div class="cp-code-wrap"><div class="cp-code-bar"><span class="cp-code-lang">${(lang || 'code').toUpperCase()}</span>` +
      `<button class="cp-copy-btn" type="button">复制</button></div>` +
      `<pre><code${lang ? ` class="language-${lang}"` : ''}>${inner}</code></pre></div>`
  })
}

// 复制按钮：全局事件委托（v-html 注入的元素无法绑局部监听）
const setupCopyDelegate = () => {
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    const btn = target.closest('.cp-copy-btn') as HTMLElement | null
    if (!btn) return
    const wrap = btn.closest('.cp-code-wrap')
    const code = wrap?.querySelector('pre code')
    if (!code) return
    navigator.clipboard.writeText(code.textContent || '').then(() => {
      btn.textContent = '已复制 ✓'
      setTimeout(() => { btn.textContent = '复制' }, 1500)
    })
  })
}

// ========== ⑧ 报告在线预览 ==========
interface PreviewFile { name: string; url: string }
const previewFile = ref<PreviewFile | null>(null)
const previewHtml = ref('')
const previewLoading = ref(false)

const openPreview = async (f: PreviewFile) => {
  previewFile.value = f
  previewHtml.value = ''
  if (/\.md$/i.test(f.name)) {
    previewLoading.value = true
    try {
      const res = await axios.get(f.url, { responseType: 'text' })
      previewHtml.value = enhanceMarkdown(String(marked(String(res.data))))
    } catch {
      previewHtml.value = '<p style="color:#ff6b81">预览加载失败，请尝试直接下载。</p>'
    }
    previewLoading.value = false
  }
  // 非 md 文件（pdf/图片等）用 iframe 直接预览
}
const closePreview = () => { previewFile.value = null; previewHtml.value = '' }

// ========== ⑨ 深浅主题 ==========
const theme = ref<'dark' | 'light'>(
  (localStorage.getItem('compass_theme') as 'dark' | 'light') || 'dark'
)
const applyTheme = () => {
  document.body.classList.toggle('theme-light', theme.value === 'light')
}
const toggleTheme = () => {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  try { localStorage.setItem('compass_theme', theme.value) } catch {}
  applyTheme()
}

// ========== ⑩ 语音输入 ==========
const isRecording = ref(false)
const speechSupported = ref(false)
let recognition: any = null

const initSpeech = () => {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SR) { speechSupported.value = false; return }
  speechSupported.value = true
  recognition = new SR()
  recognition.lang = 'zh-CN'
  recognition.continuous = true
  recognition.interimResults = false
  recognition.onresult = (e: any) => {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) {
        const text = e.results[i][0].transcript.trim()
        if (text) inputQuery.value = (inputQuery.value ? inputQuery.value + ' ' : '') + text
      }
    }
  }
  recognition.onend = () => { isRecording.value = false }
  recognition.onerror = () => { isRecording.value = false }
}
const toggleRecord = () => {
  if (!recognition) {
    messages.value.push({ role: 'system', content: '当前浏览器不支持语音识别（推荐使用 Edge 浏览器），请直接键入问题。', timestamp: Date.now() })
    return
  }
  if (isRecording.value) {
    recognition.stop()
    isRecording.value = false
  } else {
    try {
      recognition.start()
      isRecording.value = true
    } catch { isRecording.value = false }
  }
}

// Helper: Scroll to bottom
const scrollToBottom = async () => {
  await nextTick()
  if (messagesEndRef.value) {
    messagesEndRef.value.scrollIntoView({ behavior: 'smooth' })
  }
}

// Fetch Files
const fetchFiles = async () => {
  if (!currentSessionPath.value) return
  try {
    const res = await axios.get('/api/files', {
      params: { path: currentSessionPath.value }
    })
    if (res.data.files) {
      fileList.value = res.data.files.map((f: any) => ({
        ...f,
        // 使用新的下载 API，传入绝对路径
        url: `/api/download?path=${encodeURIComponent(f.path)}`
      }))
    }
  } catch (e) {
    console.error('Failed to fetch files', e)
  }
}

// WebSocket Connection
const connectWebSocket = () => {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/${currentThreadId.value}`)

  ws.onopen = () => {
    console.log('WebSocket Connected')
    wsStatus.value = 'open'
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      handleSocketMessage(data)
    } catch (e) {
      console.error('Error parsing WS message:', e)
    }
  }

  ws.onclose = () => {
    // 已被新连接替换（如「新对话」重建 WS）时不再自动重连旧地址
    if (socket.value !== ws) return
    console.log('WebSocket Disconnected, retrying in 3s...')
    wsStatus.value = 'closed'
    setTimeout(connectWebSocket, 3000)
  }

  socket.value = ws
}

// Handle Incoming Messages
const handleSocketMessage = (data: any) => {
  const { type, event, message, data: eventData } = data

  if (type === 'pong') return

  let lastAiMsg = messages.value.slice().reverse().find(m => m.role === 'ai')
  
  if (event === 'session_created') {
    currentSessionPath.value = eventData.path
    const parts = eventData.path.split(/output[\\/]/)
    if (parts.length > 1) {
      currentSessionUrl.value = `/outputs/${parts[1].replace(/\\/g, '/')}`
    }
    isSidebarOpen.value = true
    fetchFiles()
  } else if (event === 'tool_start') {
    // 触发文件列表刷新，以确保用户能看到生成的文件
    if (currentSessionPath.value) {
      // 延迟一点刷新，因为工具刚开始运行，文件可能还没生成
      // 但如果是“写入文件”类工具，可能很快就有了
      // 这里可以尝试立即刷新 + 延迟刷新
      fetchFiles()
      setTimeout(fetchFiles, 2000)
    }

    if (lastAiMsg) {
      if (!lastAiMsg.logs) lastAiMsg.logs = []
      lastAiMsg.logs.push({
        type: 'tool',
        title: `使用的工具： ${eventData.tool_name}...`,
        details: eventData.args,
        timestamp: new Date().toLocaleTimeString()
      })
      
      if (eventData.args && eventData.args.filename && currentSessionUrl.value) {
        if (!lastAiMsg.files) lastAiMsg.files = []
        const fileUrl = `${currentSessionUrl.value}/${eventData.args.filename}`
        // Avoid duplicates
        if (!lastAiMsg.files.find(f => f.name === eventData.args.filename)) {
           lastAiMsg.files.push({
            name: eventData.args.filename,
            path: eventData.args.filename,
            url: fileUrl
          })
        }
      }
    }
  } else if (event === 'assistant_call') {
    // 同样刷新文件列表
    if (currentSessionPath.value) {
        fetchFiles()
    }
     if (lastAiMsg) {
      if (!lastAiMsg.logs) lastAiMsg.logs = []
      lastAiMsg.logs.push({
        type: 'agent',
        title: `正在使用助手： ${eventData.assistant_name}...`,
        details: eventData.args,
        timestamp: new Date().toLocaleTimeString()
      })
    }
  } else if (event === 'task_result') {
    if (lastAiMsg) {
      // 打字机效果：完整结果逐字显示
      typewrite(lastAiMsg, eventData.result)
    } else {
       const newMsg: Message = {
        role: 'ai',
        content: eventData.result,
        displayContent: '',
        timestamp: Date.now()
      }
      messages.value.push(newMsg)
      typewrite(newMsg, eventData.result)
    }
    status.value = 'idle'
    fetchFiles()
  } else if (event === 'error') {
     messages.value.push({
      role: 'system',
      content: `Error: ${message}`,
      timestamp: Date.now()
    })
    status.value = 'idle'
    saveHistory()
  }
  
  scrollToBottom()
}

// Send Message
const sendMessage = async () => {
  if ((!inputQuery.value.trim() && selectedFiles.value.length === 0) || status.value === 'running') return

  const query = inputQuery.value
  inputQuery.value = ''
  status.value = 'running'
  qaCount.value++
  try { localStorage.setItem('compass_qa_count', String(qaCount.value)) } catch {}

  messages.value.push({
    role: 'user',
    content: query,
    timestamp: Date.now()
  })

  messages.value.push({
    role: 'ai',
    content: '', // Start empty, show "Thinking" via logs/status if needed, or placeholder
    logs: [],
    files: [],
    timestamp: Date.now()
  })

  scrollToBottom()

  // Handle File Upload
  if (selectedFiles.value.length > 0) {
    console.log('Uploading files:', selectedFiles.value)
    
    // Log to UI
    const lastAiMsg = messages.value[messages.value.length - 1]
    if (lastAiMsg && lastAiMsg.role === 'ai') {
        if (!lastAiMsg.logs) lastAiMsg.logs = []
        
        const fileDetails = selectedFiles.value.map(f => ({ name: f.name, size: f.size }))
        
        lastAiMsg.logs.push({
            type: 'info',
            title: `Uploading ${selectedFiles.value.length} file(s)...`,
            details: fileDetails,
            timestamp: new Date().toLocaleTimeString()
        })
    }

    // Actual Upload
    try {
        const formData = new FormData()
        // Ensure thread_id is available
        if (typeof currentThreadId !== 'undefined' && currentThreadId.value) {
             formData.append('thread_id', currentThreadId.value)
        } else {
             // Fallback if no thread ID (should ideally not happen as initialized in state)
             console.warn('No thread ID found for upload')
        }

        selectedFiles.value.forEach(file => {
            console.log(`Appending file to FormData: name=${file.name}, size=${file.size}, type=${file.type}`)
            formData.append('files', file)
        })

        await axios.post('/api/upload', formData, {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        })
        
        // Clear files after successful upload
        selectedFiles.value = []
        
        if (lastAiMsg && lastAiMsg.logs) {
            lastAiMsg.logs.push({
                type: 'success',
                title: 'Files uploaded successfully',
                details: null,
                timestamp: new Date().toLocaleTimeString()
            })
        }

    } catch (e: any) {
        console.error('Upload failed', e)
        if (lastAiMsg && lastAiMsg.logs) {
            lastAiMsg.logs.push({
                type: 'error',
                title: 'File upload failed',
                details: e.message || 'Unknown error',
                timestamp: new Date().toLocaleTimeString()
            })
        }
        // Don't stop task execution, but maybe warn user?
    }
  }

  try {
    const payload: any = { query }
    // Only add thread_id if it exists and is not empty
    if (typeof currentThreadId !== 'undefined' && currentThreadId.value) {
      payload.thread_id = currentThreadId.value
    }
    console.log('Sending request payload:', payload)
    const res = await axios.post('/api/task', payload)
    
    if (res.data && res.data.thread_id) {
      currentThreadId.value = res.data.thread_id
    }
  } catch (error: any) {
    console.error('Request failed:', error)
    let errorMsg = 'Failed to send request.'
    if (error.message) errorMsg += ` (${error.message})`
    if (error.response && error.response.data) {
        errorMsg += ` Server says: ${JSON.stringify(error.response.data)}`
    }
    
    messages.value.push({
      role: 'system',
      content: errorMsg,
      timestamp: Date.now()
    })
    status.value = 'idle'
  }
}

// File Upload
const fileInputRef = ref<HTMLInputElement | null>(null)
const selectedFiles = ref<File[]>([])

const triggerFileUpload = () => {
  fileInputRef.value?.click()
}

const handleFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    // Append new files to existing list
    selectedFiles.value = [...selectedFiles.value, ...Array.from(target.files)]
    console.log('Files selected:', selectedFiles.value)
    // Reset input so same file can be selected again if needed
    target.value = ''
  }
}

const removeFile = (index: number) => {
  selectedFiles.value.splice(index, 1)
}

const renderMarkdown = (text: string) => {
  if (!text) return '<span class="typing-indicator">Thinking...</span>'
  return enhanceMarkdown(String(marked(text)))
}

// ========== ⑪ 左侧栏：导航 / 新对话 / 导出对话 / 数据库速览 / 使用指南 ==========
const isSideNavOpen = ref(false)      // 移动端抽屉开关
const activeNav = ref('chat')

// 数据库速览（GET /api/db/stats）
const dbStats = ref<{ drugs: number; inventory: number; sales_records: number } | null>(null)
const fetchDbStats = async () => {
  try {
    const res = await axios.get('/api/db/stats')
    dbStats.value = res.data
  } catch { dbStats.value = null }
}

const shortThreadId = computed(() => currentThreadId.value.slice(0, 8))

// 新对话：保存当前会话 -> 清空状态 -> 换 threadId 并重建 WebSocket
const startNewChat = () => {
  if (status.value === 'running') {
    messages.value.push({ role: 'system', content: '当前任务正在执行，请等任务结束后再开新对话。', timestamp: Date.now() })
    isSideNavOpen.value = false
    return
  }
  saveHistory()
  messages.value = []
  currentSessionPath.value = ''
  currentSessionUrl.value = ''
  fileList.value = []
  isSidebarOpen.value = false
  currentThreadId.value = crypto.randomUUID()
  try { socket.value?.close() } catch {}
  connectWebSocket()
  isSideNavOpen.value = false
}

// 导出当前对话为 Markdown 下载
const exportChat = () => {
  if (messages.value.length === 0) {
    messages.value.push({ role: 'system', content: '当前还没有对话内容，先提问一句再导出吧。', timestamp: Date.now() })
    isSideNavOpen.value = false
    return
  }
  const lines: string[] = ['# 罗盘对话记录', '', `- 导出时间：${new Date().toLocaleString()}`, '']
  for (const m of messages.value) {
    if (m.role === 'user') lines.push(`## 🙋 提问\n\n${m.content}\n`)
    else if (m.role === 'ai') lines.push(`## 🧭 罗盘回答\n\n${m.content}\n`)
    else lines.push(`> ${m.content}\n`)
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `罗盘对话_${new Date().toISOString().slice(0, 10)}.md`
  a.click()
  URL.revokeObjectURL(url)
  isSideNavOpen.value = false
}

// 侧边栏导航：切到对应独立页面
const navGo = (key: string) => {
  activeNav.value = key
  isSideNavOpen.value = false
  if (key === 'chat') {
    activeView.value = 'chat'
    nextTick(() => ((document.querySelector('.input-container textarea') as HTMLElement | null)?.focus?.()))
  } else if (key === 'stats') {
    activeView.value = 'data'
  } else if (key === 'files') {
    activeView.value = 'reports'
  } else if (key === 'guide') {
    activeView.value = 'guide'
  }
}

// 从其他页面点「去问一句」：切回对话页并自动发送
const askFromPage = (q: string) => {
  const text = (q || '').trim()
  if (!text) return
  activeNav.value = 'chat'
  activeView.value = 'chat'
  nextTick(() => quickAsk(text))
}

// ========== ⑫ 侧栏增强：快速提问 / 历史内嵌 / 数据速览摘要 ==========
// 数据浏览的完整实现已拆到 DataView 页，此处只保留侧栏摘要所需状态。
// 会话文件数（报告文件徽标）
const sessionFileCount = computed(() => reportTotal.value || fileList.value.length)

// ===== 右侧「本次会话产物」面板 =====
const SIDE_FILE_FILTERS = [
  { key: '', label: '全部' },
  { key: 'md', label: 'MD' },
  { key: 'docx,doc,pdf', label: '文档' },
  { key: 'csv,xlsx,xls,json', label: '数据' },
  { key: 'png,jpg,jpeg,svg,gif', label: '图片' },
  { key: 'txt,log,html', label: '文本' },
]
const sideFileFilter = ref('')
const sideFileExt = (n: string) => (n.includes('.') ? n.split('.').pop()!.toLowerCase() : '')
const sessionFileSize = computed(() => fileList.value.reduce((s, f) => s + (f.size || 0), 0))
const sideFileView = computed(() => {
  if (!sideFileFilter.value) return fileList.value
  const want = new Set(sideFileFilter.value.split(','))
  return fileList.value.filter((f) => want.has(sideFileExt(f.name)))
})

// 空状态引导：点一下直接去问
const SIDE_FILE_HINTS = [
  '查询阿莫西林的库存和价格',
  '统计上个月销售额最高的 5 种药品',
  '生成一份补货建议报告（Markdown）',
]
const sideAskHint = (q: string) => {
  isSidebarOpen.value = false
  askFromPage(q)
}

// 侧栏底部主题切换
const sideThemeLabel = computed(() => (theme.value === 'dark' ? '浅色模式' : '深色模式'))

// 清空全部历史
const clearAllHistory = () => {
  historyList.value = []
  try { localStorage.setItem('compass_history', '[]') } catch {}
}

// 侧栏快捷提问（与欢迎屏 chip 同一套问题，对话中也能一键发）
const sideQuickAsk = (q: string) => {
  isSideNavOpen.value = false
  quickAsk(q)
}

// 侧栏快捷提问（精简 3 条，覆盖查数 / 分析 / 报告）
const SIDE_QUICK_PROMPTS = [
  '查一下库存最少的 5 种药品',
  '统计上个月销售额最高的 5 种药品',
  '哪些药品库存低于安全线？生成补货建议',
]

// ========== ⑬ 报告中心（完整功能在 ReportCenter 页；此处只保留侧栏「最近报告」摘要） ==========
interface ReportFile {
  name: string; path: string; rel: string; url: string
  session: string; ext: string; size: number; mtime: number
}

const reportFiles = ref<ReportFile[]>([])
const reportTotal = ref(0)

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
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const loadReports = async () => {
  try {
    const res = await axios.get('/api/reports')
    reportFiles.value = res.data.files || []
    reportTotal.value = res.data.total || 0
  } catch {
    reportFiles.value = []
    reportTotal.value = 0
  }
}

// 打开报告中心页 / 数据快览页（侧栏按钮与导航共用）
const openReportCenter = () => {
  activeNav.value = 'files'
  activeView.value = 'reports'
  isSideNavOpen.value = false
}

const openDataCenter = () => {
  activeNav.value = 'stats'
  activeView.value = 'data'
  isSideNavOpen.value = false
}

const reportPreview = (f: ReportFile) => {
  closePreview()
  openPreview({ name: f.name, url: f.url })
}

// 侧栏「最近报告」：取最新 3 个
const recentReports = computed(() => reportFiles.value.slice(0, 3))

onMounted(() => {
  loadHistory()
  setupCopyDelegate()
  initSpeech()
  applyTheme()
  connectWebSocket()
  fetchDbStats()
  loadReports()
})
</script>

<template>
  <!-- 登录门禁：未登录时全屏登录页，登录后才挂载工作台 -->
  <LoginGate v-if="!isLoggedIn" @logged-in="handleLoggedIn" />
  <div v-else class="app-container">
    <!-- ======== 左侧导航栏（参考大屏风：品牌 / 导航 / 数据速览 / 账号） ======== -->
    <div v-if="isSideNavOpen" class="cp-side-mask" :class="{ open: isSideNavOpen }" @click="isSideNavOpen = false"></div>
    <aside class="cp-sidebar" :class="{ open: isSideNavOpen }">
      <div class="cp-side-brand">
        <div class="cp-brand-logo">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L15 9L22 12L15 15L12 22L9 15L2 12L9 9L12 2Z" fill="#0d362a"/>
            <circle cx="12" cy="12" r="3.2" fill="#c9a45c"/>
          </svg>
        </div>
        <div>
          <div class="cp-side-title">经营罗盘</div>
          <div class="cp-side-sub">罗盘项目 · PHARMA AI</div>
        </div>
      </div>

      <nav class="cp-side-nav">
        <button class="cp-nav-item" :class="{ active: activeNav === 'chat' }" @click="navGo('chat')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M4 5h16v11H8l-4 4V5z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          </svg>
          对话工作台
        </button>
        <button class="cp-nav-item" :class="{ active: activeNav === 'stats' }" @click="navGo('stats')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M4 20V10M10 20V4M16 20v-8M22 20H2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          数据快览
        </button>
        <button class="cp-nav-item" :class="{ active: activeNav === 'files' }" @click="navGo('files')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M6 3h9l4 4v14H6V3z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
            <path d="M9 12h7M9 16h7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          报告中心
          <span v-if="sessionFileCount > 0" class="cp-nav-badge">{{ sessionFileCount }}</span>
        </button>
        <button class="cp-nav-item" :class="{ active: activeNav === 'guide' }" @click="navGo('guide')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/>
            <path d="M12 11v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            <circle cx="12" cy="7.5" r="1.2" fill="currentColor"/>
          </svg>
          使用指南
        </button>
      </nav>

      <!-- 快捷操作 -->
      <div class="cp-side-section">
        <div class="cp-side-sec-title">快捷操作</div>
        <button class="cp-nav-item cp-nav-new" @click="startNewChat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          新对话
        </button>
        <button class="cp-nav-item" @click="exportChat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M12 3v12M7 10l5 5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M4 19h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          导出对话
        </button>
      </div>

      <!-- 最近报告（跨会话最新产物，一键进报告中心） -->
      <div class="cp-side-section cp-report-card">
        <div class="cp-side-sec-head">
          <span class="cp-side-sec-title" style="margin:0;">最近报告（{{ reportTotal }}）</span>
          <button class="cp-h-clear" @click="loadReports" title="刷新">↻</button>
        </div>
        <div v-if="recentReports.length === 0" class="cp-side-empty">
          暂无产物，让罗盘「生成一份报告」试试
        </div>
        <div v-else class="cp-side-report-list">
          <button
            v-for="f in recentReports"
            :key="f.rel"
            class="cp-side-report-item"
            @click="reportPreview(f)"
            :title="f.rel"
          >
            <span class="cp-rep-tag" :data-ext="f.ext">{{ extTag(f.ext) }}</span>
            <span class="cp-rep-name">{{ f.name }}</span>
            <span class="cp-rep-size">{{ fmtSize(f.size) }}</span>
          </button>
        </div>
        <button class="cp-db-more" @click="openReportCenter()">打开报告中心 →</button>
      </div>

      <!-- 数据库速览（实时统计，可点开看数据） -->
      <div class="cp-side-section cp-db-card">
        <div class="cp-side-sec-title">数据库速览</div>
        <div class="cp-db-row"><span>药品主数据</span><b>{{ dbStats?.drugs ?? '—' }} 种</b></div>
        <div class="cp-db-row"><span>库存记录</span><b>{{ dbStats?.inventory ?? '—' }} 条</b></div>
        <div class="cp-db-row"><span>销售记录</span><b>{{ dbStats?.sales_records ?? '—' }} 条</b></div>
        <button class="cp-db-more" @click="openDataCenter()">查看数据明细 →</button>
        <div class="cp-db-foot">pharma.sqlite · 只读白名单</div>
      </div>

      <!-- 快捷提问（一键发送） -->
      <div class="cp-side-section">
        <div class="cp-side-sec-title">快捷提问</div>
        <button
          v-for="q in SIDE_QUICK_PROMPTS"
          :key="q"
          class="cp-side-quick"
          :disabled="status === 'running'"
          @click="sideQuickAsk(q)"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
          </svg>
          <span>{{ q }}</span>
        </button>
      </div>

      <!-- 历史会话（内嵌，可恢复 / 删除 / 清空） -->
      <div class="cp-side-section cp-history-card">
        <div class="cp-side-sec-head">
          <span class="cp-side-sec-title" style="margin:0;">历史会话（{{ historyList.length }}）</span>
          <button v-if="historyList.length > 0" class="cp-h-clear" @click="clearAllHistory" title="清空全部">清空</button>
        </div>
        <div v-if="historyList.length === 0" class="cp-side-empty">
          暂无记录，完成任务后自动保存
        </div>
        <div v-else class="cp-side-history-list">
          <button
            v-for="h in historyList.slice(0, 8)"
            :key="h.threadId"
            class="cp-side-history-item"
            :class="{ current: h.threadId === currentThreadId }"
            @click="restoreHistory(h); isSideNavOpen = false"
          >
            <span class="cp-side-hist-title">{{ h.title }}</span>
            <span class="cp-side-hist-time">{{ new Date(h.time).toLocaleDateString() }}</span>
          </button>
        </div>
        <button v-if="historyList.length > 0" class="cp-db-more" @click="isHistoryOpen = true">展开全部 →</button>
      </div>

      <!-- 会话状态 -->
      <div class="cp-side-section cp-conn-card">
        <span class="cp-conn-dot" :class="wsStatus"></span>
        <span class="cp-conn-text">{{ wsStatus === 'open' ? '服务连接正常' : wsStatus === 'connecting' ? '连接中…' : '连接断开，重连中' }}</span>
        <span class="cp-conn-id">#{{ shortThreadId }}</span>
      </div>

      <!-- 底部账号 -->
      <div class="cp-side-foot">
        <div class="cp-avatar">{{ maskedUser.slice(0, 3) }}</div>
        <div class="cp-side-user">
          <div class="cp-side-user-name">{{ maskedUser }}</div>
          <div class="cp-side-user-tag">{{ authInfo?.channel === 'phone' ? '手机验证码登录' : '扫码登录' }}</div>
        </div>
        <button class="cp-side-exit" @click="toggleTheme" :title="'切换到' + sideThemeLabel">
          <svg v-if="theme === 'dark'" width="15" height="15" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="4.5" stroke="currentColor" stroke-width="2"/>
            <path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none">
            <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          </svg>
        </button>
        <button class="cp-side-exit" @click="handleLogout" title="退出登录">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
            <path d="M15 4h4v16h-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M10 8l-4 4 4 4M6 12h9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
    </aside>

    <!-- 移动端侧栏开关 -->
    <button class="cp-side-toggle" @click="isSideNavOpen = !isSideNavOpen" title="菜单">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M4 6H20M4 12H20M4 18H20" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
    </button>

    <!-- 背景光晕装饰 -->
    <div class="cp-bg-deco" aria-hidden="true">
      <div class="cp-blob cp-blob-1"></div>
      <div class="cp-blob cp-blob-2"></div>
      <div class="cp-blob cp-blob-3"></div>
      <div class="cp-grid-lines"></div>
    </div>

    <!-- 品牌条 -->
    <div class="cp-brand-bar">
      <div class="cp-brand-logo">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="#fff" stroke-width="2"/>
          <path d="M15.5 8.5L13.2 13.2L8.5 15.5L10.8 10.8L15.5 8.5Z" fill="#fff"/>
        </svg>
      </div>
      <span class="cp-brand-name">罗盘智能体</span>
      <span class="cp-brand-badge">PHARMA AI AGENT</span>
    </div>

    <!-- 断线重连横幅 -->
    <div v-if="wsStatus !== 'open'" class="cp-ws-banner" :class="wsStatus">
      <span class="cp-ws-dot"></span>
      {{ wsStatus === 'connecting' ? '正在连接服务器…' : '连接已断开，正在自动重连…' }}
    </div>

    <!-- 右上角用户栏：主题 / 历史 / 头像 / 退出 -->
    <div class="cp-user-bar">
      <button class="cp-user-btn cp-theme-btn" @click="toggleTheme" :title="theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'">
        <svg v-if="theme === 'dark'" width="15" height="15" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="4.5" stroke="currentColor" stroke-width="2"/>
          <path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none">
          <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
        </svg>
        {{ theme === 'dark' ? '浅色' : '深色' }}
      </button>
      <button class="cp-user-btn" @click="isHistoryOpen = !isHistoryOpen" title="历史会话">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/>
          <path d="M12 7v5l3.5 2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        历史
      </button>
      <div class="cp-avatar">{{ maskedUser.slice(0, 3) }}</div>
      <button class="cp-user-btn cp-logout" @click="handleLogout" title="退出登录">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
          <path d="M15 4h4v16h-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M10 8l-4 4 4 4M6 12h9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        退出
      </button>
    </div>

    <!-- 历史会话抽屉 -->
    <div v-if="isHistoryOpen" class="cp-history-drawer">
      <div class="cp-history-head">
        <span>历史会话（{{ historyList.length }}）</span>
        <button class="cp-h-close" @click="isHistoryOpen = false">×</button>
      </div>
      <div class="cp-history-list">
        <div v-if="historyList.length === 0" class="cp-history-empty">
          还没有历史记录，完成任务后会自动保存在这里（本地浏览器）。
        </div>
        <div v-for="h in historyList" :key="h.threadId" class="cp-history-item" @click="restoreHistory(h)">
          <div class="cp-history-info">
            <div class="cp-history-title">{{ h.title }}</div>
            <div class="cp-history-time">{{ new Date(h.time).toLocaleString() }} · {{ h.messages.length }} 条消息</div>
          </div>
          <button class="cp-h-del" @click.stop="deleteHistory(h.threadId)" title="删除">🗑</button>
        </div>
      </div>
    </div>

    <!-- 运行中时间线浮条 -->
    <div v-if="status === 'running'" class="cp-timeline">
      <span class="cp-tl-spinner"></span>
      <span class="cp-tl-text">{{ timelineText }}</span>
      <span class="cp-tl-count">已执行 {{ timelineSteps }} 步</span>
    </div>

    <!-- Main Content -->
    <main
      class="main-content"
      :class="{ 'centered-layout': isWelcomeScreen && activeView === 'chat', 'page-mode': activeView !== 'chat' }"
    >
      <!-- ============ 页面一：对话工作台 ============ -->
      <template v-if="activeView === 'chat'">
      <!-- Sidebar Toggle Button -->
      <button 
        v-if="currentSessionPath && !isSidebarOpen" 
        class="sidebar-toggle-btn" 
        @click="isSidebarOpen = true"
        title="Open File Sidebar"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M4 6H20M4 12H20M4 18H20" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>

      <!-- Welcome Screen -->
      <div v-if="isWelcomeScreen" class="welcome-screen">
        <div class="cp-welcome">
          <!-- Hero 区 -->
          <div class="cp-hero">
            <div class="cp-hero-compass">
              <svg width="120" height="120" viewBox="0 0 120 120">
                <defs>
                  <linearGradient id="cpHeroGrad" x1="0" y1="0" x2="120" y2="120" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#2f8a63"/>
                    <stop offset="0.5" stop-color="#3aa878"/>
                    <stop offset="1" stop-color="#c9a45c"/>
                  </linearGradient>
                </defs>
                <circle cx="60" cy="60" r="52" fill="none" stroke="url(#cpHeroGrad)" stroke-width="2" opacity="0.85"/>
                <circle cx="60" cy="60" r="42" fill="none" stroke="url(#cpHeroGrad)" stroke-width="0.8" opacity="0.4" stroke-dasharray="3 5"/>
                <g class="cp-compass-needle">
                  <path d="M60 22L68 60L60 98L52 60Z" fill="url(#cpHeroGrad)" opacity="0.95"/>
                  <circle cx="60" cy="60" r="5" fill="#fff"/>
                </g>
                <g stroke="url(#cpHeroGrad)" stroke-width="1.4" opacity="0.7">
                  <path d="M60 4v10M60 106v10M4 60h10M106 60h10"/>
                </g>
              </svg>
            </div>
            <div class="cp-hero-text">
              <h1 class="cp-hero-title">一句话，问遍<br /><span class="cp-hero-grad">药品 · 库存 · 销售</span></h1>
              <p class="cp-hero-sub">
                三个专家助手协同工作：数据库问答、网络资讯检索、报告一键生成。
                问出好问题，剩下的交给罗盘。
              </p>
              <div class="cp-hero-stats">
                <div class="cp-hstat"><span class="cp-hstat-num">{{ qaCount }}</span><span class="cp-hstat-label">本机累计提问</span></div>
                <div class="cp-hstat-div"></div>
                <div class="cp-hstat"><span class="cp-hstat-num">3</span><span class="cp-hstat-label">专家助手</span></div>
                <div class="cp-hstat-div"></div>
                <div class="cp-hstat"><span class="cp-hstat-num">3 种</span><span class="cp-hstat-label">报告格式</span></div>
                <div class="cp-hstat-div"></div>
                <div class="cp-hstat"><span class="cp-hstat-num">24h</span><span class="cp-hstat-label">在线</span></div>
              </div>
            </div>
          </div>

          <!-- 数据快览（装饰性图表，演示氛围） -->
          <div class="cp-charts">
            <div class="cp-chart-card">
              <div class="cp-chart-head">近 7 日销售趋势</div>
              <svg width="100%" height="46" viewBox="0 0 180 46" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="cpSpark" x1="0" y1="0" x2="0" y2="46" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#2f8a63" stop-opacity="0.5"/>
                    <stop offset="1" stop-color="#2f8a63" stop-opacity="0"/>
                  </linearGradient>
                </defs>
                <path d="M0 38 L26 30 L52 33 L78 20 L104 24 L130 10 L156 14 L180 6 V46 H0 Z" fill="url(#cpSpark)"/>
                <path d="M0 38 L26 30 L52 33 L78 20 L104 24 L130 10 L156 14 L180 6" fill="none" stroke="#c9a45c" stroke-width="2" stroke-linecap="round"/>
                <circle cx="180" cy="6" r="3" fill="#c9a45c"/>
              </svg>
            </div>
            <div class="cp-chart-card">
              <div class="cp-chart-head">库存健康度</div>
              <div class="cp-ring-row">
                <svg width="52" height="52" viewBox="0 0 52 52">
                  <circle cx="26" cy="26" r="21" fill="none" stroke="#235445" stroke-width="6"/>
                  <circle cx="26" cy="26" r="21" fill="none" stroke="#5fd4a0" stroke-width="6" stroke-linecap="round" stroke-dasharray="105 132" transform="rotate(-90 26 26)"/>
                  <text x="26" y="31" text-anchor="middle" fill="#e9f2ec" font-size="13" font-weight="700">80%</text>
                </svg>
                <div class="cp-ring-desc">30 个在售 SKU<br />6 个低库存预警</div>
              </div>
            </div>
            <div class="cp-chart-card">
              <div class="cp-chart-head">本月品类销量</div>
              <div class="cp-bars">
                <div class="cp-bar" style="height: 60%"><i style="background:#2f8a63"></i>抗生素</div>
                <div class="cp-bar" style="height: 85%"><i style="background:#3aa878"></i>解热镇痛</div>
                <div class="cp-bar" style="height: 45%"><i style="background:#c9a45c"></i>心脑血管</div>
                <div class="cp-bar" style="height: 70%"><i style="background:#5fd4a0"></i>消化类</div>
              </div>
            </div>
          </div>

          <!-- 快捷提问 -->
          <div class="cp-quick-grid">
            <button v-for="q in QUICK_PROMPTS" :key="q" class="cp-quick-chip" @click="quickAsk(q)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
              </svg>
              {{ q }}
            </button>
          </div>

          <!-- 欢迎屏历史入口 -->
          <div v-if="historyList.length > 0" class="cp-welcome-history">
            <div class="cp-wh-head">最近任务</div>
            <button v-for="h in historyList.slice(0, 3)" :key="h.threadId" class="cp-wh-item" @click="restoreHistory(h)">
              <span class="cp-wh-title">{{ h.title }}</span>
              <span class="cp-wh-time">{{ new Date(h.time).toLocaleDateString() }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Chat Area -->
      <div v-else class="chat-scroll-area">
        <div class="chat-container">
          <div v-for="(msg, index) in messages" :key="index" class="message-wrapper" :class="msg.role">
            
            <!-- User Message -->
            <div v-if="msg.role === 'user'" class="message-user">
              <div class="msg-content">{{ msg.content }}</div>
            </div>

            <!-- AI Message -->
            <div v-else-if="msg.role === 'ai'" class="message-ai">
              <div class="ai-avatar">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" fill="url(#grad1)"/>
                  <defs>
                    <linearGradient id="grad1" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
                      <stop stop-color="#2f8a63"/>
                      <stop offset="1" stop-color="#c9a45c"/>
                    </linearGradient>
                  </defs>
                </svg>
              </div>
              
              <div class="ai-content-wrapper">
                <!-- Logs / Thinking Process -->
                <div v-if="msg.logs && msg.logs.length > 0" class="process-section">
                  <details>
                    <summary>
                      <span class="spinner" v-if="status === 'running' && index === messages.length - 1"></span>
                      View thought process
                    </summary>
                    <div class="process-steps">
                      <div v-for="(log, idx) in msg.logs" :key="idx" class="step-item">
                        <div class="step-header">
                          <span class="step-icon">🔧</span>
                          <span class="step-title">{{ log.title }}</span>
                        </div>
                        <div class="step-details" v-if="log.details">
                           <pre>{{ JSON.stringify(log.details, null, 2) }}</pre>
                        </div>
                      </div>
                    </div>
                  </details>
                </div>

                <!-- Text Content -->
                <div class="markdown-body" v-html="renderMarkdown(msg.displayContent ?? msg.content)"></div>

                <!-- Files -->
                <div v-if="msg.files && msg.files.length > 0" class="files-grid">
                  <div v-for="file in msg.files" :key="file.name" class="file-card-wrap">
                    <a :href="file.url" target="_blank" class="file-card" :download="file.name">
                      <div class="file-icon">📄</div>
                      <div class="file-info">
                        <div class="file-name">{{ file.name }}</div>
                        <div class="file-type">Document</div>
                      </div>
                    </a>
                    <button class="cp-preview-chip" @click="openPreview(file)" title="在线预览">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                        <path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z" stroke="currentColor" stroke-width="2"/>
                        <circle cx="12" cy="12" r="2.8" stroke="currentColor" stroke-width="2"/>
                      </svg>
                      预览
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- System Message -->
             <div v-else class="message-system">
              {{ msg.content }}
            </div>

          </div>
          <div ref="messagesEndRef" class="spacer-bottom"></div>
        </div>
      </div>

      <!-- Input Area -->
      <footer class="input-footer">
        <!-- File Preview Tab -->
        <div v-if="selectedFiles.length > 0" class="file-preview-container">
          <div v-for="(file, index) in selectedFiles" :key="index" class="file-preview-chip">
            <span class="file-preview-icon">📎</span>
            <span class="file-preview-name">{{ file.name }}</span>
            <button class="file-remove-btn" @click="removeFile(index)" title="Remove file">×</button>
          </div>
        </div>

        <div class="input-container" :class="{ focused: status === 'running' }">
          <input 
            type="file" 
            ref="fileInputRef" 
            multiple
            style="display: none" 
            @change="handleFileChange" 
          />
          <button class="upload-btn" @click="triggerFileUpload" :disabled="status === 'running'" title="Upload file">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <button
            class="upload-btn cp-mic-btn"
            :class="{ recording: isRecording }"
            @click="toggleRecord"
            :disabled="status === 'running'"
            :title="isRecording ? '停止录音' : '语音输入'"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="9" y="2.5" width="6" height="11" rx="3" stroke="currentColor" stroke-width="2"/>
              <path d="M5.5 11a6.5 6.5 0 0 0 13 0" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              <path d="M12 17.5V21M8.5 21h7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
          <textarea 
            v-model="inputQuery" 
            @keydown.enter.exact.prevent="sendMessage"
            placeholder="Enter a prompt here"
            :disabled="status === 'running'"
          ></textarea>
          <button class="send-btn" @click="sendMessage" :disabled="!inputQuery.trim() && status !== 'running'">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"></path>
            </svg>
          </button>
        </div>
        <div class="footer-text">
          DeepAgents may display inaccurate info, including about people, so double-check its responses.
        </div>
      </footer>
      </template>

      <!-- ============ 页面二：数据快览 ============ -->
      <DataView
        v-else-if="activeView === 'data'"
        @ask="askFromPage"
        @open-reports="openReportCenter"
      />

      <!-- ============ 页面三：报告中心 ============ -->
      <ReportCenter
        v-else-if="activeView === 'reports'"
        @ask="askFromPage"
        @open-data="openDataCenter"
        @preview="(f) => { closePreview(); openPreview({ name: f.name, url: f.url }) }"
        @changed="loadReports"
      />

      <!-- ============ 页面四：使用指南 ============ -->
      <GuideView
        v-else-if="activeView === 'guide'"
        @ask="askFromPage"
        @goto="navGo"
      />
    </main>

    <!-- ⑧ 报告在线预览模态框 -->
    <div v-if="previewFile" class="cp-preview-mask cp-preview-top" @click.self="closePreview">
      <div class="cp-preview-modal">
        <div class="cp-preview-head">
          <span class="cp-preview-title">{{ previewFile.name }}</span>
          <div style="display:flex; gap:8px; align-items:center;">
            <a :href="previewFile.url" target="_blank" :download="previewFile.name" class="cp-preview-dl">下载</a>
            <button class="cp-h-close" @click="closePreview">×</button>
          </div>
        </div>
        <div class="cp-preview-body">
          <div v-if="previewLoading" class="cp-preview-loading">加载中…</div>
          <div v-else-if="previewHtml" class="cp-preview-md markdown-body" v-html="previewHtml"></div>
          <iframe v-else :src="previewFile.url" class="cp-preview-frame"></iframe>
        </div>
      </div>
    </div>

    <!-- 三个功能弹层已升级为独立页面：数据快览 / 报告中心 / 使用指南 -->

    <!-- ======== 右侧「本次会话产物」面板 ======== -->
    <aside v-if="isSidebarOpen" class="file-sidebar cp-artifact-panel">
      <div class="cp-art-head">
        <div class="cp-art-head-l">
          <div class="cp-art-title">本次会话产物</div>
          <div class="cp-art-sub">#{{ shortThreadId }} · 罗盘生成的文件会自动出现在这里</div>
        </div>
        <div class="cp-art-head-r">
          <button class="cp-art-icon-btn" @click="fetchFiles" title="刷新">↻</button>
          <button class="cp-art-icon-btn" @click="isSidebarOpen = false" title="关闭">×</button>
        </div>
      </div>

      <!-- 概览统计 -->
      <div class="cp-art-stats">
        <div class="cp-art-stat"><b>{{ fileList.length }}</b><span>文件</span></div>
        <div class="cp-art-stat"><b>{{ fmtSize(sessionFileSize) }}</b><span>合计体积</span></div>
        <div class="cp-art-stat"><b>{{ reportTotal }}</b><span>历史累计</span></div>
      </div>

      <!-- 格式筛选 -->
      <div class="cp-art-filters">
        <button
          v-for="f in SIDE_FILE_FILTERS"
          :key="f.key"
          class="cp-art-chip"
          :class="{ active: sideFileFilter === f.key }"
          @click="sideFileFilter = f.key"
        >{{ f.label }}</button>
      </div>

      <!-- 文件列表 -->
      <div class="cp-art-list">
        <div v-if="fileList.length === 0" class="cp-art-empty">
          <div class="cp-art-empty-ico">
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none">
              <path d="M6 3h9l4 4v14H6V3z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
              <path d="M9 12h7M9 16h5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
            </svg>
          </div>
          <div class="cp-art-empty-t">这次会话还没有生成文件</div>
          <div class="cp-art-empty-d">
            罗盘回答时会自动把 Markdown / Word / PDF / CSV 落到这里。
            直接问一句，或者点下面的示例：
          </div>
          <button
            v-for="h in SIDE_FILE_HINTS"
            :key="h"
            class="cp-art-hint"
            :disabled="status === 'running'"
            @click="sideAskHint(h)"
          >
            <span class="cp-art-hint-dot"></span>{{ h }}
          </button>
          <div class="cp-art-empty-foot">
            产物也会同步汇总到「报告中心」，可按格式筛选、打包 zip 下载。
          </div>
        </div>

        <div v-else-if="sideFileView.length === 0" class="cp-art-empty">
          <div class="cp-art-empty-t">当前筛选下没有文件</div>
          <div class="cp-art-empty-d">换一个格式分类，或点「全部」查看所有产物。</div>
        </div>

        <div
          v-for="file in sideFileView"
          v-else
          :key="file.path"
          class="cp-art-card"
        >
          <span class="cp-rep-tag" :data-ext="sideFileExt(file.name)">{{ extTag(sideFileExt(file.name)) }}</span>
          <div class="cp-art-meta">
            <div class="cp-art-name" :title="file.name">{{ file.name }}</div>
            <div class="cp-art-sub2">{{ fmtSize(file.size) }} · {{ fmtTime(file.mtime) }}</div>
          </div>
          <div class="cp-art-acts">
            <button class="cp-art-mini" @click="openPreview(file)" title="在线预览">预览</button>
            <a class="cp-art-mini" :href="file.url" :download="file.name" title="下载">下载</a>
          </div>
        </div>
      </div>

      <!-- 面板底部 -->
      <div class="cp-art-foot">
        <button class="cp-art-goto" @click="openReportCenter(); isSidebarOpen = false">
          打开报告中心（跨会话汇总）→
        </button>
      </div>
    </aside>
  </div>
</template>

<style>
/* Global Resets & Variables */
:root {
  --bg-dark: #071d16;
  --surface-dark: #0d2b21;
  --surface-light: #143c2e;
  --text-primary: #e9f2ec;
  --text-secondary: #a8c3b4;
  --accent-blue: #dcc489;
  --user-msg-bg: #123a2c; /* Darker gray for user */
  --border-color: #27594a;
}

body {
  margin: 0;
  background-color: var(--bg-dark);
  color: var(--text-primary);
  font-family: 'Google Sans', 'Roboto', Helvetica, Arial, sans-serif;
  overflow: hidden; /* App handles scroll */
}

/* Layout */
.app-container {
  display: flex;
  height: 100vh;
  width: 100vw;
  /* justify-content: center; Removed to allow sidebar layout */
}

/* ===== 左侧导航栏 ===== */
.cp-sidebar {
  width: 236px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 12px 12px;
  background: linear-gradient(180deg, #0e3327 0%, #0a261d 100%);
  border-right: 1px solid #1c4a3a;
  overflow-y: auto;
  z-index: 2600;
}
.cp-side-brand {
  display: flex; align-items: center; gap: 10px;
  padding: 2px 4px 10px;
  border-bottom: 1px solid #1c4a3a;
}
.cp-side-title { font-size: 15px; font-weight: 800; color: #e9f2ec; letter-spacing: 1px; }
.cp-side-sub { font-size: 10px; color: #93b5a7; letter-spacing: 1px; margin-top: 2px; }

.cp-side-nav { display: flex; flex-direction: column; gap: 4px; }
.cp-nav-item {
  display: flex; align-items: center; gap: 9px;
  background: transparent; border: 1px solid transparent;
  color: #a8c3b4; font-size: 12.5px;
  padding: 8px 11px; border-radius: 9px;
  cursor: pointer; transition: all 0.15s;
  text-align: left; width: 100%;
}
.cp-nav-item:hover { background: rgba(58, 168, 120, 0.12); color: #e9f2ec; }
.cp-nav-item.active {
  background: linear-gradient(90deg, rgba(201, 164, 92, 0.16), rgba(201, 164, 92, 0.05));
  border-color: rgba(201, 164, 92, 0.5);
  color: #ecd9a8; font-weight: 700;
}
.cp-nav-new { color: #dcc489; }
.cp-nav-new:hover { color: #ffd166; }

.cp-side-section {
  background: rgba(13, 43, 33, 0.65);
  border: 1px solid #1c4a3a;
  border-radius: 11px;
  padding: 10px;
}
.cp-side-sec-title {
  font-size: 10.5px; color: #93b5a7; letter-spacing: 1.5px;
  margin-bottom: 8px;
}
.cp-db-card .cp-db-row {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12.5px; color: #a8c3b4;
  padding: 4px 0;
}
.cp-db-card .cp-db-row b { color: #ecd9a8; font-size: 13px; }
.cp-db-foot { font-size: 10px; color: #6f9486; margin-top: 8px; letter-spacing: 0.5px; }
.cp-nav-badge {
  margin-left: auto;
  background: linear-gradient(135deg, #c9a45c, #e0c684);
  color: #0d362a; font-size: 10.5px; font-weight: 800;
  border-radius: 999px; padding: 1px 7px;
}
.cp-db-more {
  width: 100%; margin-top: 8px;
  background: rgba(201, 164, 92, 0.1);
  border: 1px dashed rgba(201, 164, 92, 0.5);
  color: #dcc489; font-size: 11.5px;
  border-radius: 8px; padding: 6px 0; cursor: pointer;
  transition: all 0.15s;
}
.cp-db-more:hover { background: rgba(201, 164, 92, 0.2); color: #ffd166; }

/* 侧栏快捷提问 */
.cp-side-quick {
  display: flex; align-items: flex-start; gap: 7px;
  width: 100%; text-align: left;
  background: transparent; border: 1px solid #235445;
  color: #c2d8cd; font-size: 11.5px; line-height: 1.5;
  border-radius: 9px; padding: 7px 9px; margin-bottom: 6px;
  cursor: pointer; transition: all 0.15s;
}
.cp-side-quick svg { flex-shrink: 0; margin-top: 2px; color: #c9a45c; }
.cp-side-quick:hover { border-color: #c9a45c; color: #ecd9a8; background: rgba(201, 164, 92, 0.08); }
.cp-side-quick:disabled { opacity: 0.4; cursor: not-allowed; }

/* 侧栏内嵌历史 */
.cp-side-sec-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.cp-h-clear {
  background: transparent; border: none; color: #6f9486;
  font-size: 10.5px; cursor: pointer; padding: 0;
}
.cp-h-clear:hover { color: #ff6b81; }
.cp-side-empty { font-size: 11.5px; color: #6f9486; line-height: 1.6; }
.cp-side-history-list { display: flex; flex-direction: column; gap: 3px; max-height: 140px; overflow-y: auto; }
.cp-side-history-item {
  display: flex; flex-direction: column; gap: 2px;
  background: transparent; border: 1px solid transparent;
  border-radius: 8px; padding: 6px 8px;
  cursor: pointer; text-align: left; transition: all 0.15s;
}
.cp-side-history-item:hover { background: rgba(58, 168, 120, 0.12); border-color: #235445; }
.cp-side-history-item.current { border-color: rgba(201, 164, 92, 0.5); background: rgba(201, 164, 92, 0.08); }
.cp-side-hist-title {
  font-size: 12px; color: #c2d8cd;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%;
}
.cp-side-hist-time { font-size: 10px; color: #6f9486; }

/* 数据浏览弹层 */
.cp-data-modal { max-width: 900px; width: 92vw; }
.cp-data-body { padding: 14px 18px 18px; overflow: auto; max-height: 74vh; }
.cp-data-tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.cp-data-tab {
  display: flex; align-items: center; gap: 7px;
  background: rgba(13, 43, 33, 0.7); border: 1px solid #235445;
  color: #a8c3b4; font-size: 12.5px;
  border-radius: 9px; padding: 7px 12px; cursor: pointer;
  transition: all 0.15s;
}
.cp-data-tab em {
  font-style: normal; font-size: 11px; font-weight: 800;
  background: rgba(201, 164, 92, 0.18); color: #dcc489;
  border-radius: 999px; padding: 1px 7px;
}
.cp-data-tab.active { border-color: #c9a45c; color: #ecd9a8; background: rgba(201, 164, 92, 0.12); }
.cp-data-grid-wrap { overflow: auto; border: 1px solid #235445; border-radius: 10px; max-height: 52vh; }
.cp-data-grid { border-collapse: collapse; width: 100%; font-size: 12px; }
.cp-data-grid th {
  position: sticky; top: 0;
  background: #123a2c; color: #ecd9a8;
  font-weight: 700; text-align: left;
  padding: 8px 12px; border-bottom: 1px solid #235445;
  white-space: nowrap;
}
.cp-data-grid td {
  color: #c2d8cd; padding: 7px 12px;
  border-bottom: 1px solid rgba(35, 84, 69, 0.5);
  white-space: nowrap;
}
.cp-data-grid tr:hover td { background: rgba(58, 168, 120, 0.08); }
.cp-data-foot { font-size: 11px; color: #6f9486; margin-top: 10px; }

/* ===== 浅色模式：左侧栏整套浅色皮肤 =====
   之前只改了文字颜色、没改侧栏背景，导致深色文字压在深绿底上看不见。 */
body.theme-light .cp-sidebar {
  background: linear-gradient(180deg, #ffffff 0%, #eef3f0 100%);
  border-right-color: #dde5e1;
}
body.theme-light .cp-side-brand { border-bottom-color: #e4ebe8; }
body.theme-light .cp-side-title { color: #12362b; }
body.theme-light .cp-side-sub { color: #7d918a; }

body.theme-light .cp-nav-item { color: #40604f; font-weight: 500; }
body.theme-light .cp-nav-item:hover { background: rgba(47, 138, 99, 0.1); color: #12362b; }
body.theme-light .cp-nav-item.active {
  background: linear-gradient(90deg, rgba(201, 164, 92, 0.26), rgba(201, 164, 92, 0.07));
  border-color: rgba(168, 134, 63, 0.55);
  color: #7d5f14; font-weight: 700;
}
body.theme-light .cp-nav-new { color: #8a6b1f; }
body.theme-light .cp-nav-new:hover { color: #6d5314; }
body.theme-light .cp-nav-badge { background: linear-gradient(135deg, #c9a45c, #e0c684); color: #3a2c08; }

body.theme-light .cp-side-section { background: #ffffff; border-color: #e4ebe8; }
body.theme-light .cp-side-sec-title { color: #7d918a; }
body.theme-light .cp-db-card .cp-db-row { color: #40604f; }
body.theme-light .cp-db-card .cp-db-row b { color: #8a6b1f; }
body.theme-light .cp-db-foot { color: #93a8a0; }
body.theme-light .cp-db-more {
  background: rgba(201, 164, 92, 0.12);
  border-color: rgba(168, 134, 63, 0.5);
  color: #8a6b1f;
}
body.theme-light .cp-db-more:hover { background: rgba(201, 164, 92, 0.22); color: #6d5314; }

body.theme-light .cp-side-quick { color: #2f4c41 !important; border-color: #d5e0da; }
body.theme-light .cp-side-quick:hover { color: #12362b; border-color: #2f8a63; background: #eef6f2; }
body.theme-light .cp-side-quick svg { color: #a8863f; }

body.theme-light .cp-side-empty { color: #7d918a; }
body.theme-light .cp-h-clear { color: #93a8a0; }
body.theme-light .cp-side-history-item:hover { background: #f0f7f3; border-color: #d5e0da; }
body.theme-light .cp-side-history-item.current { border-color: rgba(168, 134, 63, 0.55); background: #faf6ea; }
body.theme-light .cp-side-hist-title { color: #2f4c41; }
body.theme-light .cp-side-hist-time { color: #93a8a0; }

body.theme-light .cp-side-report-item:hover { background: #f0f7f3; border-color: #d5e0da; }
body.theme-light .cp-rep-name { color: #2f4c41; }
body.theme-light .cp-rep-size { color: #93a8a0; }
body.theme-light .cp-conn-text { color: #40604f; }
body.theme-light .cp-conn-id { color: #93a8a0; }
body.theme-light .cp-side-foot { border-top-color: #e4ebe8; }
body.theme-light .cp-side-user-name { color: #12362b; }
body.theme-light .cp-side-user-tag { color: #7d918a; }
body.theme-light .cp-side-exit { border-color: #d5e0da; color: #5c7a6d; }
body.theme-light .cp-side-exit:hover { border-color: #2f8a63; color: #12362b; }
body.theme-light .cp-side-toggle { background: rgba(255, 255, 255, 0.95); border-color: #d5e0da; color: #40604f; }

/* 用户气泡：底色始终是深绿→金渐变，文字必须保持亮色 */
.message-user .msg-content { color: #f2fbf6 !important; }

/* ==================================================================
   独立页面通用样式（数据快览 / 报告中心 / 使用指南 三个子组件共用）
   统一走 --cp-* 变量，深浅主题自动切换，不再各写一份
   ================================================================== */
:root {
  --cp-bg: #071d16;
  --cp-surface: #0d2b21;
  --cp-surface-2: #123a2c;
  --cp-surface-3: #164535;
  --cp-border: #1d4a3b;
  --cp-border-2: #27594a;
  --cp-text: #eaf3ee;
  --cp-text-2: #b3ccbe;
  --cp-text-3: #86a596;
  --cp-gold: #dcc489;
  --cp-gold-strong: #ffd166;
  --cp-green: #3aa878;
  --cp-red: #ff9c9c;
  --cp-blue: #9dc0ff;
  --cp-shadow: 0 12px 34px rgba(0, 0, 0, 0.32);
}
body.theme-light {
  --cp-bg: #f3f4f9;
  --cp-surface: #ffffff;
  --cp-surface-2: #f5f8f6;
  --cp-surface-3: #eaf1ed;
  --cp-border: #e0e7e4;
  --cp-border-2: #cfdcd6;
  --cp-text: #113326;
  --cp-text-2: #436053;
  --cp-text-3: #7d918a;
  --cp-gold: #8a6b1f;
  --cp-gold-strong: #6d5314;
  --cp-green: #2f8a63;
  --cp-red: #c5394a;
  --cp-blue: #2f5fbe;
  --cp-shadow: 0 10px 30px rgba(18, 54, 43, 0.1);
}

.page-mode { overflow-y: auto; display: block; }
/* 顶部让位已由 .main-content 的 padding-top 统一处理，这里只补一点呼吸感 */
.page-mode .cp-page { padding-top: 8px; }

.cp-page {
  min-height: 100%;
  padding: 26px 30px 40px;
  color: var(--cp-text);
  box-sizing: border-box;
}
.cp-page-head {
  display: flex; align-items: flex-start; gap: 16px;
  margin-bottom: 20px; flex-wrap: wrap;
}
.cp-page-title { font-size: 22px; font-weight: 800; letter-spacing: 0.5px; color: var(--cp-text); margin: 0; }
.cp-page-desc { font-size: 13px; color: var(--cp-text-3); margin-top: 6px; line-height: 1.7; max-width: 720px; }
.cp-page-head-acts { margin-left: auto; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.cp-btn {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--cp-surface-2); border: 1px solid var(--cp-border-2);
  color: var(--cp-text-2); font-size: 12.5px; font-weight: 600;
  border-radius: 9px; padding: 8px 14px; cursor: pointer;
  transition: all 0.15s; white-space: nowrap; text-decoration: none;
}
.cp-btn:hover { border-color: var(--cp-green); color: var(--cp-text); }
.cp-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.cp-btn-primary {
  background: linear-gradient(135deg, #2f8a63, #3aa878);
  border-color: #46b98a; color: #f2fff9;
}
.cp-btn-primary:not(:disabled):hover { filter: brightness(1.1); color: #fff; }
.cp-btn-gold {
  background: linear-gradient(135deg, #c9a45c, #e0c684);
  border-color: #e0c684; color: #3a2c08;
}
.cp-btn-gold:not(:disabled):hover { filter: brightness(1.06); }
.cp-btn-danger { border-color: rgba(226, 92, 92, 0.55); color: var(--cp-red); }
.cp-btn-danger:not(:disabled):hover { background: rgba(226, 92, 92, 0.14); border-color: #e25c5c; }
.cp-btn-sm { padding: 5px 11px; font-size: 11.5px; border-radius: 7px; }

.cp-card {
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 14px;
  padding: 16px;
}
.cp-card-title {
  font-size: 13.5px; font-weight: 700; color: var(--cp-text);
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
}
.cp-card-title .cp-mini-tag {
  font-size: 10px; font-weight: 700; letter-spacing: 0.5px;
  background: rgba(201, 164, 92, 0.16); color: var(--cp-gold);
  border: 1px solid rgba(201, 164, 92, 0.35);
  border-radius: 999px; padding: 1px 8px;
}

.cp-grid { display: grid; gap: 14px; }
.cp-grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.cp-grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.cp-grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }

.cp-stat-card {
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 14px; padding: 14px 16px;
  display: flex; flex-direction: column; gap: 4px;
  position: relative; overflow: hidden;
}
.cp-stat-card::after {
  content: ''; position: absolute; inset: 0 0 auto 0; height: 3px;
  background: linear-gradient(90deg, #2f8a63, #3aa878, #c9a45c);
  opacity: 0.75;
}
.cp-stat-val { font-size: 24px; font-weight: 800; color: var(--cp-gold); letter-spacing: 0.5px; }
.cp-stat-label { font-size: 12px; color: var(--cp-text-3); }
.cp-stat-hint { font-size: 11px; color: var(--cp-text-3); opacity: 0.85; margin-top: 2px; }

.cp-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; padding: 40px 20px; text-align: center;
  color: var(--cp-text-3); font-size: 13px; line-height: 1.8;
}
.cp-empty-ico { color: var(--cp-border-2); }

.cp-divider { height: 1px; background: var(--cp-border); margin: 18px 0; }

/* 报告中心文件行（App.vue 侧栏与 ReportCenter 页共用） */
.cp-rep-row {
  display: flex; align-items: center; gap: 10px;
  background: var(--cp-surface-2);
  border: 1px solid var(--cp-border); border-radius: 10px;
  padding: 9px 12px; transition: all 0.15s;
}
.cp-rep-row:hover { border-color: var(--cp-green); }
.cp-rep-row.sel { border-color: #c9a45c; background: rgba(201, 164, 92, 0.1); }
.cp-rep-checkbox {
  width: 15px; height: 15px; border-radius: 4px; flex-shrink: 0;
  border: 1.5px solid var(--cp-border-2); cursor: pointer; position: relative;
  transition: all 0.15s; background: transparent;
}
.cp-rep-checkbox:hover { border-color: #c9a45c; }
.cp-rep-checkbox.on { background: #3aa878; border-color: #3aa878; }
.cp-rep-checkbox.on::after {
  content: ''; position: absolute; left: 4.5px; top: 1.5px;
  width: 4px; height: 8px;
  border: solid #08110d; border-width: 0 2px 2px 0; transform: rotate(45deg);
}
.cp-rep-meta { flex: 1; min-width: 0; cursor: pointer; }
.cp-rep-fname {
  font-size: 13px; color: var(--cp-text); font-weight: 600;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cp-rep-fsub { font-size: 10.5px; color: var(--cp-text-3); margin-top: 2px; }
.cp-rep-row-act { display: flex; gap: 6px; flex-shrink: 0; }
.cp-rep-mini {
  background: transparent; border: 1px solid var(--cp-border-2); color: var(--cp-text-2);
  font-size: 11px; border-radius: 7px; padding: 4px 10px; cursor: pointer;
  transition: all 0.15s; text-decoration: none;
}
.cp-rep-mini:hover { border-color: #c9a45c; color: var(--cp-gold); }
.cp-rep-mini-del:hover { border-color: #e25c5c; color: var(--cp-red); }

/* 侧栏「最近报告」 */
.cp-side-report-list { display: flex; flex-direction: column; gap: 3px; margin-bottom: 2px; }
.cp-side-report-item {
  display: flex; align-items: center; gap: 7px;
  background: transparent; border: 1px solid transparent;
  border-radius: 8px; padding: 6px 8px;
  cursor: pointer; text-align: left; transition: all 0.15s; width: 100%;
}
.cp-side-report-item:hover { background: rgba(58, 168, 120, 0.12); border-color: var(--cp-border-2); }
.cp-rep-name {
  flex: 1; min-width: 0; font-size: 11.5px; color: var(--cp-text-2);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cp-rep-size { font-size: 10px; color: var(--cp-text-3); flex-shrink: 0; }

/* 文件类型标签（按后缀着色） */
.cp-rep-tag {
  flex-shrink: 0;
  font-size: 9.5px; font-weight: 800; letter-spacing: 0.4px;
  border-radius: 5px; padding: 2px 5px; line-height: 1.3;
  background: rgba(58, 168, 120, 0.16); color: #7fd8ac;
  border: 1px solid rgba(58, 168, 120, 0.35);
}
.cp-rep-tag[data-ext="pdf"] { background: rgba(226, 92, 92, 0.16); color: #ff9c9c; border-color: rgba(226, 92, 92, 0.4); }
.cp-rep-tag[data-ext="docx"], .cp-rep-tag[data-ext="doc"] { background: rgba(74, 132, 226, 0.18); color: #9dc0ff; border-color: rgba(74, 132, 226, 0.42); }
.cp-rep-tag[data-ext="csv"], .cp-rep-tag[data-ext="xlsx"], .cp-rep-tag[data-ext="xls"] { background: rgba(52, 162, 122, 0.18); color: #86e0b6; border-color: rgba(52, 162, 122, 0.42); }
.cp-rep-tag[data-ext="png"], .cp-rep-tag[data-ext="jpg"], .cp-rep-tag[data-ext="jpeg"], .cp-rep-tag[data-ext="svg"], .cp-rep-tag[data-ext="gif"] { background: rgba(201, 164, 92, 0.18); color: #e7c977; border-color: rgba(201, 164, 92, 0.45); }
body.theme-light .cp-rep-tag { color: #1f7a52; background: #e8f5ee; border-color: #b9e0cd; }
body.theme-light .cp-rep-tag[data-ext="pdf"] { color: #b8323f; background: #fdecee; border-color: #f2c2c8; }
body.theme-light .cp-rep-tag[data-ext="docx"],
body.theme-light .cp-rep-tag[data-ext="doc"] { color: #2f5fbe; background: #ebf1fd; border-color: #c3d5f7; }
body.theme-light .cp-rep-tag[data-ext="csv"],
body.theme-light .cp-rep-tag[data-ext="xlsx"],
body.theme-light .cp-rep-tag[data-ext="xls"] { color: #1f7a52; background: #e8f5ee; border-color: #b9e0cd; }
body.theme-light .cp-rep-tag[data-ext="png"],
body.theme-light .cp-rep-tag[data-ext="jpg"],
body.theme-light .cp-rep-tag[data-ext="jpeg"],
body.theme-light .cp-rep-tag[data-ext="svg"],
body.theme-light .cp-rep-tag[data-ext="gif"] { color: #8a6b1f; background: #faf3e2; border-color: #e8d6a8; }

/* ===== 右侧「本次会话产物」面板 ===== */
/* 与 .main-content 保持一致的顶部让位，避免固定用户栏压住面板标题 */
.cp-artifact-panel { width: 340px; padding-top: 58px; }
.cp-art-head {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 14px 16px 12px;
  border-bottom: 1px solid var(--cp-border, #27594a);
}
.cp-art-head-l { flex: 1; min-width: 0; }
.cp-art-title { font-size: 14.5px; font-weight: 800; color: var(--cp-text, #eaf3ee); }
.cp-art-sub { font-size: 10.5px; color: var(--cp-text-3, #86a596); margin-top: 3px; line-height: 1.5; }
.cp-art-head-r { display: flex; gap: 6px; flex-shrink: 0; }
.cp-art-icon-btn {
  width: 26px; height: 26px; border-radius: 8px;
  background: transparent; border: 1px solid var(--cp-border, #27594a);
  color: var(--cp-text-2, #b3ccbe); cursor: pointer; font-size: 14px; line-height: 1;
  display: flex; align-items: center; justify-content: center;
}
.cp-art-icon-btn:hover { border-color: #c9a45c; color: var(--cp-gold, #dcc489); }

.cp-art-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding: 12px 16px 10px; }
.cp-art-stat {
  background: var(--cp-surface-2, #123a2c);
  border: 1px solid var(--cp-border, #1d4a3b);
  border-radius: 10px; padding: 8px 10px;
  display: flex; flex-direction: column; gap: 2px;
}
.cp-art-stat b { font-size: 15px; color: var(--cp-gold, #dcc489); font-weight: 800; }
.cp-art-stat span { font-size: 10px; color: var(--cp-text-3, #86a596); }

.cp-art-filters { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 16px 12px; }
.cp-art-chip {
  background: var(--cp-surface-2, #123a2c);
  border: 1px solid var(--cp-border, #1d4a3b);
  color: var(--cp-text-2, #b3ccbe);
  font-size: 11px; border-radius: 999px; padding: 4px 10px; cursor: pointer;
  transition: all 0.15s;
}
.cp-art-chip:hover { border-color: #c9a45c; color: var(--cp-gold, #dcc489); }
.cp-art-chip.active { background: rgba(201, 164, 92, 0.2); border-color: #c9a45c; color: var(--cp-gold-strong, #ffd166); font-weight: 700; }

.cp-art-list { flex: 1; overflow-y: auto; padding: 0 16px 12px; display: flex; flex-direction: column; gap: 8px; }
.cp-art-card {
  display: flex; align-items: center; gap: 9px;
  background: var(--cp-surface-2, #123a2c);
  border: 1px solid var(--cp-border, #1d4a3b);
  border-radius: 11px; padding: 9px 11px; transition: all 0.15s;
}
.cp-art-card:hover { border-color: var(--cp-green, #3aa878); }
.cp-art-meta { flex: 1; min-width: 0; }
.cp-art-name {
  font-size: 12.5px; font-weight: 600; color: var(--cp-text, #eaf3ee);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cp-art-sub2 { font-size: 10px; color: var(--cp-text-3, #86a596); margin-top: 2px; }
.cp-art-acts { display: flex; gap: 5px; flex-shrink: 0; }
.cp-art-mini {
  background: transparent; border: 1px solid var(--cp-border-2, #27594a);
  color: var(--cp-text-2, #b3ccbe); font-size: 10.5px;
  border-radius: 7px; padding: 4px 9px; cursor: pointer;
  transition: all 0.15s; text-decoration: none; line-height: 1.4;
}
.cp-art-mini:hover { border-color: #c9a45c; color: var(--cp-gold, #dcc489); }

.cp-art-empty { display: flex; flex-direction: column; align-items: flex-start; gap: 9px; padding: 18px 2px 8px; }
.cp-art-empty-ico {
  align-self: center; color: var(--cp-border-2, #27594a);
  background: var(--cp-surface-2, #123a2c);
  border: 1px dashed var(--cp-border-2, #27594a);
  border-radius: 14px; width: 62px; height: 62px;
  display: flex; align-items: center; justify-content: center;
}
.cp-art-empty-t { font-size: 13px; font-weight: 700; color: var(--cp-text, #eaf3ee); align-self: center; }
.cp-art-empty-d { font-size: 11.5px; color: var(--cp-text-3, #86a596); line-height: 1.75; }
.cp-art-hint {
  display: flex; align-items: center; gap: 8px; width: 100%;
  background: var(--cp-surface-2, #123a2c);
  border: 1px solid var(--cp-border, #1d4a3b);
  color: var(--cp-text-2, #b3ccbe);
  font-size: 11.5px; text-align: left;
  border-radius: 9px; padding: 8px 10px; cursor: pointer; transition: all 0.15s;
}
.cp-art-hint:hover { border-color: #c9a45c; color: var(--cp-gold, #dcc489); }
.cp-art-hint:disabled { opacity: 0.4; cursor: not-allowed; }
.cp-art-hint-dot {
  width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, #3aa878, #c9a45c);
}
.cp-art-empty-foot {
  font-size: 10.5px; color: var(--cp-text-3, #86a596);
  line-height: 1.7; border-top: 1px dashed var(--cp-border-2, #27594a);
  padding-top: 9px; width: 100%;
}
.cp-art-foot { padding: 12px 16px; border-top: 1px solid var(--cp-border, #27594a); }
.cp-art-goto {
  width: 100%; background: rgba(201, 164, 92, 0.12);
  border: 1px dashed rgba(201, 164, 92, 0.5);
  color: var(--cp-gold, #dcc489); font-size: 12px; font-weight: 600;
  border-radius: 9px; padding: 9px 0; cursor: pointer; transition: all 0.15s;
}
.cp-art-goto:hover { background: rgba(201, 164, 92, 0.22); color: var(--cp-gold-strong, #ffd166); }

.cp-conn-card {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
}
.cp-conn-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  background: #5fd4a0;
  box-shadow: 0 0 8px rgba(95, 212, 160, 0.7);
}
.cp-conn-dot.connecting { background: #ffd166; box-shadow: 0 0 8px rgba(255, 209, 102, 0.7); animation: cp-blink 1.2s ease-in-out infinite; }
.cp-conn-dot.closed { background: #ff6b81; box-shadow: 0 0 8px rgba(255, 107, 129, 0.7); }
.cp-conn-text { font-size: 12px; color: #a8c3b4; flex: 1; }
.cp-conn-id { font-size: 10.5px; color: #6f9486; font-family: monospace; }

.cp-side-foot {
  margin-top: auto;
  display: flex; align-items: center; gap: 10px;
  padding: 12px 10px 4px;
  border-top: 1px solid #1c4a3a;
}
.cp-side-user { flex: 1; min-width: 0; }
.cp-side-user-name { font-size: 13px; font-weight: 700; color: #e9f2ec; }
.cp-side-user-tag { font-size: 10.5px; color: #6f9486; margin-top: 2px; }
.cp-side-exit {
  background: transparent; border: 1px solid #235445;
  color: #a8c3b4; border-radius: 9px;
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s;
}
.cp-side-exit:hover { border-color: #ff6b81; color: #ff6b81; }

.cp-side-mask {
  display: none;
  position: fixed; inset: 0;
  background: rgba(4, 15, 11, 0.6);
  z-index: 2550;
}
.cp-side-toggle { display: none; }

/* 使用指南 */
.cp-guide-modal { max-width: 560px; }
.cp-guide-body { display: flex; flex-direction: column; gap: 14px; }
.cp-guide-item { display: flex; gap: 12px; align-items: flex-start; }
.cp-guide-ico { font-size: 20px; flex-shrink: 0; }
.cp-guide-t { font-size: 14px; font-weight: 700; color: #e9f2ec; }
.cp-guide-d { font-size: 12.5px; color: #a8c3b4; line-height: 1.7; margin-top: 3px; }
.cp-guide-note {
  font-size: 11.5px; color: #6f9486;
  border-top: 1px dashed #235445; padding-top: 10px;
}
body.theme-light .cp-guide-t { color: #1a1c24; }
body.theme-light .cp-guide-d { color: #5c6070; }
body.theme-light .cp-guide-note { color: #8a8fa3; border-top-color: #d9dce7; }

@media (max-width: 900px) {
  .cp-sidebar {
    position: fixed; top: 0; left: 0; bottom: 0;
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    box-shadow: 8px 0 30px rgba(4, 15, 11, 0.5);
  }
  .cp-sidebar.open { transform: translateX(0); }
  .cp-side-mask { display: none; }
  .cp-side-mask.open { display: block; }
  .cp-side-toggle {
    display: flex; align-items: center; justify-content: center;
    position: fixed; top: 14px; left: 14px; z-index: 2600;
    width: 38px; height: 38px; border-radius: 10px;
    background: rgba(13, 43, 33, 0.9); border: 1px solid #235445;
    color: #c2d8cd; cursor: pointer;
  }
  .cp-brand-bar { left: 64px; }
}
@media (min-width: 901px) {
  .cp-brand-bar { left: 258px; }
}

/* Main Content */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  background-color: var(--bg-dark);
  min-width: 0; /* Prevent flex overflow */
  /* 固定右上角用户栏（主题/历史/退出）浮在内容之上，这里统一让出顶部空间，
     否则首条消息气泡、右侧产物面板标题、独立页面页头都会被压住 */
  padding-top: 58px;
  box-sizing: border-box;
}

.sidebar-toggle-btn {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  z-index: 10;
  padding: 8px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.sidebar-toggle-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary);
}

/* File Sidebar */
.file-sidebar {
  width: 300px;
  background-color: var(--surface-dark);
  border-left: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 1rem;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 500;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 1.5rem;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: var(--text-primary);
}

.file-list {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

.empty-files {
  color: var(--text-secondary);
  text-align: center;
  font-size: 0.9rem;
  margin-top: 2rem;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.file-link {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  border-radius: 8px;
  color: var(--text-primary);
  text-decoration: none;
  transition: background 0.2s;
  border: 1px solid transparent;
}

.file-link:hover {
  background: #123a2c;
  border-color: #2a5c4b;
}

.folder-btn {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.folder-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary);
  border-color: var(--text-secondary);
}

.file-name-text {
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Welcome Screen */
.welcome-screen {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 2rem;
}

/* Centered Layout Mode (Initial State) */
.main-content.centered-layout {
  justify-content: center;
  align-items: center;
  overflow-y: auto;
}

.main-content.centered-layout .welcome-screen {
  flex: 0 0 auto;
  padding-bottom: 2rem;
}

.main-content.centered-layout .input-footer {
  width: 100%;
  max-width: 100%;
  padding: 0;
  background: transparent;
  justify-content: center;
}

.welcome-text {
  text-align: center;
  margin-bottom: 2rem;
}

.welcome-text h1 {
  font-size: 3.5rem;
  background: linear-gradient(90deg, #2f8a63, #c9a45c);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin: 0;
  line-height: 1.2;
}

.welcome-text h2 {
  font-size: 3.5rem;
  color: #27594a;
  margin: 0;
  line-height: 1.2;
}

/* Chat Area */
.chat-scroll-area {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

.chat-container {
  max-width: 800px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.message-wrapper {
  display: flex;
  flex-direction: column;
  width: 100%;
}

/* User Message */
.message-user {
  align-self: flex-end;
  max-width: 70%;
}

.msg-content {
  background-color: var(--user-msg-bg);
  padding: 12px 18px;
  border-radius: 18px;
  border-bottom-right-radius: 4px;
  line-height: 1.6;
}

/* AI Message */
.message-ai {
  align-self: flex-start;
  width: 100%;
  display: flex;
  gap: 1rem;
}

.ai-avatar {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  margin-top: 4px;
}

.ai-content-wrapper {
  flex: 1;
  min-width: 0; /* Text wrap fix */
}

.markdown-body {
  line-height: 1.6;
  font-size: 1rem;
}

.markdown-body pre {
  background: #123a2c;
  padding: 1rem;
  border-radius: 8px;
  overflow-x: auto;
}

.typing-indicator {
  color: var(--text-secondary);
  font-style: italic;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% { opacity: 0.5; }
  50% { opacity: 1; }
  100% { opacity: 0.5; }
}

/* Process / Logs */
.process-section {
  margin-bottom: 1rem;
}

.process-section summary {
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 0.85rem;
  list-style: none; /* Hide default arrow */
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-radius: 4px;
}

.process-section summary:hover {
  background: #123a2c;
}

.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--text-secondary);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.process-steps {
  background: #0d2b21;
  border-radius: 8px;
  padding: 0.5rem;
  margin-top: 0.5rem;
  border: 1px solid #1f4d3d;
}

.step-item {
  padding: 0.5rem;
  border-left: 2px solid #1f4d3d;
  margin-left: 0.5rem;
  margin-bottom: 0.5rem;
}

.step-header {
  font-size: 0.85rem;
  font-weight: 500;
  color: #e9f2ec;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.step-details pre {
  margin: 0.5rem 0 0 0;
  font-size: 0.75rem;
  color: #8fb3a4;
  background: #051510;
  padding: 0.5rem;
  border-radius: 4px;
  overflow-x: auto;
}

/* Files Grid */
.files-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1rem;
}

.file-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: #123a2c;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  text-decoration: none;
  color: var(--text-primary);
  border: 1px solid #2a5c4b;
  transition: all 0.2s;
  min-width: 150px;
}

.file-card:hover {
  background: #333537;
  border-color: #6f9486;
}

.file-info {
  display: flex;
  flex-direction: column;
}

.file-name {
  font-weight: 500;
  font-size: 0.9rem;
}

.file-type {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

/* System Message */
.message-system {
  text-align: center;
  font-size: 0.8rem;
  color: #6f9486;
  margin: 1rem 0;
}

.spacer-bottom { height: 100px; }

/* Input Footer */
.input-footer {
  background: var(--bg-dark); /* Ensure it covers scrolling content */
  padding: 1rem 2rem 2rem 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.input-container {
  width: 100%;
  max-width: 800px;
  background: #0d2b21;
  border-radius: 32px;
  display: flex;
  align-items: center;
  padding: 0.5rem 1rem;
  transition: background 0.2s;
}

.input-container.focused {
  background: #123a2c;
}

textarea {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 1rem;
  padding: 10px;
  resize: none;
  height: 24px;
  max-height: 200px;
  font-family: inherit;
  outline: none;
}

.send-btn {
  background: none;
  border: none;
  color: var(--text-primary); /* White when active */
  cursor: pointer;
  padding: 8px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.send-btn:disabled {
  color: #27594a;
  cursor: default;
}

.send-btn:not(:disabled):hover {
  background: #1a4636;
}

.upload-btn {
  background: none;
  border: none;
  color: var(--text-primary);
  cursor: pointer;
  padding: 8px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 4px;
}

.upload-btn:hover {
  background: #1a4636;
}

.upload-btn:disabled {
  color: #27594a;
  cursor: default;
}

.footer-text {
  font-size: 0.75rem;
  color: #27594a;
  text-align: center;
}

/* File Preview Styles */
.file-preview-container {
  width: 100%;
  max-width: 800px;
  display: flex;
  justify-content: flex-start;
  padding-left: 1rem;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.file-preview-chip {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #123a2c;
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  border: 1px solid #2a5c4b;
  font-size: 0.9rem;
  color: var(--text-primary);
  animation: slideUp 0.2s ease-out;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.file-preview-icon {
  font-size: 1rem;
}

.file-preview-name {
  max-width: 200px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-remove-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 1.1rem;
  padding: 0 4px;
  line-height: 1;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-remove-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #ff6b6b;
}

/* Scrollbar Styles */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #2a5c4b;
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: #3a705e;
}

/* ================= 增强功能样式（cp- 前缀） ================= */

/* 断线重连横幅 */
.cp-ws-banner {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 3000;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 8px 16px;
  font-size: 13px;
  color: #ffd166;
  background: rgba(60, 45, 10, 0.92);
  border-bottom: 1px solid rgba(255, 209, 102, 0.3);
  backdrop-filter: blur(6px);
}
.cp-ws-banner.connecting { color: #8fb8ff; background: rgba(20, 40, 80, 0.92); border-bottom-color: rgba(143, 184, 255, 0.3); }
.cp-ws-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: currentColor;
  animation: cp-blink 1.2s ease-in-out infinite;
}
@keyframes cp-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }

/* 右上角用户栏 */
.cp-user-bar {
  position: fixed;
  top: 16px; right: 20px;
  z-index: 2500;
  display: flex; align-items: center; gap: 8px;
}
.cp-user-btn {
  display: flex; align-items: center; gap: 6px;
  background: rgba(13, 43, 33, 0.85);
  border: 1px solid #235445;
  color: #c2d8cd;
  font-size: 13px;
  border-radius: 999px;
  padding: 7px 14px;
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: all 0.15s;
}
.cp-user-btn:hover { border-color: #2f8a63; color: #fff; }
.cp-logout:hover { border-color: #ff6b81; color: #ff6b81; }
.cp-avatar {
  width: 34px; height: 34px; border-radius: 50%;
  background: linear-gradient(135deg, #2f8a63, #c9a45c);
  color: #fff; font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 12px rgba(58, 168, 120, 0.4);
}

/* 历史会话抽屉 */
.cp-history-drawer {
  position: fixed;
  top: 60px; right: 20px;
  z-index: 2600;
  width: 360px; max-width: calc(100vw - 32px);
  max-height: 70vh;
  background: #0b241c;
  border: 1px solid #1d4a3a;
  border-radius: 16px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.cp-history-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px;
  font-size: 14px; font-weight: 700; color: #e9f2ec;
  border-bottom: 1px solid #16382c;
}
.cp-h-close {
  background: none; border: none; color: #86a89a;
  font-size: 20px; cursor: pointer; line-height: 1;
}
.cp-h-close:hover { color: #fff; }
.cp-history-list { overflow-y: auto; padding: 8px; }
.cp-history-empty {
  padding: 28px 16px; text-align: center;
  color: #6f9486; font-size: 12.5px; line-height: 1.8;
}
.cp-history-item {
  display: flex; align-items: center; gap: 8px;
  padding: 11px 12px; border-radius: 10px;
  cursor: pointer;
  transition: background 0.12s;
}
.cp-history-item:hover { background: #11332a; }
.cp-history-info { flex: 1; min-width: 0; }
.cp-history-title {
  font-size: 13px; color: #dcebe2;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cp-history-time { font-size: 11px; color: #6f9486; margin-top: 3px; }
.cp-h-del {
  background: none; border: none; cursor: pointer;
  font-size: 14px; opacity: 0; transition: opacity 0.12s;
}
.cp-history-item:hover .cp-h-del { opacity: 0.7; }
.cp-h-del:hover { opacity: 1 !important; }

/* 运行中时间线浮条 */
.cp-timeline {
  position: fixed;
  top: 18px; left: 50%; transform: translateX(-50%);
  z-index: 2400;
  display: flex; align-items: center; gap: 10px;
  background: rgba(11, 36, 28, 0.92);
  border: 1px solid #2a5c4b;
  border-radius: 999px;
  padding: 9px 18px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(8px);
  max-width: min(640px, calc(100vw - 200px));
}
.cp-tl-spinner {
  width: 14px; height: 14px; flex-shrink: 0;
  border: 2px solid #2a5c4b;
  border-top-color: #2f8a63;
  border-radius: 50%;
  animation: cp-spin 0.8s linear infinite;
}
@keyframes cp-spin { to { transform: rotate(360deg); } }
.cp-tl-text {
  font-size: 13px; color: #dcebe2;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cp-tl-count {
  font-size: 11.5px; color: #86a89a; flex-shrink: 0;
  background: #11332a; border-radius: 999px; padding: 3px 9px;
}

/* 快捷提问模板 */
.cp-quick-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  width: min(560px, 90%);
  margin-top: 28px;
}
.cp-quick-chip {
  display: flex; align-items: center; gap: 9px;
  background: rgba(13, 43, 33, 0.75);
  border: 1px solid #1e4a3a;
  color: #c2d8cd;
  font-size: 13px;
  text-align: left;
  border-radius: 12px;
  padding: 13px 15px;
  cursor: pointer;
  transition: all 0.15s;
}
.cp-quick-chip svg { color: #c9a45c; flex-shrink: 0; }
.cp-quick-chip:hover {
  border-color: #2f8a63;
  color: #fff;
  background: rgba(58, 168, 120, 0.12);
  transform: translateY(-1px);
}

/* 欢迎屏最近任务 */
.cp-welcome-history {
  width: min(560px, 90%);
  margin-top: 22px;
}
.cp-wh-head {
  font-size: 12px; color: #6f9486;
  margin-bottom: 8px; padding-left: 4px;
  letter-spacing: 1px;
}
.cp-wh-item {
  width: 100%;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  background: transparent;
  border: none;
  border-bottom: 1px solid #123026;
  color: #a8c3b4;
  font-size: 13px;
  padding: 10px 4px;
  cursor: pointer;
  transition: color 0.12s;
}
.cp-wh-item:hover { color: #fff; }
.cp-wh-title {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cp-wh-time { font-size: 11.5px; color: #55506a; flex-shrink: 0; }

@media (max-width: 700px) {
  .cp-quick-grid { grid-template-columns: 1fr; }
  .cp-timeline { max-width: calc(100vw - 32px); top: 60px; }
  .cp-user-bar { top: 12px; right: 12px; }
}

/* ================= ⑨ 深浅主题 ================= */
body.theme-light {
  --bg-dark: #f3f4f9;
  --surface-dark: #ffffff;
  --surface-light: #e9ebf3;
  --text-primary: #1a1c24;
  --text-secondary: #5c6070;
  --accent-blue: #3b6ef6;
  --user-msg-bg: #e4e9ff;
  --border-color: #d9dce7;
}
/* 硬编码深色的容器在浅色主题下覆盖 */
body.theme-light .markdown-body pre { background: #f0f1f7; color: #2a2c36; }
body.theme-light .process-steps { background: #f6f7fb; }
body.theme-light .step-details pre { background: #e8eaf2; color: #333; }
body.theme-light .file-card { background: #ffffff; border-color: #d9dce7; }
body.theme-light .file-card:hover { background: #eef1fb; }
body.theme-light .file-link:hover { background: #eef1fb; }
body.theme-light .input-container { background: #ffffff; border-color: #d9dce7; }
body.theme-light .input-container.focused { background: #ffffff; }
body.theme-light .file-preview-chip { background: #eef1fb; }
body.theme-light .process-section summary:hover { background: #eef1fb; }
body.theme-light .markdown-body { color: #262933; }
body.theme-light .markdown-body code { background: #eceef6; color: #c7254e; }
body.theme-light .markdown-body a { color: #3b6ef6; }
body.theme-light .send-btn:not(:disabled):hover,
body.theme-light .upload-btn:hover { background: #e4e8f5; }
body.theme-light .welcome-text h1 { color: #1a1c24; }
body.theme-light .welcome-text h2 { color: #6a6f80; }
body.theme-light .footer-text { color: #9aa0b2; }
body.theme-light .cp-user-btn { background: rgba(255,255,255,0.9); border-color: #d9dce7; color: #4c5064; }
body.theme-light .cp-user-btn:hover { border-color: #2f8a63; color: #1a1c24; }
body.theme-light .cp-timeline { background: rgba(255,255,255,0.95); border-color: #d9dce7; }
body.theme-light .cp-tl-text { color: #33364a; }
body.theme-light .cp-tl-count { background: #eef1fb; color: #5c6070; }
body.theme-light .cp-history-drawer { background: #ffffff; border-color: #d9dce7; }
body.theme-light .cp-history-title { color: #262933; }
body.theme-light .cp-history-item:hover { background: #eef1fb; }
body.theme-light .cp-quick-chip { background: #ffffff; border-color: #d9dce7; color: #4c5064; }
body.theme-light .cp-quick-chip:hover { border-color: #2f8a63; color: #1a1c24; background: #eef4ff; }
body.theme-light .cp-quick-chip svg { color: #2f8a63; }
body.theme-light .cp-wh-item { color: #5c6070; border-bottom-color: #e6e8f2; }
body.theme-light .cp-wh-item:hover { color: #1a1c24; }

/* ================= ⑦ 代码块：标签栏 / 复制按钮 / SQL 高亮 ================= */
.cp-code-wrap {
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
  margin: 12px 0;
}
.cp-code-wrap pre { margin: 0 !important; border-radius: 0 !important; }
.cp-code-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 12px;
  background: rgba(127, 127, 160, 0.12);
  border-bottom: 1px solid var(--border-color);
}
.cp-code-lang { font-size: 10.5px; letter-spacing: 1px; color: var(--text-secondary); }
.cp-copy-btn {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 11.5px;
  border-radius: 6px;
  padding: 3px 10px;
  cursor: pointer;
  transition: all 0.15s;
}
.cp-copy-btn:hover { border-color: #2f8a63; color: #c9a45c; }
.cp-tok-str { color: #7ec699; }
.cp-tok-comment { color: #7a7f92; font-style: italic; }
.cp-tok-kw { color: #e0c684; font-weight: 700; }
.cp-tok-num { color: #f0b866; }
body.theme-light .cp-tok-str { color: #1d7a45; }
body.theme-light .cp-tok-comment { color: #8a8fa3; }
body.theme-light .cp-tok-kw { color: #2b5fd9; }
body.theme-light .cp-tok-num { color: #b8690f; }

/* ================= ⑧ 报告预览模态框 ================= */
.cp-preview-mask {
  position: fixed; inset: 0; z-index: 4000;
  background: rgba(8, 6, 16, 0.72);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  padding: 32px;
}
/* 在线预览需盖在报告中心等弹层之上 */
.cp-preview-mask.cp-preview-top { z-index: 4200; }
.cp-preview-modal {
  width: min(860px, 100%);
  height: min(86vh, 900px);
  background: var(--surface-dark, #0d2b21);
  border: 1px solid var(--border-color, #27594a);
  border-radius: 16px;
  display: flex; flex-direction: column;
  overflow: hidden;
  box-shadow: 0 30px 90px rgba(0,0,0,0.6);
}
.cp-preview-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border-color, #27594a);
}
.cp-preview-title {
  font-size: 14px; font-weight: 700; color: var(--text-primary, #e9f2ec);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cp-preview-dl {
  font-size: 12.5px; color: #e0c684; text-decoration: none;
  border: 1px solid #8a7434; border-radius: 8px; padding: 5px 12px;
}
.cp-preview-dl:hover { background: rgba(58, 168, 120, 0.15); }
.cp-preview-body { flex: 1; overflow: auto; background: var(--bg-dark, #071d16); }
.cp-preview-frame { width: 100%; height: 100%; border: none; background: #fff; }
.cp-preview-loading {
  display: flex; align-items: center; justify-content: center;
  height: 200px; color: var(--text-secondary, #a8c3b4); font-size: 14px;
}
.cp-preview-md { padding: 24px 28px; max-width: none; }

/* 文件行 / 文件卡片上的预览按钮 */
.cp-file-eye {
  background: transparent; border: none; color: var(--text-secondary, #a8c3b4);
  cursor: pointer; padding: 6px; border-radius: 6px; line-height: 0;
  flex-shrink: 0;
}
.cp-file-eye:hover { color: #c9a45c; background: rgba(58, 168, 120, 0.14); }
.file-item { display: flex; align-items: center; gap: 4px; }
.file-item .file-link { flex: 1; min-width: 0; }
.file-card-wrap { position: relative; }
.cp-preview-chip {
  position: absolute; right: 8px; bottom: 8px;
  display: flex; align-items: center; gap: 5px;
  background: rgba(58, 168, 120, 0.85);
  border: none; color: #fff;
  font-size: 11.5px;
  border-radius: 8px;
  padding: 5px 10px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s;
}
.file-card-wrap:hover .cp-preview-chip { opacity: 1; }
.cp-preview-chip:hover { background: #2f8a63; }

/* ================= ⑩ 语音输入按钮 ================= */
.cp-mic-btn { position: relative; }
.cp-mic-btn.recording {
  color: #ff6b81;
  animation: cp-pulse 1.1s ease-in-out infinite;
}
@keyframes cp-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.12); }
}
.cp-mic-btn.recording::after {
  content: '';
  position: absolute; top: 6px; right: 6px;
  width: 7px; height: 7px; border-radius: 50%;
  background: #ff6b81;
}

/* ================= 演示级视觉升级 ================= */

/* 背景光晕 + 网格 */
.cp-bg-deco { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
.main-content, .input-footer, .file-sidebar { position: relative; z-index: 1; }
.cp-blob {
  position: absolute; border-radius: 50%; filter: blur(90px); opacity: 0.35;
  animation: cp-float 16s ease-in-out infinite;
}
.cp-blob-1 { width: 480px; height: 480px; top: -160px; right: -120px; background: radial-gradient(circle, #2f8a63 0%, transparent 70%); }
.cp-blob-2 { width: 420px; height: 420px; bottom: -140px; left: -120px; background: radial-gradient(circle, #c9a45c 0%, transparent 70%); animation-delay: -5s; }
.cp-blob-3 { width: 360px; height: 360px; top: 30%; left: 42%; background: radial-gradient(circle, #3fa98c 0%, transparent 70%); opacity: 0.16; animation-delay: -9s; }
@keyframes cp-float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(-30px, 24px) scale(1.06); }
  66% { transform: translate(22px, -18px) scale(0.96); }
}
.cp-grid-lines {
  position: absolute; inset: 0;
  background-image: linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(ellipse 90% 70% at 50% 40%, #000 30%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse 90% 70% at 50% 40%, #000 30%, transparent 75%);
}
body.theme-light .cp-grid-lines {
  background-image: linear-gradient(rgba(30,30,60,0.04) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(30,30,60,0.04) 1px, transparent 1px);
}
body.theme-light .cp-blob { opacity: 0.2; }

/* 品牌条 */
.cp-brand-bar {
  position: fixed; top: 18px; left: 22px; z-index: 2500;
  display: flex; align-items: center; gap: 10px;
}
.cp-brand-logo {
  width: 34px; height: 34px; border-radius: 10px;
  background: linear-gradient(135deg, #2f8a63, #3aa878, #c9a45c);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 18px rgba(58, 168, 120, 0.45);
}
.cp-brand-name { font-size: 15.5px; font-weight: 800; color: #e9f2ec; letter-spacing: 0.5px; }
.cp-brand-badge {
  font-size: 10px; color: #93b5a7; letter-spacing: 1px;
  border: 1px solid #235445; border-radius: 999px; padding: 3px 9px;
}
body.theme-light .cp-brand-name { color: #1a1c24; }
body.theme-light .cp-brand-badge { color: #7a7f92; border-color: #d9dce7; }

/* 消息入场动画 + AI 渐变顶线 + 用户气泡渐变 */
.message-wrapper { animation: cp-fade-up 0.35s ease both; }
@keyframes cp-fade-up {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
.message-ai .ai-content-wrapper::before {
  content: '';
  display: block;
  width: 100%; height: 1.5px;
  margin-bottom: 14px;
  background: linear-gradient(90deg, rgba(58,168,120,0.55), rgba(201,164,92,0.35), transparent 80%);
  border-radius: 2px;
}
/* 用户气泡：深绿→金渐变（金色端压暗一档，保证亮色文字两段都清晰） */
.message-user .msg-content {
  background: linear-gradient(120deg, #10402f 0%, #1b6449 48%, #9a7a37 100%) !important;
  color: #f4fbf7 !important;
  font-weight: 500;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.28);
  box-shadow: 0 8px 22px rgba(58, 168, 120, 0.28);
  border: 1px solid rgba(255, 255, 255, 0.12);
}

/* 时间线浮条渐变描边 */
.cp-timeline {
  border: 1px solid transparent;
  background:
    linear-gradient(rgba(11, 36, 28, 0.94), rgba(11, 36, 28, 0.94)) padding-box,
    linear-gradient(90deg, #2f8a63, #3aa878, #c9a45c) border-box;
  box-shadow: 0 10px 36px rgba(58, 168, 120, 0.25);
}
body.theme-light .cp-timeline {
  background:
    linear-gradient(rgba(255, 255, 255, 0.97), rgba(255, 255, 255, 0.97)) padding-box,
    linear-gradient(90deg, #2f8a63, #3aa878, #c9a45c) border-box;
}

/* ===== 欢迎屏 Hero ===== */
.cp-welcome {
  display: flex; flex-direction: column; align-items: center;
  width: 100%; max-width: 860px;
  animation: cp-fade-up 0.5s ease both;
}
.cp-hero {
  display: flex; align-items: center; gap: 36px;
  justify-content: center;
  flex-wrap: wrap;
}
.cp-hero-compass {
  flex-shrink: 0;
  filter: drop-shadow(0 0 24px rgba(58, 168, 120, 0.45));
  animation: cp-breathe 4s ease-in-out infinite;
}
@keyframes cp-breathe {
  0%, 100% { filter: drop-shadow(0 0 20px rgba(58, 168, 120, 0.4)); transform: scale(1); }
  50% { filter: drop-shadow(0 0 34px rgba(201, 164, 92, 0.65)); transform: scale(1.03); }
}
.cp-compass-needle {
  transform-origin: 60px 60px;
  animation: cp-swing 5s ease-in-out infinite;
}
@keyframes cp-swing {
  0%, 100% { transform: rotate(-14deg); }
  50% { transform: rotate(14deg); }
}
.cp-hero-text { max-width: 520px; }
.cp-hero-title {
  font-size: clamp(30px, 4.2vw, 44px);
  line-height: 1.22;
  font-weight: 800;
  color: #eef6f1;
  margin: 0 0 14px;
  letter-spacing: 0.5px;
}
.cp-hero-grad {
  background: linear-gradient(90deg, #3aa878 0%, #c9a45c 45%, #e0c684 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.cp-hero-sub {
  font-size: 14.5px; color: #a8c3b4; line-height: 1.85; margin: 0 0 18px;
}
body.theme-light .cp-hero-title { color: #1a1c24; }
body.theme-light .cp-hero-sub { color: #5c6070; }

.cp-hero-stats {
  display: flex; align-items: center; gap: 16px;
  background: rgba(13, 43, 33, 0.6);
  border: 1px solid #1e4a3a;
  border-radius: 14px;
  padding: 12px 20px;
  backdrop-filter: blur(8px);
}
body.theme-light .cp-hero-stats { background: rgba(255,255,255,0.85); border-color: #d9dce7; }
.cp-hstat { display: flex; flex-direction: column; align-items: center; min-width: 56px; }
.cp-hstat-num { font-size: 19px; font-weight: 800; color: #eef6f1; }
body.theme-light .cp-hstat-num { color: #1a1c24; }
.cp-hstat-label { font-size: 10.5px; color: #86a89a; margin-top: 3px; white-space: nowrap; }
.cp-hstat-div { width: 1px; height: 28px; background: #235445; }
body.theme-light .cp-hstat-div { background: #d9dce7; }

/* 数据快览图表 */
.cp-charts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  width: 100%;
  margin-top: 30px;
}
.cp-chart-card {
  background: rgba(11, 36, 28, 0.72);
  border: 1px solid #1a4536;
  border-radius: 14px;
  padding: 13px 16px;
  backdrop-filter: blur(6px);
  transition: transform 0.18s, border-color 0.18s;
}
.cp-chart-card:hover { transform: translateY(-3px); border-color: #8a7434; }
body.theme-light .cp-chart-card { background: rgba(255,255,255,0.85); border-color: #d9dce7; }
.cp-chart-head { font-size: 11.5px; color: #86a89a; margin-bottom: 10px; letter-spacing: 0.5px; }
.cp-ring-row { display: flex; align-items: center; gap: 12px; }
.cp-ring-desc { font-size: 11.5px; color: #a8c3b4; line-height: 1.6; }
body.theme-light .cp-ring-desc { color: #5c6070; }
.cp-bars {
  display: flex; align-items: flex-end; justify-content: space-around;
  height: 56px; gap: 8px;
}
.cp-bar {
  display: flex; flex-direction: column; justify-content: flex-end; align-items: center;
  font-size: 9.5px; color: #86a89a; gap: 4px;
  width: 25%;
}
.cp-bar i {
  display: block; width: 18px; border-radius: 5px 5px 2px 2px;
  transform-origin: bottom;
  animation: cp-grow 0.9s ease both;
}
@keyframes cp-grow { from { transform: scaleY(0); } to { transform: scaleY(1); } }

/* 快捷提问渐变卡（覆盖旧版） */
.cp-quick-grid {
  width: 100%;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: 26px;
}
.cp-quick-chip {
  background: rgba(13, 43, 33, 0.7);
  border: 1px solid #1e4a3a;
  border-radius: 13px;
  padding: 15px 16px;
  backdrop-filter: blur(6px);
}
.cp-quick-chip:hover {
  background: rgba(58, 168, 120, 0.14);
  border-color: transparent;
  background:
    linear-gradient(rgba(13, 43, 33, 0.9), rgba(13, 43, 33, 0.9)) padding-box,
    linear-gradient(120deg, #2f8a63, #3aa878, #c9a45c) border-box;
}
body.theme-light .cp-quick-chip:hover {
  background:
    linear-gradient(#ffffff, #ffffff) padding-box,
    linear-gradient(120deg, #2f8a63, #3aa878, #c9a45c) border-box;
}

@media (max-width: 900px) {
  .cp-hero { gap: 20px; }
  .cp-hero-compass svg { width: 84px; height: 84px; }
  .cp-charts { grid-template-columns: 1fr; }
  .cp-quick-grid { grid-template-columns: 1fr 1fr; }
  .cp-brand-bar { top: 12px; left: 14px; }
  .cp-user-bar { top: 12px; right: 12px; }
}

/* 完结撒花彩带画布 */
.cp-confetti {
  position: fixed; inset: 0;
  z-index: 5000;
  pointer-events: none;
}

</style>
