import { ref, onMounted, computed } from 'vue'
import { useStore } from '../store/index.js'

export const Settings = {
  name: 'Settings',
  setup() {
    const { state, actions } = useStore()
    const activeTab = ref('profile')
    const loading = ref(false)
    const settingDefault = ref(null)

    const isDefaultLedger = (ledgerId) => state.user?.default_ledger_id === ledgerId

    const setDefaultLedger = async (ledgerId) => {
      settingDefault.value = ledgerId
      const result = await actions.setDefaultLedger(ledgerId)
      settingDefault.value = null
      if (result.success && window.$showToast) {
        window.$showToast('默认账本已更新', 'success')
      } else if (!result.success && window.$showToast) {
        window.$showToast(result.error || '设置失败', 'error')
      }
    }
    
    const tabs = computed(() => {
      const baseTabs = [
        { id: 'profile', label: '个人资料', icon: '🔐' },
        { id: 'ledgers', label: '账本', icon: '📚' },
        { id: 'accounts', label: '账户', icon: '🏦' },
        { id: 'currencies', label: '币种', icon: '💱' },
        { id: 'categories', label: '类别', icon: '📁' },
        { id: 'prices', label: '价格', icon: '📊' }
      ]
      
      if (state.isAdmin) {
        baseTabs.push(
          { id: 'users', label: '用户管理', icon: '👥' },
          { id: 'database', label: '数据库', icon: '🗄️' }
        )
      }
      
      return baseTabs
    })

    const switchTab = (tabId) => {
      activeTab.value = tabId
    }

    return {
      activeTab,
      tabs,
      loading,
      switchTab,
      isDefaultLedger,
      setDefaultLedger,
      settingDefault
    }
  },
  template: `
    <div id="settings-view" class="view">
      <div class="settings-hero">
        <span class="settings-pill">⚙️ 设置管理中心</span>
        <h2>⚙️ 系统设置</h2>
        <p>统一管理系统配置、数据源与业务基础信息</p>
        <div class="settings-metrics">
          <div class="settings-metric">
            <span>📚 账本</span>
            <strong>{{ state.ledgers.length }}</strong>
          </div>
          <div class="settings-metric">
            <span>🏦 账户</span>
            <strong>{{ state.accounts.length }}</strong>
          </div>
          <div class="settings-metric">
            <span>💱 币种</span>
            <strong>{{ state.currencies.length }}</strong>
          </div>
          <div class="settings-metric">
            <span>📁 类别</span>
            <strong>{{ state.categories.length }}</strong>
          </div>
        </div>
      </div>

      <div class="settings-tabs">
        <button 
          v-for="tab in tabs" 
          :key="tab.id"
          :class="['settings-tab', { active: activeTab === tab.id }]"
          @click="switchTab(tab.id)"
        >
          {{ tab.icon }} {{ tab.label }}
        </button>
      </div>

      <div class="settings-content">
        <div :class="['settings-panel', { active: activeTab === 'profile' }]" id="tab-profile">
          <div class="settings-section">
            <h3>👤 个人资料</h3>
            <p class="settings-subtitle">管理您的账户信息</p>
            <form id="profile-form">
              <div class="form-row">
                <div class="form-group">
                  <label>用户名</label>
                  <input type="text" :value="state.user?.username || ''" readonly>
                </div>
                <div class="form-group">
                  <label>邮箱</label>
                  <input type="email" required>
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label>昵称</label>
                  <input type="text" required>
                </div>
              </div>
              <div class="form-actions">
                <button type="submit" class="btn btn-primary">💾 保存修改</button>
              </div>
            </form>
          </div>
        </div>

        <div :class="['settings-panel', { active: activeTab === 'ledgers' }]" id="tab-ledgers">
          <div class="settings-section">
            <h3>📚 账本列表</h3>
            <form id="ledger-form" class="inline-form">
              <div class="form-group">
                <input type="text" id="new-ledger-name" placeholder="账本名称">
              </div>
              <div class="form-group">
                <input type="text" id="new-ledger-desc" placeholder="账本描述">
              </div>
              <button type="submit" class="btn btn-primary">
                <span class="material-icons">add</span>
                添加账本
              </button>
            </form>
            <div id="ledgers-list" class="items-list">
              <div v-for="ledger in state.ledgers" :key="ledger.id" class="item-card">
                <div class="item-info">
                  <span class="item-name">{{ ledger.name }}</span>
                  <span class="item-desc">{{ ledger.description || '无描述' }}</span>
                  <span v-if="isDefaultLedger(ledger.id)" class="badge-default">默认</span>
                </div>
                <div class="item-actions">
                  <button 
                    class="btn btn-sm btn-outline" 
                    title="设为默认账本"
                    :disabled="isDefaultLedger(ledger.id) || settingDefault === ledger.id"
                    @click="setDefaultLedger(ledger.id)"
                  >
                    {{ isDefaultLedger(ledger.id) ? '已默认' : '设为默认' }}
                  </button>
                  <button class="btn-icon" title="编辑">
                    <span class="material-icons">edit</span>
                  </button>
                  <button class="btn-icon" title="删除">
                    <span class="material-icons">delete</span>
                  </button>
                </div>
              </div>
              <p v-if="state.ledgers.length === 0" class="empty-message">暂无账本</p>
            </div>
          </div>
        </div>

        <div :class="['settings-panel', { active: activeTab === 'accounts' }]" id="tab-accounts">
          <div class="settings-section">
            <h3>🏦 账户列表</h3>
            <form id="account-form" class="inline-form">
              <div class="form-group">
                <select id="account-ledger-select">
                  <option value="">选择账本</option>
                  <option v-for="ledger in state.ledgers" :key="ledger.id" :value="ledger.id">
                    {{ ledger.name }}
                  </option>
                </select>
              </div>
              <div class="form-group">
                <input type="text" id="new-account-name" placeholder="账户名称">
              </div>
              <button type="submit" class="btn btn-primary">
                <span class="material-icons">add</span>
                添加账户
              </button>
            </form>
            <div id="accounts-list" class="items-list">
              <div v-for="account in state.accounts" :key="account.id" class="item-card">
                <div class="item-info">
                  <span class="item-name">{{ account.name }}</span>
                  <span class="item-desc">{{ account.type }} | {{ account.currency }}</span>
                </div>
                <div class="item-actions">
                  <button class="btn-icon" title="编辑">
                    <span class="material-icons">edit</span>
                  </button>
                  <button class="btn-icon" title="删除">
                    <span class="material-icons">delete</span>
                  </button>
                </div>
              </div>
              <p v-if="state.accounts.length === 0" class="empty-message">暂无账户</p>
            </div>
          </div>
        </div>

        <div :class="['settings-panel', { active: activeTab === 'currencies' }]" id="tab-currencies">
          <div class="settings-section">
            <h3>💱 币种列表</h3>
            <form id="currency-form" class="inline-form">
              <div class="form-group">
                <input type="text" id="currency-code" placeholder="代码 (如 SGD)" maxlength="3">
              </div>
              <div class="form-group">
                <input type="text" id="currency-name" placeholder="名称 (如 新加坡元)">
              </div>
              <div class="form-group">
                <input type="text" id="currency-symbol" placeholder="符号 (如 S$)">
              </div>
              <div class="form-group">
                <input type="number" id="currency-rate" placeholder="对人民币汇率" step="0.0001">
              </div>
              <button type="submit" class="btn btn-primary">
                <span class="material-icons">add</span>
                添加币种
              </button>
            </form>
            <div id="currencies-list" class="items-list">
              <div v-for="currency in state.currencies" :key="currency.id" class="item-card">
                <div class="item-info">
                  <span class="item-name">{{ currency.code }} - {{ currency.name }}</span>
                  <span class="item-desc">{{ currency.symbol }} | 汇率: {{ currency.exchange_rate }}</span>
                </div>
                <div class="item-actions">
                  <button class="btn-icon" title="删除">
                    <span class="material-icons">delete</span>
                  </button>
                </div>
              </div>
              <p v-if="state.currencies.length === 0" class="empty-message">暂无币种</p>
            </div>
          </div>
        </div>

        <div :class="['settings-panel', { active: activeTab === 'categories' }]" id="tab-categories">
          <div class="settings-section">
            <h3>📁 投资类别</h3>
            <form id="category-form" class="inline-form">
              <div class="form-group">
                <input type="text" id="category-name" placeholder="类别名称 (如 股票、基金、债券)">
              </div>
              <div class="form-group">
                <input type="text" id="category-desc" placeholder="类别描述">
              </div>
              <button type="submit" class="btn btn-primary">
                <span class="material-icons">add</span>
                添加类别
              </button>
            </form>
            <div id="categories-list" class="items-list">
              <div v-for="category in state.categories" :key="category.id" class="item-card">
                <div class="item-info">
                  <span class="item-name">{{ category.name }}</span>
                  <span class="item-desc">{{ category.description || '无描述' }}</span>
                </div>
                <div class="item-actions">
                  <button class="btn-icon" title="编辑">
                    <span class="material-icons">edit</span>
                  </button>
                  <button class="btn-icon" title="删除">
                    <span class="material-icons">delete</span>
                  </button>
                </div>
              </div>
              <p v-if="state.categories.length === 0" class="empty-message">暂无类别</p>
            </div>
          </div>
        </div>

        <div :class="['settings-panel', { active: activeTab === 'prices' }]" id="tab-prices">
          <div class="settings-section">
            <h3>📊 价格与汇率管理</h3>
            <div class="info-box">
              <div class="quick-action">
                <div class="quick-action-icon">🚀</div>
                <div class="quick-action-content">
                  <div class="quick-action-title">一键获取最新数据</div>
                  <div class="quick-action-desc">同时更新所有持仓价格与外币汇率</div>
                </div>
              </div>
              <button class="btn btn-primary" style="margin-top: 16px;">
                <span class="material-icons">refresh</span>
                🔄 一键获取（价格+汇率）
              </button>
            </div>
          </div>
        </div>

        <div v-if="state.isAdmin" :class="['settings-panel', { active: activeTab === 'users' }]" id="tab-users">
          <div class="settings-section">
            <h3>👥 用户管理</h3>
            <p class="settings-subtitle">管理系统用户账户与权限</p>
            <form id="add-user-form" class="inline-form">
              <div class="form-group">
                <input type="text" id="new-user-name" placeholder="登录名">
              </div>
              <div class="form-group">
                <input type="email" id="new-user-email" placeholder="邮箱">
              </div>
              <div class="form-group">
                <input type="password" id="new-user-password" placeholder="密码">
              </div>
              <div class="form-group">
                <label class="checkbox-label">
                  <input type="checkbox" id="new-user-admin">
                  <span>管理员</span>
                </label>
              </div>
              <button type="submit" class="btn btn-primary">
                <span class="material-icons">person_add</span>
                添加用户
              </button>
            </form>
            <div id="users-list" class="items-list">
              <p class="empty-message">用户列表</p>
            </div>
          </div>
        </div>

        <div v-if="state.isAdmin" :class="['settings-panel', { active: activeTab === 'database' }]" id="tab-database">
          <div class="settings-section">
            <h3>🗄️ 数据库设置</h3>
            <p class="settings-subtitle">配置数据存储方式与连接参数</p>
            <form id="database-form">
              <div class="form-group">
                <label>数据库类型</label>
                <select id="db-type">
                  <option value="sqlite">🗃️ SQLite（本地文件）</option>
                  <option value="postgresql">🖥️ PostgreSQL（远程/本地）</option>
                </select>
              </div>
              <div class="form-actions">
                <button type="button" class="btn btn-outline">🔌 测试连接</button>
                <button type="submit" class="btn btn-primary">💾 保存配置</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  `
}
