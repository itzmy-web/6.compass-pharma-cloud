<script setup lang="ts">
import { ref, computed } from 'vue'

const emit = defineEmits<{ (e: 'logged-in', info: { channel: string; phone: string }): void }>()

// 伪二维码数据点（固定伪随机，避免每次渲染闪动）
const qrDots: Array<[number, number]> = []
{
  let seed = 42
  for (let y = 10; y <= 27; y++) {
    for (let x = 1; x <= 27; x++) {
      if (x <= 9 && y <= 9) continue   // 跳过定位角区域
      if (x >= 20 && y <= 9) continue
      if (x <= 9 && y >= 20) continue
      seed = (seed * 1103515245 + 12345) % 2147483648
      if (seed % 100 < 46) qrDots.push([x, y])
    }
  }
}

// ---------- 登录态 ----------
type Channel = 'phone' | 'wechat' | 'alipay'
const activeChannel = ref<Channel>('phone')

// ---------- 手机号登录 ----------
const phone = ref('')
const smsCode = ref('')
const sentCode = ref('')          // 演示环境直接展示的验证码
const codeCountdown = ref(0)
const phoneTouched = ref(false)
const codeError = ref('')

const PHONE_RE = /^1[3-9]\d{9}$/

const phoneError = computed(() => {
  if (!phoneTouched.value) return ''
  const v = phone.value.replace(/\D/g, '')
  if (v.length === 0) return ''
  if (v.length < 11) return `手机号不足 11 位，还差 ${11 - v.length} 位`
  if (!PHONE_RE.test(v)) return '手机号格式不正确，应以 1 开头的 11 位数字'
  return ''
})

const onPhoneInput = () => {
  phoneTouched.value = true
}

const canGetCode = computed(() => PHONE_RE.test(phone.value.replace(/\D/g, '')) && codeCountdown.value === 0)
const canLogin = computed(() => PHONE_RE.test(phone.value.replace(/\D/g, '')) && smsCode.value.length === 6)

// 协议勾选
const agreed = ref(false)
const agreeError = ref(false)
const agreeShake = ref(false)
const toggleAgree = () => {
  agreed.value = !agreed.value
  if (agreed.value) agreeError.value = false
}
const requireAgree = () => {
  if (agreed.value) return true
  agreeError.value = true
  agreeShake.value = true
  setTimeout(() => { agreeShake.value = false }, 500)
  return false
}

const loginByPhone = () => {
  if (!PHONE_RE.test(phone.value.replace(/\D/g, ''))) {
    phoneTouched.value = true
    return
  }
  if (!requireAgree()) return
  if (smsCode.value.length < 6) {
    codeError.value = '请输入 6 位短信验证码'
    return
  }
  if (sentCode.value && smsCode.value !== sentCode.value) {
    codeError.value = '验证码不正确，请核对上方提示'
    return
  }
  emit('logged-in', { channel: 'phone', phone: phone.value.replace(/\D/g, '') })
}

const getCode = () => {
  if (!canGetCode.value) return
  // 演示环境：生成 6 位验证码直接展示
  sentCode.value = String(Math.floor(100000 + Math.random() * 900000))
  codeError.value = ''
  codeCountdown.value = 60
  // 验证码自动填入输入框（模拟收到短信后自动读取）
  smsCode.value = ''
  setTimeout(() => { smsCode.value = sentCode.value }, 500)
  const timer = setInterval(() => {
    codeCountdown.value--
    if (codeCountdown.value <= 0) clearInterval(timer)
  }, 1000)
}

// ---------- 扫码登录（演示环境：模拟扫码） ----------
const qrScanPending = ref<Channel | null>(null)

const mockScan = (channel: Channel) => {
  if (!requireAgree()) return
  qrScanPending.value = channel
  // 模拟扫码 -> 授权 的过程
  setTimeout(() => {
    qrScanPending.value = null
    emit('logged-in', { channel, phone: '' })
  }, 900)
}

