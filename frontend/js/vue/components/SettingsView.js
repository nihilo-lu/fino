import { ref, onMounted, watch, computed } from 'vue'
import { useStore } from '../store/index.js'

export default {
  name: 'SettingsView',
  setup() {
    const { state, actions } = useStore()
    const apiToken = ref('')
    const tokenVisible = ref(false)
    const pwaConfig = ref({
      name: '投资追踪器',
      short_name: '投资追踪',
      description: '投资组合追踪与收益分析工具',
      theme_color: '#E8A317',
      background_color: '#ffffff',
      display: 'standalone',
      icon_192: '/frontend/icons/icon-192.png',
      icon_512: '/frontend/icons/icon-512.png'
    })
    const pwaSaving = ref(false)
    const newLedgerName = ref('')
    const newLedgerDesc = ref('')
    const accountLedgerId = ref('')
    const newAccountName = ref('')
    const newAccountType = ref('股票')
    const newAccountCurrency = ref('CNY')
    const settingsAccounts = ref([])

    const displayAccounts = computed(() => {
      if (accountLedgerId.value === state.currentLedgerId) return state.accounts
      return settingsAccounts.value
    })

    const loadSettingsAccounts = async () => {
      if (accountLedgerId.value) {
        settingsAccounts.value = await actions.fetchAccountsForLedger(parseInt(accountLedgerId.value))
      } else {
        settingsAccounts.value = []
      }
    }

    const loadToken = async () => {
      apiToken.value = await actions.fetchToken()
    }

    const loadPwaConfig = async () => {
      const cfg = await actions.fetchPwaConfig()
      if (cfg) pwaConfig.value = { ...pwaConfig.value, ...cfg }
    }

    const handlePwaSave = async (e) => {
      e.preventDefault()
      pwaSaving.value = true
      const ok = await actions.savePwaConfig(pwaConfig.value)
      pwaSaving.value = false
      if (ok) loadPwaConfig()
    }

    const generateToken = async () => {
      const token = await actions.generateToken()
      if (token) apiToken.value = token
    }

    const resetToken = async () => {
      const token = await actions.resetToken()
      if (token) apiToken.value = token
    }

    const copyToken = () => {
      if (!apiToken.value) {
        actions.showToast('请先生成 Token', 'warning')
        return
      }
      navigator.clipboard.writeText(apiToken.value).then(() => {
        actions.showToast('Token 已复制到剪贴板', 'success')
      }).catch(() => actions.showToast('复制失败', 'error'))
    }

    const toggleTokenVisibility = () => {
      tokenVisible.value = !tokenVisible.value
    }

    const handleLedgerSubmit = async (e) => {
      e.preventDefault()
      if (!newLedgerName.value.trim()) {
        actions.showToast('请输入账本名称', 'warning')
        return
      }
      const ok = await actions.createLedger(newLedgerName.value.trim(), newLedgerDesc.value.trim())
      if (ok) {
        newLedgerName.value = ''
        newLedgerDesc.value = ''
        await actions.fetchLedgers()
      }
    }

    const handleAccountSubmit = async (e) => {
      e.preventDefault()
      if (!accountLedgerId.value || !newAccountName.value.trim()) {
        actions.showToast('请填写完整信息', 'warning')
        return
      }
      const ok = await actions.createAccount(
        parseInt(accountLedgerId.value),
        newAccountName.value.trim(),
        newAccountType.value,
        newAccountCurrency.value
      )
      if (ok) {
        newAccountName.value = ''
        await actions.fetchAccounts()
        await actions.fetchLedgers()
      }
    }

    const deleteLedger = async (id) => {
      const ok = await actions.deleteLedger(id)
      if (ok) await actions.fetchLedgers()
    }

    const deleteAccount = async (id) => {
      const ok = await actions.deleteAccount(id)
      if (ok) {
        await actions.fetchAccounts()
        await actions.fetchLedgers()
      }
    }

    onMounted(() => {
      loadToken()
      loadPwaConfig()
      actions.fetchLedgers()
      accountLedgerId.value = state.currentLedgerId || state.ledgers[0]?.id
      loadSettingsAccounts()
    })
    watch(() => state.ledgers, () => {
      if (state.ledgers.length && !accountLedgerId.value) accountLedgerId.value = state.currentLedgerId || state.ledgers[0]?.id
    }, { deep: true })
    watch(accountLedgerId, loadSettingsAccounts)

    return {
      displayAccounts,
      state,
      actions,
      apiToken,
      tokenVisible,
      pwaConfig,
      pwaSaving,
      loadPwaConfig,
      handlePwaSave,
      newLedgerName,
      newLedgerDesc,
      accountLedgerId,
      newAccountName,
      newAccountType,
      newAccountCurrency,
      generateToken,
      resetToken,
      copyToken,
      toggleTokenVisibility,
      handleLedgerSubmit,
      handleAccountSubmit,
      deleteLedger,
      deleteAccount
    }
  },
  template: `
    <div id="settings-view" class="view">
      <div class="form-card">
        <div class="card-header"><h3>📱 PWA 应用配置</h3></div>
        <div class="card-body">
          <p class="form-hint" style="margin-bottom: 16px;">自定义安装到主屏幕时的应用名称、图标和主题色</p>
          <form @submit="handlePwaSave">
            <div class="form-row">
              <div class="form-group">
                <label>应用名称</label>
                <input v-model="pwaConfig.name" type="text" placeholder="如：投资追踪器">
              </div>
              <div class="form-group">
                <label>短名称</label>
                <input v-model="pwaConfig.short_name" type="text" placeholder="如：投资追踪">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>应用描述</label>
                <input v-model="pwaConfig.description" type="text" placeholder="投资组合追踪与收益分析工具">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>主题色</label>
                <input v-model="pwaConfig.theme_color" type="text" placeholder="#E8A317">
              </div>
              <div class="form-group">
                <label>背景色</label>
                <input v-model="pwaConfig.background_color" type="text" placeholder="#ffffff">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>启动方式</label>
                <select v-model="pwaConfig.display">
                  <option value="standalone">独立应用（推荐）</option>
                  <option value="minimal-ui">最小浏览器 UI</option>
                  <option value="browser">浏览器</option>
                </select>
              </div>
              <div class="form-group">
                <label>图标 192×192</label>
                <input v-model="pwaConfig.icon_192" type="text" placeholder="/frontend/icons/icon-192.png">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>图标 512×512</label>
                <input v-model="pwaConfig.icon_512" type="text" placeholder="/frontend/icons/icon-512.png">
              </div>
            </div>
            <div class="form-actions">
              <button type="submit" class="btn btn-primary" :disabled="pwaSaving">
                {{ pwaSaving ? '保存中...' : '💾 保存 PWA 配置' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      <div class="form-card">
        <div class="card-header"><h3>API 访问令牌</h3></div>
        <div class="card-body">
          <div class="form-group">
            <label>Token 用于 API 调用（如脚本、第三方工具），退出登录和修改密码后仍有效</label>
            <div class="token-display">
              <input
                :type="tokenVisible ? 'text' : 'password'"
                v-model="apiToken"
                readonly
                class="token-input"
                :placeholder="apiToken ? '' : '点击「生成」创建 Token'"
              >
              <button v-if="!apiToken" type="button" class="btn btn-primary" @click="generateToken" title="生成">
                <span class="material-icons">add</span>
                生成
              </button>
              <button v-if="apiToken" type="button" class="btn btn-outline" @click="resetToken" title="重置">
                <span class="material-icons">refresh</span>
                重置
              </button>
              <button type="button" class="btn btn-outline" @click="copyToken" title="复制">
                <span class="material-icons">content_copy</span>
                复制
              </button>
              <button type="button" class="btn btn-outline" @click="toggleTokenVisibility" title="显示/隐藏">
                <span class="material-icons">{{ tokenVisible ? 'visibility_off' : 'visibility' }}</span>
              </button>
            </div>
            <p class="form-hint">Token 在设置中生成，永久有效。重置后旧 Token 失效。请勿泄露给他人。</p>
          </div>
        </div>
      </div>
      <div class="form-card">
        <div class="card-header"><h3>账本管理</h3></div>
        <div class="card-body">
          <form @submit="handleLedgerSubmit" class="inline-form">
            <div class="form-group">
              <input v-model="newLedgerName" type="text" placeholder="新账本名称">
            </div>
            <div class="form-group">
              <input v-model="newLedgerDesc" type="text" placeholder="账本描述">
            </div>
            <button type="submit" class="btn btn-primary">
              <span class="material-icons">add</span>
              添加账本
            </button>
          </form>
          <div class="items-list">
            <div v-for="ledger in state.ledgers" :key="ledger.id" class="item-card">
              <div class="item-info">
                <span class="item-name">{{ ledger.name }}</span>
                <span class="item-desc">{{ ledger.description || '无描述' }} | {{ ledger.cost_method }}</span>
              </div>
              <div class="item-actions">
                <button class="btn-icon" @click="deleteLedger(ledger.id)" title="删除">
                  <span class="material-icons">delete</span>
                </button>
              </div>
            </div>
            <p v-if="state.ledgers.length === 0" class="empty-message">暂无账本</p>
          </div>
        </div>
      </div>
      <div class="form-card">
        <div class="card-header"><h3>账户管理</h3></div>
        <div class="card-body">
          <form @submit="handleAccountSubmit" class="inline-form">
            <div class="form-group">
              <select v-model="accountLedgerId">
                <option value="">选择账本</option>
                <option v-for="l in state.ledgers" :key="l.id" :value="l.id">{{ l.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <input v-model="newAccountName" type="text" placeholder="账户名称">
            </div>
            <div class="form-group">
              <select v-model="newAccountType">
                <option value="股票">股票</option>
                <option value="基金">基金</option>
                <option value="债券">债券</option>
                <option value="期货">期货</option>
                <option value="现金">现金</option>
              </select>
            </div>
            <div class="form-group">
              <select v-model="newAccountCurrency">
                <option value="CNY">CNY</option>
                <option value="USD">USD</option>
                <option value="HKD">HKD</option>
                <option value="EUR">EUR</option>
              </select>
            </div>
            <button type="submit" class="btn btn-primary">
              <span class="material-icons">add</span>
              添加账户
            </button>
          </form>
          <div class="items-list">
            <div v-for="account in displayAccounts" :key="account.id" class="item-card">
              <div class="item-info">
                <span class="item-name">{{ account.name }}</span>
                <span class="item-desc">{{ account.type }} | {{ account.currency }}</span>
              </div>
              <div class="item-actions">
                <button class="btn-icon" @click="deleteAccount(account.id)" title="删除">
                  <span class="material-icons">delete</span>
                </button>
              </div>
            </div>
            <p v-if="displayAccounts.length === 0" class="empty-message">暂无账户</p>
          </div>
        </div>
      </div>
    </div>
  `
}
