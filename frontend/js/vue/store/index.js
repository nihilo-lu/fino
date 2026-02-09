import { reactive, computed } from 'vue'
import { apiFetch, apiGet, apiPost, apiDelete } from '../utils/api.js'

const API_BASE = '/api'

const state = reactive({
  user: null,
  isAuthenticated: false,
  ledgers: [],
  accounts: [],
  currentLedgerId: null,
  currentAccountId: null,
  toast: null,
  cloudreveEnabled: false,
  cloudreveBound: false,
  enabledPlugins: [],  // 已启用的插件 id 列表，用于控制 AI 按钮、网盘入口等
  pluginCenterEnabled: true  // 是否在设置中显示插件中心
})

const isAdmin = computed(() => (state.user?.roles || []).includes('admin'))

function setToast(fn) {
  state.toast = fn
}

function showToast(message, type = 'info') {
  if (state.toast) state.toast(message, type)
}

async function parseJson(response) {
  if (!response.ok) return null
  try {
    return await response.json()
  } catch {
    return null
  }
}

const actions = {
  setToast,
  showToast,

  async checkAuth() {
    try {
      const response = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' })
      if (response.ok) {
        const data = await response.json()
        const u = data.data || data
        if (u?.username) {
          state.user = { username: u.username, name: u.name || u.username, email: u.email, roles: u.roles || [], avatar: u.avatar }
          state.isAuthenticated = true
          return true
        }
      }
    } catch (e) {
      console.error('checkAuth error:', e)
    }
    state.user = null
    state.isAuthenticated = false
    return false
  },

  async login(username, password) {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
      credentials: 'include'
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      const u = data.data || data
      state.user = { username: u.username, name: u.name || u.username, email: u.email, roles: u.roles || [], avatar: u.avatar }
      state.isAuthenticated = true
      localStorage.setItem('user_data', JSON.stringify(state.user))
      return { success: true }
    }
    return { success: false, error: data?.error || '登录失败' }
  },

  async register(formData) {
    const payload = {
      email: formData.email,
      username: formData.username,
      password: formData.password,
      password_repeat: formData.password_confirm || formData.password_repeat,
      password_hint: formData.password_hint || ''
    }
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      return { success: true }
    }
    return { success: false, error: data?.error || '注册失败' }
  },

  async logout() {
    try {
      await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' })
    } catch (e) { /* ignore */ }
    state.user = null
    state.isAuthenticated = false
    state.ledgers = []
    state.accounts = []
    state.currentLedgerId = null
    state.currentAccountId = null
    state.enabledPlugins = []
    state.cloudreveEnabled = false
    state.cloudreveBound = false
    localStorage.removeItem('user_data')
    localStorage.removeItem('last_ledger_id')
  },

  async fetchLedgers() {
    if (!state.user) return
    const response = await apiFetch(`${API_BASE}/ledgers?username=${state.user.username}`)
    if (response.unauthorized) {
      showToast('登录已过期，请重新登录', 'error')
      state.isAuthenticated = false
      return
    }
    const data = await parseJson(response)
    if (data?.ledgers) {
      state.ledgers = data.ledgers
    }
  },

  tryRestoreLastLedger() {
    const lastId = localStorage.getItem('last_ledger_id')
    if (!lastId || !state.ledgers.length) return false
    const id = parseInt(lastId, 10)
    const exists = state.ledgers.some((l) => l.id === id)
    if (exists) {
      state.currentLedgerId = id
      return true
    }
    return false
  },

  async fetchAccounts() {
    if (!state.currentLedgerId) {
      state.accounts = []
      return
    }
    const response = await apiFetch(`${API_BASE}/accounts?ledger_id=${state.currentLedgerId}`)
    const data = await parseJson(response)
    if (data?.accounts) state.accounts = data.accounts
  },

  async fetchAccountsForLedger(ledgerId) {
    if (!ledgerId) return []
    const response = await apiFetch(`${API_BASE}/accounts?ledger_id=${ledgerId}`)
    const data = await parseJson(response)
    return data?.accounts || []
  },

  setCurrentLedger(ledgerId) {
    const id = ledgerId ? parseInt(ledgerId) : null
    state.currentLedgerId = id
    state.currentAccountId = null
    if (id) localStorage.setItem('last_ledger_id', String(id))
    this.fetchAccounts()
  },

  setCurrentAccount(accountId) {
    state.currentAccountId = accountId ? parseInt(accountId) : null
  },

  clearCurrentLedger() {
    state.currentLedgerId = null
    state.currentAccountId = null
    state.accounts = []
  },

  async fetchPortfolioStats() {
    if (!state.currentLedgerId) return null
    const params = { ledger_id: state.currentLedgerId }
    if (state.currentAccountId) params.account_id = state.currentAccountId
    const response = await apiFetch(`${API_BASE}/portfolio/stats?${new URLSearchParams(params)}`)
    const data = await parseJson(response)
    return data
  },

  async fetchPositions() {
    if (!state.currentLedgerId) return null
    const params = { ledger_id: state.currentLedgerId }
    if (state.currentAccountId) params.account_id = state.currentAccountId
    const response = await apiFetch(`${API_BASE}/positions?${new URLSearchParams(params)}`)
    return parseJson(response)
  },

  async fetchRecentTransactions() {
    if (!state.currentLedgerId) return null
    const params = { ledger_id: state.currentLedgerId, limit: 5 }
    if (state.currentAccountId) params.account_id = state.currentAccountId
    const response = await apiFetch(`${API_BASE}/transactions?${new URLSearchParams(params)}`)
    return parseJson(response)
  },

  async fetchTransactions(opts = {}) {
    if (!state.currentLedgerId) return null
    const params = { ledger_id: state.currentLedgerId, limit: opts.limit || 20, offset: opts.offset || 0 }
    if (state.currentAccountId) params.account_id = state.currentAccountId
    if (opts.type) params.type = opts.type
    if (opts.start_date) params.start_date = opts.start_date
    if (opts.end_date) params.end_date = opts.end_date
    const response = await apiFetch(`${API_BASE}/transactions?${new URLSearchParams(params)}`)
    return parseJson(response)
  },

  async deleteTransaction(id, onSuccess) {
    if (!confirm('确定要删除这条交易记录吗？')) return
    const response = await apiFetch(`${API_BASE}/transactions/${id}`, { method: 'DELETE' })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('删除成功', 'success')
      if (onSuccess) onSuccess()
    } else {
      showToast(data?.error || '删除失败', 'error')
    }
  },

  async fetchFundTransactions(opts = {}) {
    if (!state.currentLedgerId) return null
    const params = { ledger_id: state.currentLedgerId, limit: 50 }
    if (state.currentAccountId) params.account_id = state.currentAccountId
    if (opts.type) params.type = opts.type
    const response = await apiFetch(`${API_BASE}/fund-transactions?${new URLSearchParams(params)}`)
    return parseJson(response)
  },

  async createTransaction(transaction) {
    const response = await apiFetch(`${API_BASE}/transactions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(transaction)
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('交易记录添加成功', 'success')
      return true
    }
    showToast(data?.error || '添加失败', 'error')
    return false
  },

  async createFundTransaction(fund) {
    const response = await apiFetch(`${API_BASE}/fund-transactions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fund)
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('资金明细添加成功', 'success')
      return true
    }
    showToast(data?.error || '添加失败', 'error')
    return false
  },

  async fetchCategories() {
    const response = await apiFetch(`${API_BASE}/categories`)
    return parseJson(response)
  },

  async fetchAnalysis() {
    if (!state.currentLedgerId) return null
    const params = { ledger_id: state.currentLedgerId }
    if (state.currentAccountId) params.account_id = state.currentAccountId
    const response = await apiFetch(`${API_BASE}/analysis/returns?${new URLSearchParams(params)}`)
    const data = await parseJson(response)
    if (data?.cumulative_return != null) {
      return { nav_return: data.cumulative_return, simple_return: data.cumulative_return }
    }
    return data
  },

  async fetchToken() {
    const response = await apiFetch(`${API_BASE}/auth/token`)
    const data = await parseJson(response)
    return (data?.data?.token ?? data?.token) || ''
  },

  async generateToken() {
    const response = await apiFetch(`${API_BASE}/auth/token/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    const data = await parseJson(response)
    const token = (data?.data?.token ?? data?.token) || ''
    if (token) showToast('Token 生成成功', 'success')
    else showToast(data?.error || '生成失败', 'error')
    return token
  },

  async fetchPwaConfig() {
    const response = await fetch(`${API_BASE}/pwa/config`)
    const data = await parseJson(response)
    return data?.data || data
  },

  async fetchCheckUpdate() {
    const response = await apiFetch(`${API_BASE}/check-update`)
    const data = await parseJson(response)
    return data?.data || data
  },

  async updateProfile({ username, nickname, email }) {
    const response = await apiFetch(`${API_BASE}/auth/profile`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, nickname, email })
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      const u = data.data || data
      state.user = { ...state.user, username: u.username, name: u.name || u.username, email: u.email, avatar: u.avatar }
      showToast('资料已更新', 'success')
      return { success: true }
    }
    showToast(data?.error || '更新失败', 'error')
    return { success: false, error: data?.error }
  },

  async updatePassword({ current_password, new_password, new_password_repeat }) {
    const response = await apiFetch(`${API_BASE}/auth/password`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password, new_password, new_password_repeat })
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('密码已更新', 'success')
      return { success: true }
    }
    showToast(data?.error || '更新失败', 'error')
    return { success: false, error: data?.error }
  },

  async fetchUsers() {
    const response = await apiFetch(`${API_BASE}/auth/users`)
    const data = await parseJson(response)
    return data?.data?.users ?? data?.users ?? []
  },

  async addUser({ username, email, password, is_admin }) {
    const response = await apiFetch(`${API_BASE}/auth/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password, is_admin })
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('用户已添加', 'success')
      return true
    }
    showToast(data?.error || '添加失败', 'error')
    return false
  },

  async updateUser(username, { disabled, is_admin }) {
    const response = await apiFetch(`${API_BASE}/auth/users/${encodeURIComponent(username)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ disabled, is_admin })
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('已更新', 'success')
      return true
    }
    showToast(data?.error || '更新失败', 'error')
    return false
  },

  async deleteUser(username) {
    const response = await apiFetch(`${API_BASE}/auth/users/${encodeURIComponent(username)}`, { method: 'DELETE' })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('已删除', 'success')
      return true
    }
    showToast(data?.error || '删除失败', 'error')
    return false
  },

  async uploadAvatar(file) {
    const formData = new FormData()
    formData.append('avatar', file)
    const response = await fetch(`${API_BASE}/auth/avatar`, {
      method: 'POST',
      body: formData,
      credentials: 'include'
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      const url = data.data?.avatar
      if (url) state.user = { ...state.user, avatar: url }
      showToast('头像已更新', 'success')
      return { success: true, avatar: url }
    }
    showToast(data?.error || '上传失败', 'error')
    return { success: false, error: data?.error }
  },

  async savePwaConfig(pwa) {
    const response = await apiFetch(`${API_BASE}/pwa/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pwa)
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('PWA 配置已保存', 'success')
      return true
    }
    showToast(data?.error || '保存失败', 'error')
    return false
  },

  async fetchDatabaseConfig() {
    const response = await apiFetch(`${API_BASE}/database/config`)
    const data = await parseJson(response)
    return data?.data || data
  },

  async saveDatabaseConfig(cfg) {
    const response = await apiFetch(`${API_BASE}/database/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg)
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('数据库配置已保存，请重启应用生效', 'success')
      return true
    }
    showToast(data?.error || '保存失败', 'error')
    return false
  },

  async fetchAiConfig() {
    const response = await apiFetch(`${API_BASE}/ai/config`)
    const data = await parseJson(response)
    return data?.data || data
  },

  async saveAiConfig(cfg) {
    const response = await apiFetch(`${API_BASE}/ai/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg)
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('AI 配置已保存', 'success')
      return true
    }
    showToast(data?.error || '保存失败', 'error')
    return false
  },

  async fetchCloudreveConfig() {
    const response = await apiFetch(`${API_BASE}/cloudreve/config`)
    const data = await parseJson(response)
    const cfg = data?.data ?? data ?? { enabled: false }
    state.cloudreveEnabled = !!cfg.enabled
    return { enabled: !!cfg.enabled }
  },

  async saveCloudreveConfig(cfg) {
    const response = await apiFetch(`${API_BASE}/cloudreve/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg)
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('网盘配置已保存', 'success')
      return true
    }
    showToast(data?.error || '保存失败', 'error')
    return false
  },

  async fetchCloudreveStatus() {
    const response = await apiFetch(`${API_BASE}/cloudreve/status`)
    const data = await parseJson(response)
    const st = data?.data ?? data ?? { bound: false }
    state.cloudreveBound = !!st.bound
    return { bound: !!st.bound, cloudreve_url: st.cloudreve_url }
  },

  async verifyCloudreveServer(url) {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 15000)
    try {
      const response = await apiFetch(`${API_BASE}/cloudreve/verify?url=${encodeURIComponent(url)}`, {
        signal: controller.signal
      })
      if (response.unauthorized) return { valid: false, error: '请先登录' }
      const data = await parseJson(response)
      if (response.ok && data?.success) return data.data ?? data
      let errMsg = data?.error || '无法连接该服务器'
      if (errMsg === '无法连接该服务器' && typeof response.json === 'function') {
        try {
          const errBody = await response.json()
          if (errBody?.error) errMsg = errBody.error
        } catch (_) {}
      }
      return { valid: false, error: errMsg }
    } catch (e) {
      if (e?.name === 'AbortError') return { valid: false, error: '请求超时，请检查网络或服务器地址' }
      throw e
    } finally {
      clearTimeout(timeoutId)
    }
  },

  async fetchCloudreveCaptcha(url) {
    const response = await apiFetch(`${API_BASE}/cloudreve/captcha?url=${encodeURIComponent(url)}`)
    const data = await parseJson(response)
    return response.ok && data?.success ? (data.data ?? data) : null
  },

  async bindCloudreve({ url, email, password, captcha, ticket }) {
    const response = await apiFetch(`${API_BASE}/cloudreve/bind`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, email, password, captcha: captcha || '', ticket: ticket || '' })
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('绑定成功', 'success')
      return true
    }
    let errMsg = data?.error || '绑定失败'
    if (errMsg === '绑定失败' && typeof response.json === 'function') {
      try {
        const errBody = await response.json()
        if (errBody?.error) errMsg = errBody.error
      } catch (_) {}
    }
    showToast(errMsg, 'error')
    return false
  },

  async unbindCloudreve() {
    const response = await apiFetch(`${API_BASE}/cloudreve/unbind`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('已解绑', 'success')
      return true
    }
    showToast(data?.error || '解绑失败', 'error')
    return false
  },

  async fetchCloudreveFiles(uri, page = 0, pageSize = 50) {
    const params = new URLSearchParams({ uri: uri || 'cloudreve://my/', page: String(page), page_size: String(pageSize) })
    const response = await apiFetch(`${API_BASE}/cloudreve/files?${params}`)
    const data = await parseJson(response)
    if (!response.ok || !data?.success) return null
    const raw = data.data ?? data
    return { files: raw.files ?? raw.objects ?? [], parent: raw.parent ?? null }
  },

  async createCloudreveDownloadUrl(uri) {
    const response = await apiFetch(`${API_BASE}/cloudreve/download-url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri })
    })
    const data = await parseJson(response)
    return response.ok && data?.success ? data.data : null
  },

  async uploadCloudreveFile(file, parentUri) {
    const form = new FormData()
    form.append('file', file)
    form.append('uri', parentUri || 'cloudreve://my/')
    const response = await apiFetch(`${API_BASE}/cloudreve/upload`, { method: 'POST', body: form })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('上传成功', 'success')
      return true
    }
    showToast(data?.error || '上传失败', 'error')
    return false
  },

  async deleteCloudreveFile(uri) {
    const response = await apiFetch(`${API_BASE}/cloudreve/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri })
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('已删除', 'success')
      return true
    }
    showToast(data?.error || '删除失败', 'error')
    return false
  },

  async createCloudreveFolder(parentUri, name) {
    const response = await apiFetch(`${API_BASE}/cloudreve/mkdir`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parent_uri: parentUri || 'cloudreve://my/', name })
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('文件夹已创建', 'success')
      return true
    }
    showToast(data?.error || '创建失败', 'error')
    return false
  },

  async fetchPluginRegistry() {
    const response = await apiFetch(`${API_BASE}/plugins/registry`)
    const data = await parseJson(response)
    if (response.ok && data?.success) return data.plugins ?? data.data?.plugins ?? []
    return []
  },

  async fetchInstalledPlugins() {
    const response = await apiFetch(`${API_BASE}/plugins/installed`)
    if (response.unauthorized) return { installed: [], enabled: [] }
    const data = await parseJson(response)
    if (!data) return { installed: [], enabled: [] }
    const payload = (data.installed !== undefined || data.enabled !== undefined) ? data : { installed: [], enabled: [] }
    const result = {
      installed: payload.installed ?? [],
      enabled: payload.enabled ?? []
    }
    state.enabledPlugins = result.enabled
    return result
  },

  async enablePlugin(pluginId) {
    const response = await apiFetch(`${API_BASE}/plugins/installed/${encodeURIComponent(pluginId)}/enable`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('插件已启用，请刷新页面生效', 'success')
      return true
    }
    showToast(data?.error || '启用失败', 'error')
    return false
  },

  async disablePlugin(pluginId) {
    const response = await apiFetch(`${API_BASE}/plugins/installed/${encodeURIComponent(pluginId)}/disable`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('插件已禁用', 'success')
      return true
    }
    showToast(data?.error || '禁用失败', 'error')
    return false
  },

  async uninstallPlugin(pluginId) {
    const response = await apiFetch(`${API_BASE}/plugins/installed/${encodeURIComponent(pluginId)}/uninstall`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('插件已卸载，请重启应用生效', 'success')
      return true
    }
    showToast(data?.error || '卸载失败', 'error')
    return false
  },

  async fetchPluginCenterSetting() {
    const response = await apiFetch(`${API_BASE}/settings/plugin-center`)
    if (response.unauthorized) return { enabled: true }
    const data = await parseJson(response)
    const payload = data?.data ?? data ?? {}
    state.pluginCenterEnabled = payload.enabled !== false
    return { enabled: state.pluginCenterEnabled }
  },

  async savePluginCenterSetting(enabled) {
    const response = await apiFetch(`${API_BASE}/settings/plugin-center`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      state.pluginCenterEnabled = !!data.enabled
      showToast('已保存，请重启应用生效', 'success')
      return true
    }
    showToast(data?.error || '保存失败', 'error')
    return false
  },

  async installPlugin(pluginId) {
    const response = await apiFetch(`${API_BASE}/plugins/install/${encodeURIComponent(pluginId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('插件已安装，请重启应用生效', 'success')
      return true
    }
    showToast(data?.error || '安装失败', 'error')
    return false
  },

  async testDatabaseConnection(cfg) {
    const response = await apiFetch(`${API_BASE}/database/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg)
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      const res = data.data || data
      showToast(res?.message || (res?.ok ? '连接成功' : '连接失败'), res?.ok ? 'success' : 'error')
      return res
    }
    showToast(data?.error || '测试失败', 'error')
    return { ok: false, message: data?.error }
  },

  async resetToken() {
    if (!confirm('重置后旧 Token 将失效，确定继续？')) return ''
    const response = await apiFetch(`${API_BASE}/auth/token/reset`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    const data = await parseJson(response)
    const token = (data?.data?.token ?? data?.token) || ''
    if (token) showToast('Token 已重置', 'success')
    else showToast(data?.error || '重置失败', 'error')
    return token
  },

  async createLedger(name, description) {
    const response = await apiFetch(`${API_BASE}/ledgers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: state.user?.username, name, description, cost_method: 'FIFO' })
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('账本创建成功', 'success')
      return true
    }
    showToast(data?.error || '创建失败', 'error')
    return false
  },

  async deleteLedger(id) {
    if (!confirm('确定要删除这个账本吗？所有相关数据将被删除。')) return false
    const response = await apiFetch(`${API_BASE}/ledgers/${id}?username=${state.user?.username}`, { method: 'DELETE' })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('账本删除成功', 'success')
      return true
    }
    showToast(data?.error || '删除失败', 'error')
    return false
  },

  async createAccount(ledgerId, name, type, currency) {
    const response = await apiFetch(`${API_BASE}/accounts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ledger_id: ledgerId, name, type, currency })
    })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('账户创建成功', 'success')
      return true
    }
    showToast(data?.error || '创建失败', 'error')
    return false
  },

  async deleteAccount(id) {
    if (!confirm('确定要删除这个账户吗？所有相关数据将被删除。')) return false
    const response = await apiFetch(`${API_BASE}/accounts/${id}`, { method: 'DELETE' })
    const data = await parseJson(response)
    if (response.ok && data?.success) {
      showToast('账户删除成功', 'success')
      return true
    }
    showToast(data?.error || '删除失败', 'error')
    return false
  },

  drawPieChart(container, labels, values, title) {
    if (!container || labels.length === 0) return
    const canvas = document.createElement('canvas')
    canvas.width = container.clientWidth
    canvas.height = container.clientHeight - 20
    container.innerHTML = ''
    container.appendChild(canvas)
    const ctx = canvas.getContext('2d')
    const total = values.reduce((sum, v) => sum + v, 0)
    if (total === 0) return
    const centerX = canvas.width / 2
    const centerY = canvas.height / 2
    const radius = Math.min(centerX, centerY) - 40
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1']
    let startAngle = -Math.PI / 2
    labels.forEach((label, i) => {
      const sliceAngle = (values[i] / total) * 2 * Math.PI
      const endAngle = startAngle + sliceAngle
      ctx.beginPath()
      ctx.moveTo(centerX, centerY)
      ctx.arc(centerX, centerY, radius, startAngle, endAngle)
      ctx.closePath()
      ctx.fillStyle = colors[i % colors.length]
      ctx.fill()
      ctx.beginPath()
      ctx.moveTo(centerX, centerY)
      ctx.arc(centerX, centerY, radius * 0.6, 0, 2 * Math.PI)
      ctx.fillStyle = '#ffffff'
      ctx.fill()
      startAngle = endAngle
    })
    ctx.fillStyle = '#1e293b'
    ctx.font = '14px Inter, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(title, centerX, centerY)
  },

  drawBarChart(container, labels, values, title) {
    if (!container || labels.length === 0) return
    const canvas = document.createElement('canvas')
    canvas.width = container.clientWidth
    canvas.height = container.clientHeight - 20
    container.innerHTML = ''
    container.appendChild(canvas)
    const ctx = canvas.getContext('2d')
    const padding = { top: 20, right: 20, bottom: 60, left: 80 }
    const chartWidth = canvas.width - padding.left - padding.right
    const chartHeight = canvas.height - padding.top - padding.bottom
    const maxValue = Math.max(...values.map(Math.abs), 1)
    const barWidth = chartWidth / labels.length * 0.7
    const barGap = chartWidth / labels.length * 0.3
    const zeroY = padding.top + chartHeight / 2
    labels.forEach((label, i) => {
      const value = values[i]
      const normalizedHeight = (Math.abs(value) / maxValue) * (chartHeight / 2 - 10)
      const barX = padding.left + i * (barWidth + barGap) + barGap / 2
      const barY = value >= 0 ? zeroY - normalizedHeight : zeroY
      ctx.fillStyle = value >= 0 ? '#10b981' : '#ef4444'
      ctx.fillRect(barX, barY, barWidth, normalizedHeight)
      ctx.fillStyle = '#64748b'
      ctx.font = '11px Inter, sans-serif'
      ctx.textAlign = 'center'
      ctx.save()
      ctx.translate(barX + barWidth / 2, canvas.height - padding.bottom + 15)
      ctx.rotate(-Math.PI / 4)
      ctx.fillText(label, 0, 0)
      ctx.restore()
    })
    ctx.strokeStyle = '#e2e8f0'
    ctx.beginPath()
    ctx.moveTo(padding.left, zeroY)
    ctx.lineTo(canvas.width - padding.right, zeroY)
    ctx.stroke()
  }
}

export function useStore() {
  return { state, actions, isAdmin }
}