// ---------- 快捷进入（之前登录过的账号） ----------
const maskPhone = (p: string) => (p && p.length === 11 ? `${p.slice(0, 3)}****${p.slice(7)}` : p)
const lastAccount = (() => {
  try {
    const raw = localStorage.getItem('compass_auth')
    return raw ? JSON.parse(raw) : null
  } catch { return null }
 })()

const quickEnter = () => {
  if (lastAccount) emit('logged-in', lastAccount)
}
</script>

<template>
  <div class="login-page">
    <!-- 背景罗盘（与参考图一致：细金线同心圆 + 刻度 + 罗盘星 + 方位字母） -->
    <div class="compass-bg" aria-hidden="true">
      <svg viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="lgGold" x1="0" y1="0" x2="1200" y2="800" gradientUnits="userSpaceOnUse">
            <stop stop-color="#e8cf94"/>
            <stop offset="0.5" stop-color="#c9a45c"/>
            <stop offset="1" stop-color="#a8863f"/>
          </linearGradient>
        </defs>

        <!-- 同心圆环 -->
        <g stroke="url(#lgGold)" fill="none">
          <circle cx="620" cy="400" r="330" stroke-width="1" opacity="0.35"/>
          <circle cx="620" cy="400" r="290" stroke-width="0.6" opacity="0.22" stroke-dasharray="2 6"/>
          <circle cx="620" cy="400" r="245" stroke-width="1" opacity="0.3"/>
          <circle cx="620" cy="400" r="238" stroke-width="0.5" opacity="0.18"/>
          <circle cx="620" cy="400" r="180" stroke-width="0.7" opacity="0.26" stroke-dasharray="1 5"/>
          <circle cx="620" cy="400" r="120" stroke-width="0.8" opacity="0.3"/>
          <circle cx="620" cy="400" r="60"  stroke-width="0.7" opacity="0.25"/>
        </g>

        <!-- 外圈刻度（长短线交替） -->
        <g stroke="url(#lgGold)" opacity="0.4">
          <line x1="620" y1="40"  x2="620" y2="70"/>
          <line x1="620" y1="730" x2="620" y2="760"/>
          <line x1="260" y1="400" x2="290" y2="400"/>
          <line x1="950" y1="400" x2="980" y2="400"/>
          <line x1="397" y1="177" x2="417" y2="197" stroke-width="0.7"/>
          <line x1="823" y1="177" x2="843" y2="197" stroke-width="0.7"/>
          <line x1="397" y1="623" x2="417" y2="603" stroke-width="0.7"/>
          <line x1="823" y1="623" x2="843" y2="603" stroke-width="0.7"/>
        </g>

        <!-- 细刻度圈（用虚线圆模拟密集刻度） -->
        <circle cx="620" cy="400" r="310" stroke="url(#lgGold)" stroke-width="4" fill="none"
                opacity="0.14" stroke-dasharray="1 7"/>

        <!-- 罗盘星（八芒） -->
        <g transform="translate(620 400)">
          <path d="M0 -180 L14 -14 L0 180 L-14 -14 Z" fill="url(#lgGold)" opacity="0.85"/>
          <path d="M-180 0 L-14 -14 L180 0 L-14 14 Z" fill="url(#lgGold)" opacity="0.6"/>
          <path d="M0 -180 L-14 -14 L0 180 L14 -14 Z" fill="url(#lgGold)" opacity="0.45"/>
          <circle r="7" fill="#0d362a" stroke="url(#lgGold)" stroke-width="2"/>
          <!-- 内圈小十字准线 -->
          <g stroke="url(#lgGold)" stroke-width="0.8" opacity="0.5">
            <line x1="-46" y1="0" x2="46" y2="0"/>
            <line x1="0" y1="-46" x2="0" y2="46"/>
          </g>
        </g>

        <!-- 方位字母 -->
        <g fill="url(#lgGold)" font-family="Georgia, 'Times New Roman', serif" text-anchor="middle">
          <text x="620" y="52"  font-size="30" opacity="0.9">N</text>
          <text x="620" y="775" font-size="22" opacity="0.55">S</text>
          <text x="965" y="408" font-size="18" opacity="0.4">E</text>
          <text x="275" y="408" font-size="18" opacity="0.4">W</text>
        </g>

        <!-- 散落的刻度数字（装饰） -->
        <g fill="url(#lgGold)" font-family="Georgia, serif" font-size="11" opacity="0.35">
          <text x="360" y="120">32700</text>
          <text x="880" y="90">10500</text>
          <text x="940" y="330">2380</text>
          <text x="330" y="560">826</text>
          <text x="850" y="620">160/2700</text>
          <text x="500" y="720">12:00</text>
          <text x="180" y="240">40200</text>
          <text x="990" y="560">AGS</text>
        </g>
      </svg>
    </div>

    <!-- ======== 左栏：品牌 + 大标题 + 胶囊标签（1:1 对照参考图） ======== -->
    <div class="intro-pane">
      <div class="brand-row">
        <div class="brand-logo">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L15 9L22 12L15 15L12 22L9 15L2 12L9 9L12 2Z" fill="#0d362a"/>
            <circle cx="12" cy="12" r="3.2" fill="#c9a45c"/>
          </svg>
        </div>
        <div class="brand-name">航策向标</div>
        <div class="brand-menu" aria-hidden="true">
          <span></span><span></span><span></span>
        </div>
      </div>

      <div class="hero-block">
        <h1 class="hero-title">航策向标</h1>
        <p class="hero-sub">业务趋势的智能风向标，定位业务方向</p>
        <div class="hero-tags">
          <span class="hero-tag">指标导航</span>
          <span class="hero-tag">竞争感知</span>
          <span class="hero-tag">态势研判</span>
        </div>
      </div>
    </div>

    <!-- ======== 右栏：登录卡片（白色卡 + 深绿按钮，对照参考图配色） ======== -->
    <div class="auth-pane">
      <div class="auth-card">
        <h2 class="auth-title">欢迎登录</h2>
        <p class="auth-sub">登录后进入航策向标智能工作台，历史记录跟随账号保存</p>

        <!-- Tab 切换 -->
        <div class="channel-tabs">
          <button
            class="tab-btn"
            :class="{ active: activeChannel === 'phone' }"
            @click="activeChannel = 'phone'"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <rect x="7" y="2.5" width="10" height="19" rx="2.5" stroke="currentColor" stroke-width="2"/>
              <circle cx="12" cy="18" r="1.2" fill="currentColor"/>
            </svg>
            手机验证码
          </button>
          <button
            class="tab-btn"
            :class="{ active: activeChannel === 'wechat' }"
            @click="activeChannel = 'wechat'"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path d="M9.5 4C5.9 4 3 6.4 3 9.4c0 1.7 1 3.2 2.4 4.2L4.8 15.6l2.3-1.2c.7.2 1.5.4 2.4.4h.4A5.6 5.6 0 0 1 9.5 4z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
              <path d="M21 13.6c0-2.5-2.4-4.6-5.3-4.6s-5.3 2-5.3 4.6 2.4 4.6 5.3 4.6c.6 0 1.3-.1 1.8-.3l2 1-.5-1.7A4.4 4.4 0 0 0 21 13.6z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
            </svg>
            微信扫码
          </button>
          <button
            class="tab-btn"
            :class="{ active: activeChannel === 'alipay' }"
            @click="activeChannel = 'alipay'"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path d="M3 4h18v16H3z" stroke="currentColor" stroke-width="1.8"/>
              <path d="M7 15c2.5 1.2 6 1.8 10-.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
              <path d="M10 7v3.5c0 1.5-.6 2.7-1.8 3.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
              <path d="M11.5 10.5h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
            支付宝
          </button>
        </div>

        <!-- 手机号登录 -->
        <div v-if="activeChannel === 'phone'" class="channel-body">
          <label class="field-label">手机号</label>
          <div class="input-wrap" :class="{ 'input-error': phoneError }">
            <svg class="input-icon" width="16" height="16" viewBox="0 0 24 24" fill="none">
              <rect x="7" y="2.5" width="10" height="19" rx="2.5" stroke="#9aa8a0" stroke-width="2"/>
              <circle cx="12" cy="18" r="1.2" fill="#9aa8a0"/>
            </svg>
            <input
              v-model="phone"
              type="tel"
              maxlength="11"
              placeholder="11 位手机号"
              @input="onPhoneInput"
              @blur="phoneTouched = true"
            />
          </div>
          <div v-if="phoneError" class="error-tip">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="#d9534f" stroke-width="2"/>
              <path d="M12 7v6" stroke="#d9534f" stroke-width="2" stroke-linecap="round"/>
              <circle cx="12" cy="16.5" r="1.1" fill="#d9534f"/>
            </svg>
            {{ phoneError }}
          </div>

          <label class="field-label">短信验证码</label>
          <div class="code-row">
            <div class="input-wrap code-input" :class="{ 'input-error': codeError }">
              <svg class="input-icon" width="16" height="16" viewBox="0 0 24 24" fill="none">
                <rect x="3" y="5" width="18" height="14" rx="2" stroke="#9aa8a0" stroke-width="2"/>
                <path d="M3 7l9 6 9-6" stroke="#9aa8a0" stroke-width="2"/>
              </svg>
              <input
                v-model="smsCode"
                type="text"
                maxlength="6"
                placeholder="6 位验证码"
                @input="codeError = ''"
              />
            </div>
            <button class="get-code-btn" :disabled="!canGetCode" @click="getCode">
              {{ codeCountdown > 0 ? `${codeCountdown}s 后重发` : '获取验证码' }}
            </button>
          </div>
          <div v-if="codeError" class="error-tip">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="#d9534f" stroke-width="2"/>
              <path d="M12 7v6" stroke="#d9534f" stroke-width="2" stroke-linecap="round"/>
              <circle cx="12" cy="16.5" r="1.1" fill="#d9534f"/>
            </svg>
            {{ codeError }}
          </div>
          <div v-if="sentCode" class="demo-code-tip">
            演示环境不发真实短信，验证码：
            <span class="demo-code">{{ sentCode }}</span>
          </div>

          <!-- 协议勾选 -->
          <div class="agree-row" :class="{ 'agree-error': agreeError, 'agree-shake': agreeShake }">
            <button
              type="button"
              class="agree-checkbox"
              :class="{ checked: agreed }"
              @click="toggleAgree"
              aria-label="同意协议"
            >
              <svg v-if="agreed" width="12" height="12" viewBox="0 0 24 24" fill="none">
                <path d="M5 12.5L10 17.5L19 7" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
            <span class="agree-text">
              我已阅读并同意
              <a class="agree-link" href="javascript:void(0)" @click="agreeError = false">《用户协议》</a>
              与
              <a class="agree-link" href="javascript:void(0)" @click="agreeError = false">《隐私政策》</a>
              ，并授权使用本服务完成注册 / 登录。
            </span>
          </div>
          <div v-if="agreeError" class="error-tip" style="margin-top:6px;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="#d9534f" stroke-width="2"/>
              <path d="M12 7v6" stroke="#d9534f" stroke-width="2" stroke-linecap="round"/>
              <circle cx="12" cy="16.5" r="1.1" fill="#d9534f"/>
            </svg>
            请先勾选同意《用户协议》与《隐私政策》
          </div>

          <button class="login-btn" :disabled="!canLogin" @click="loginByPhone">登 录</button>

          <div class="auth-footnote">演示环境不发真实短信，仅用于功能体验</div>
        </div>

        <!-- 微信 / 支付宝 扫码登录 -->
        <div v-else class="channel-body qr-body">
          <div class="qr-frame">
            <svg width="150" height="150" viewBox="0 0 29 29" class="qr-svg">
              <rect width="29" height="29" fill="#fff"/>
              <!-- 三个定位角 -->
              <rect x="1" y="1" width="7" height="7" fill="#0d362a"/>
              <rect x="2" y="2" width="5" height="5" fill="#fff"/>
              <rect x="3" y="3" width="3" height="3" fill="#0d362a"/>
              <rect x="21" y="1" width="7" height="7" fill="#0d362a"/>
              <rect x="22" y="2" width="5" height="5" fill="#fff"/>
              <rect x="23" y="3" width="3" height="3" fill="#0d362a"/>
              <rect x="1" y="21" width="7" height="7" fill="#0d362a"/>
              <rect x="2" y="22" width="5" height="5" fill="#fff"/>
              <rect x="3" y="23" width="3" height="3" fill="#0d362a"/>
              <!-- 伪数据点 -->
              <template v-for="(x, i) in qrDots" :key="i">
                <rect :x="x[0]" :y="x[1]" width="1" height="1" fill="#0d362a"/>
              </template>
            </svg>
            <div class="qr-scan-line" v-if="qrScanPending !== activeChannel"></div>
          </div>
          <div class="qr-tip">
            {{ activeChannel === 'wechat' ? '请使用微信扫一扫登录' : '请使用支付宝扫一扫登录' }}
          </div>
          <button class="mock-scan-btn" @click="mockScan(activeChannel)">
            {{ qrScanPending === activeChannel ? '授权中…' : '演示环境：模拟扫码成功' }}
          </button>
          <div class="auth-footnote">线上演示环境，扫码通道为模拟实现</div>
        </div>

        <!-- 上次登录账号快捷进入 -->
        <div v-if="lastAccount" class="quick-enter">
          <button class="quick-btn" @click="quickEnter">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="8" r="4" stroke="currentColor" stroke-width="2"/>
              <path d="M4 20c1.5-3.5 4.5-5 8-5s6.5 1.5 8 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            {{ lastAccount.phone ? `继续上次登录：${maskPhone(lastAccount.phone)}` : '继续上次扫码登录' }}？直接进入
          </button>
        </div>

        <div class="auth-bottom-note">新老数据保存在当前浏览器，手机号 / 扫码登录长期保存</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  display: flex;
  /* 深绿底 + 轻微暗角，对照参考图 */
  background:
    radial-gradient(1100px 700px at 62% 46%, #14493a 0%, rgba(20, 73, 58, 0) 62%),
    radial-gradient(900px 700px at 100% 100%, #0a2b21 0%, rgba(10, 43, 33, 0) 60%),
    #0d362a;
  color: #eef4f0;
  overflow: auto;
  z-index: 9999;
}

/* ===== 背景罗盘 ===== */
.compass-bg {
  position: absolute; inset: 0;
  pointer-events: none;
  overflow: hidden;
}
.compass-bg svg { width: 100%; height: 100%; }

/* ===== 左栏 ===== */
.intro-pane {
  flex: 1.15;
  min-width: 0;
  padding: 40px 56px;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
}
.brand-row { display: flex; align-items: center; gap: 10px; }
.brand-logo {
  width: 34px; height: 34px; border-radius: 9px;
  background: linear-gradient(135deg, #e8cf94, #c9a45c);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 14px rgba(201, 164, 92, 0.35);
}
.brand-name { font-size: 18px; font-weight: 800; letter-spacing: 1px; color: #f4efe2; }
.brand-menu {
  margin-left: auto;
  display: flex; flex-direction: column; gap: 5px;
  padding: 6px 4px;
}
.brand-menu span {
  display: block; width: 22px; height: 2px; border-radius: 2px;
  background: #c9a45c; opacity: 0.85;
}

.hero-block {
  margin-top: auto;
  margin-bottom: auto;
  padding: 40px 0;
}
.hero-title {
  margin: 0;
  font-size: 72px;
  font-weight: 900;
  letter-spacing: 6px;
  line-height: 1.15;
  background: linear-gradient(100deg, #f0dba6 0%, #d9b96e 45%, #c9a45c 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  text-shadow: 0 6px 30px rgba(201, 164, 92, 0.25);
}
.hero-sub {
  margin: 14px 0 0 4px;
  font-size: 20px;
  font-weight: 500;
  color: #f2f6f3;
  letter-spacing: 2px;
}
.hero-tags { display: flex; gap: 14px; margin-top: 30px; padding-left: 4px; flex-wrap: wrap; }
.hero-tag {
  font-size: 14px;
  color: #f2f6f3;
  border: 1px solid rgba(201, 164, 92, 0.85);
  border-radius: 999px;
  padding: 7px 20px;
  letter-spacing: 2px;
  background: rgba(13, 54, 42, 0.35);
  backdrop-filter: blur(2px);
}

/* ===== 右栏 ===== */
.auth-pane {
  flex: 1;
  min-width: 400px;
  display: flex; align-items: center; justify-content: center;
  padding: 40px 48px;
  position: relative;
  z-index: 1;
}
.auth-card {
  width: 100%; max-width: 400px;
  background: #ffffff;
  border-radius: 24px;
  padding: 34px 32px 26px;
  box-shadow: 0 30px 80px rgba(4, 20, 15, 0.45);
  color: #17322a;
}
.auth-title {
  font-size: 22px; font-weight: 800; margin: 0 0 6px;
  text-align: center; color: #12362b;
}
.auth-sub { font-size: 12px; color: #7d8f88; margin: 0 0 18px; text-align: center; }

/* Tab：浅灰分段控件，选中深绿 */
.channel-tabs {
  display: flex; gap: 4px;
  background: #eef3f0;
  border-radius: 12px; padding: 4px; margin-bottom: 18px;
}
.tab-btn {
  flex: 1; display: flex; align-items: center; justify-content: center; gap: 5px;
  background: transparent; border: none; color: #6d8078;
  font-size: 12.5px; padding: 9px 0; border-radius: 9px; cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.tab-btn.active {
  background: #14493a;
  color: #f4efe2; font-weight: 700;
  box-shadow: 0 4px 12px rgba(20, 73, 58, 0.35);
}

/* 输入：参考图的下划线极简风 */
.field-label { display: block; font-size: 12px; color: #6d8078; margin: 14px 0 2px; }
.input-wrap {
  display: flex; align-items: center; gap: 8px;
  background: transparent;
  border: none; border-bottom: 1.5px solid #d5ded9;
  border-radius: 0;
  padding: 0 2px; height: 44px;
  transition: border-color 0.15s;
}
.input-wrap:focus-within { border-bottom-color: #14493a; }
.input-wrap.input-error { border-bottom-color: #d9534f; }
.input-wrap input {
  flex: 1; background: transparent; border: none; outline: none;
  color: #1d3a30; font-size: 14.5px; min-width: 0;
}
.input-wrap input::placeholder { color: #a9b8b1; }
.error-tip {
  display: flex; align-items: center; gap: 5px;
  color: #d9534f; font-size: 12px; margin-top: 6px;
}
.code-row { display: flex; gap: 10px; align-items: flex-end; }
.code-input { flex: 1; }
.get-code-btn {
  background: #14493a;
  border: none; border-radius: 10px; color: #f4efe2;
  font-size: 12.5px; padding: 0 14px; height: 38px; cursor: pointer; white-space: nowrap;
  transition: background 0.15s;
}
.get-code-btn:hover { background: #1d5c49; }
.get-code-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.demo-code-tip {
  margin-top: 10px; font-size: 12px; color: #6d8078;
  background: #f2f7f4; border: 1px dashed #bcd3c8;
  border-radius: 8px; padding: 8px 10px;
}
.demo-code { color: #a8863f; font-weight: 800; letter-spacing: 2px; }

/* 协议勾选行 */
.agree-row {
  display: flex; align-items: flex-start; gap: 9px;
  margin-top: 16px;
  padding: 10px 12px;
  background: #f6faf8;
  border: 1px solid #dfe9e4;
  border-radius: 10px;
  transition: border-color 0.2s;
}
.agree-row.agree-error { border-color: rgba(217, 83, 79, 0.55); }
.agree-row.agree-shake { animation: agree-shake 0.45s ease; }
@keyframes agree-shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-5px); }
  40% { transform: translateX(5px); }
  60% { transform: translateX(-3px); }
  80% { transform: translateX(3px); }
}
.agree-checkbox {
  flex-shrink: 0;
  width: 20px; height: 20px;
  margin-top: 1px;
  border: 2px solid #b4c5bd;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  padding: 0;
  transition: all 0.15s;
}
.agree-checkbox:hover { border-color: #14493a; }
.agree-checkbox.checked {
  background: #14493a;
  border-color: #14493a;
  box-shadow: 0 2px 8px rgba(20, 73, 58, 0.4);
}
.agree-text {
  font-size: 12px; line-height: 1.7;
  color: #6d8078;
}
.agree-link {
  color: #1d5c49;
  text-decoration: underline;
  text-underline-offset: 2px;
  font-weight: 600;
}
.agree-link:hover { color: #0d362a; }

/* 登录按钮：参考图的深绿实心 */
.login-btn {
  width: 100%; margin-top: 20px; height: 48px;
  background: #14493a;
  border: none; border-radius: 12px; color: #f4efe2;
  font-size: 15px; font-weight: 800; cursor: pointer; letter-spacing: 8px;
  box-shadow: 0 8px 22px rgba(13, 54, 42, 0.35);
  transition: background 0.15s, transform 0.1s;
}
.login-btn:hover { background: #1d5c49; }
.login-btn:active { transform: translateY(1px); }
.login-btn:disabled { opacity: 0.4; cursor: not-allowed; box-shadow: none; }

/* 扫码 */
.qr-body { display: flex; flex-direction: column; align-items: center; }
.qr-frame {
  position: relative; background: #fff; border-radius: 14px;
  padding: 12px; margin-top: 14px;
  box-shadow: 0 0 0 1px #dfe9e4, 0 10px 30px rgba(13, 54, 42, 0.12);
}
.qr-scan-line {
  position: absolute; left: 10px; right: 10px; height: 2px;
  background: linear-gradient(90deg, transparent, #c9a45c, transparent);
  animation: scan 2.2s ease-in-out infinite;
}
@keyframes scan { 0%, 100% { top: 12px; } 50% { top: calc(100% - 14px); } }
.qr-tip { margin-top: 14px; font-size: 13.5px; color: #42594f; }
.mock-scan-btn {
  margin-top: 14px; background: #eef3f0; border: 1px solid #cfe0d8;
  color: #1d5c49; font-size: 13px; border-radius: 10px;
  padding: 10px 18px; cursor: pointer; transition: all 0.15s;
}
.mock-scan-btn:hover { border-color: #14493a; background: #e4efe9; }

/* 快捷进入 & 底注 */
.quick-enter { margin-top: 16px; }
.quick-btn {
  width: 100%; display: flex; align-items: center; justify-content: center; gap: 7px;
  background: rgba(20, 73, 58, 0.06); border: 1px dashed #9dbdaf;
  color: #1d5c49; font-size: 13px; border-radius: 10px;
  padding: 11px 0; cursor: pointer;
}
.quick-btn:hover { background: rgba(20, 73, 58, 0.12); }
.auth-footnote { margin-top: 12px; font-size: 11.5px; color: #9aa8a0; text-align: center; }
.auth-bottom-note {
  margin-top: 16px; padding-top: 14px; border-top: 1px solid #e4ece8;
  font-size: 11.5px; color: #9aa8a0; text-align: center;
}

@media (max-width: 900px) {
  .login-page { flex-direction: column; }
  .intro-pane { padding: 28px 24px 8px; }
  .hero-title { font-size: 44px; letter-spacing: 3px; }
  .hero-sub { font-size: 15px; }
  .auth-pane { min-width: 0; padding: 20px 16px 40px; }
}
</style>
