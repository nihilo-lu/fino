import { ref, computed, onMounted, watch } from 'vue'
import { useStore } from '../store/index.js'
import { formatCurrency } from '../utils/formatters.js'

export default {
  name: 'AccountsView',
  emits: ['navigate'],
  setup(props, { emit }) {
    const { state, actions } = useStore()
    const selectedAccountId = ref(null)
    const collapsedGroups = ref({}) // { '资产': true, '收入': false, ... }  true=已折叠
    const accountBalances = ref([])
    const balancesLoading = ref(false)
    const accountStats = ref({ total_cost_cny: 0, total_value_cny: 0, total_profit_cny: 0, profit_rate: 0, position_count: 0 })
    const accountPositions = ref([])
    const accountTransactions = ref([])
    const accountFunds = ref([])
    const detailLoading = ref(false)

    const displayAccounts = computed(() => state.accounts || [])

    const ACCOUNT_TYPE_ORDER = ['资产', '负债', '收入', '支出', '权益']
    const accountsByType = computed(() => {
      const list = accountBalances.value || []
      const map = new Map()
      ACCOUNT_TYPE_ORDER.forEach(t => map.set(t, []))
      list.forEach(b => {
        const t = b.account_type || '其他'
        if (!map.has(t)) map.set(t, [])
        map.get(t).push(b)
      })
      return ACCOUNT_TYPE_ORDER.map(type => ({ type, accounts: map.get(type) || [] }))
        .concat(
          Array.from(map.entries())
            .filter(([type]) => !ACCOUNT_TYPE_ORDER.includes(type))
            .map(([type, accounts]) => ({ type, accounts }))
        )
        .filter(g => g.accounts.length > 0)
    })

    const selectedAccount = computed(() => {
      if (!selectedAccountId.value) return null
      return displayAccounts.value.find(a => a.id === selectedAccountId.value)
    })

    const isAssetAccount = computed(() => selectedAccount.value?.type === '资产')

    const loadBalances = async () => {
      if (!state.currentLedgerId) {
        accountBalances.value = []
        return
      }
      balancesLoading.value = true
      try {
        const list = await actions.fetchAccountBalances(state.currentLedgerId)
        accountBalances.value = list || []
      } finally {
        balancesLoading.value = false
      }
    }

    const loadAccountDetail = async (accountId) => {
      if (!state.currentLedgerId || accountId == null) {
        accountStats.value = { total_cost_cny: 0, total_value_cny: 0, total_profit_cny: 0, profit_rate: 0, position_count: 0 }
        accountPositions.value = []
        accountTransactions.value = []
        accountFunds.value = []
        return
      }
      detailLoading.value = true
      try {
        const bal = accountBalances.value.find(b => b.account_id === accountId)
        const isAsset = (bal?.account_type || displayAccounts.value.find(a => a.id === accountId)?.type) === '资产'
        const promises = [
          actions.fetchTransactions({ account_id: accountId, limit: 15, offset: 0 }),
          actions.fetchFundTransactions({ account_id: accountId, limit: 15 })
        ]
        if (isAsset) {
          promises.unshift(actions.fetchPortfolioStats(accountId))
          promises.splice(1, 0, actions.fetchPositions(accountId))
        }
        const results = await Promise.all(promises)
        let transRes, fundsRes
        if (isAsset) {
          accountStats.value = results[0]?.stats || results[0]?.data?.stats || accountStats.value
          accountPositions.value = results[1]?.positions ?? results[1]?.data?.positions ?? []
          transRes = results[2]
          fundsRes = results[3]
        } else {
          accountStats.value = { total_cost_cny: 0, total_value_cny: 0, total_profit_cny: 0, profit_rate: 0, position_count: 0 }
          accountPositions.value = []
          transRes = results[0]
          fundsRes = results[1]
        }
        accountTransactions.value = transRes?.transactions ?? transRes?.data?.transactions ?? []
        accountFunds.value = fundsRes?.fund_transactions ?? fundsRes?.data?.fund_transactions ?? []
      } finally {
        detailLoading.value = false
      }
    }

    const selectedAccountCash = computed(() => {
      if (!selectedAccountId.value) return null
      return accountBalances.value.find(b => b.account_id === selectedAccountId.value)
    })

    const balanceByCurrency = computed(() => {
      const list = accountPositions.value || []
      const byCur = new Map()
      list.forEach(p => {
        const cur = p.currency || p.currency_symbol || 'CNY'
        const cost = Number(p.cost) ?? 0
        const value = Number(p.market_value) ?? 0
        if (!byCur.has(cur)) byCur.set(cur, { currency: cur, cost: 0, market_value: 0 })
        const row = byCur.get(cur)
        row.cost += cost
        row.market_value += value
      })
      return Array.from(byCur.values()).map(r => ({ ...r, profit: r.market_value - r.cost }))
    })

    const totalCashBalance = computed(() => {
      return accountBalances.value.reduce((sum, b) => sum + (Number(b.balance) || 0), 0)
    })

    /** 格式化多币种现金余额展示 */
    const formatCashBalances = (b) => {
      const list = b?.cash_balances || []
      if (list.length === 0) return formatCurrency(b?.balance ?? 0)
      if (list.length === 1) return formatCurrency(list[0].balance, list[0].currency)
      return list.map(cb => formatCurrency(cb.balance, cb.currency)).join(' · ')
    }

    const goToTransactions = () => {
      if (selectedAccountId.value) actions.setCurrentAccount(selectedAccountId.value)
      emit('navigate', 'transactions')
    }

    const goToFunds = () => {
      if (selectedAccountId.value) actions.setCurrentAccount(selectedAccountId.value)
      emit('navigate', 'funds')
    }

    const selectAccountForDetail = (id) => {
      selectedAccountId.value = id
    }

    const toggleGroup = (type) => {
      collapsedGroups.value = { ...collapsedGroups.value, [type]: !collapsedGroups.value[type] }
    }

    const isGroupCollapsed = (type) => !!collapsedGroups.value[type]

    const getGroupSummary = (group) => {
      const total = group.accounts.reduce((sum, b) => sum + (Number(b.balance) || 0), 0)
      return { count: group.accounts.length, total }
    }

    onMounted(async () => {
      if (state.currentLedgerId) await actions.fetchAccounts()
      loadBalances()
      loadAccountDetail(null)
    })

    watch(selectedAccountId, (id) => {
      loadAccountDetail(id ?? null)
    })
    watch(() => state.currentLedgerId, () => {
      loadBalances()
    })
    watch(() => state.dashboardRefreshTrigger, () => {
      loadBalances()
      loadAccountDetail(selectedAccountId.value ?? null)
    })

    const assetTotalCash = computed(() => {
      const assetBalances = (accountBalances.value || []).filter(b => b.account_type === '资产')
      return assetBalances.reduce((sum, b) => sum + (Number(b.balance) || 0), 0)
    })

    return {
      state,
      actions,
      formatCurrency,
      formatCashBalances,
      displayAccounts,
      selectedAccountId,
      selectedAccount,
      accountBalances,
      accountsByType,
      collapsedGroups,
      balancesLoading,
      totalCashBalance,
      assetTotalCash,
      accountStats,
      accountPositions,
      selectedAccountCash,
      isAssetAccount,
      balanceByCurrency,
      accountTransactions,
      accountFunds,
      detailLoading,
      loadBalances,
      loadAccountDetail,
      goToTransactions,
      goToFunds,
      selectAccountForDetail,
      toggleGroup,
      isGroupCollapsed,
      getGroupSummary
    }
  },
  template: `
    <div id="accounts-view" class="accounts-view-new">
      <div v-if="!state.currentLedgerId" class="accounts-empty-state">
        <span class="material-icons">account_balance</span>
        <h3>请先选择账本</h3>
        <p>在顶部选择一个账本后即可查看账户信息</p>
      </div>

      <template v-else>
        <!-- 页面标题 -->
        <div class="accounts-page-header">
          <div class="accounts-header-left">
            <h1 class="accounts-main-title">账户管理</h1>
            <span class="accounts-subtitle">管理您的投资账户与资金流水</span>
          </div>
          <div v-if="displayAccounts.length > 0" class="accounts-total-badge">
            <span class="material-icons">account_balance_wallet</span>
            <span>{{ displayAccounts.length }} 个账户</span>
          </div>
        </div>

        <div class="accounts-layout-grid">
          <!-- 左侧：账户列表 -->
          <div class="accounts-sidebar">
            <div class="accounts-list-header">
              <h3>账户列表</h3>
              <span class="accounts-count">{{ accountBalances.length }}</span>
            </div>

            <div v-if="balancesLoading" class="accounts-list-loading">
              <div class="loading-spinner"></div>
              <p>加载账户信息...</p>
            </div>
            <div v-else-if="accountBalances.length === 0" class="accounts-list-empty">
              <span class="material-icons">inbox</span>
              <p>暂无账户</p>
            </div>
            <div v-else class="accounts-list">
              <template v-for="group in accountsByType" :key="group.type">
                <div class="account-group-block">
                  <div
                    class="account-group-title account-group-title-clickable"
                    :class="{ 'collapsed': isGroupCollapsed(group.type) }"
                    @click="toggleGroup(group.type)"
                  >
                    <span class="material-icons group-chevron">{{ isGroupCollapsed(group.type) ? 'expand_more' : 'expand_less' }}</span>
                    <span class="group-title-text">{{ group.type }}</span>
                    <span v-if="isGroupCollapsed(group.type)" class="group-summary">
                      {{ getGroupSummary(group).count }} 个账户 · {{ formatCurrency(getGroupSummary(group).total) }}
                    </span>
                  </div>
                  <template v-if="!isGroupCollapsed(group.type)">
                  <div
                    v-for="b in group.accounts"
                    :key="b.account_id"
                    :class="['account-card', { 'active': selectedAccountId === b.account_id }]"
                    @click="selectAccountForDetail(b.account_id)"
                  >
                    <div class="account-card-header">
                      <div class="account-avatar">{{ (b.account_name || '').charAt(0) }}</div>
                      <div class="account-info">
                        <div class="account-name">{{ b.account_name }}</div>
                        <div class="account-meta">
                          <span class="account-type">{{ b.account_type }}</span>
                        </div>
                      </div>
                      <div :class="['account-balance', { 'negative': (b.balance || 0) < 0 }]">
                        {{ formatCashBalances(b) }}
                      </div>
                    </div>
                    <div class="account-card-detail">
                      <div v-if="b.account_type === '资产'" class="account-detail-item">
                        <span class="detail-label">投入</span>
                        <span class="detail-value">{{ formatCurrency(b.total_invest || 0) }}</span>
                      </div>
                      <div class="account-detail-item">
                        <span class="detail-label">现金余额</span>
                        <span :class="['detail-value', { 'negative': (b.balance || 0) < 0 }]">
                          {{ formatCashBalances(b) }}
                        </span>
                      </div>
                      <div v-if="(b.cash_balances || []).length > 1" class="account-detail-item account-detail-currencies">
                        <span class="detail-label">按币种</span>
                        <span class="detail-value detail-value-multi">
                          <template v-for="(cb, i) in b.cash_balances" :key="cb.currency">
                            {{ i > 0 ? ' · ' : '' }}{{ formatCurrency(cb.balance, cb.currency) }}
                          </template>
                        </span>
                      </div>
                    </div>
                  </div>
                  <!-- 资产账户小计 -->
                  <div v-if="group.type === '资产' && group.accounts.length > 1" class="account-card account-total-card">
                    <div class="account-card-header">
                      <div class="account-avatar total-avatar">
                        <span class="material-icons">calculate</span>
                      </div>
                      <div class="account-info">
                        <div class="account-name">资产账户合计</div>
                        <div class="account-meta">
                          <span class="account-type">小计</span>
                        </div>
                      </div>
                      <div :class="['account-balance', { 'negative': assetTotalCash < 0 }]">
                        {{ formatCurrency(assetTotalCash) }}
                      </div>
                    </div>
                  </div>
                  </template>
                </div>
              </template>
            </div>
          </div>

          <!-- 右侧：账户详情 -->
          <div class="accounts-main">
            <template v-if="selectedAccountId">
              <!-- 账户头部 -->
              <div class="accounts-detail-header">
                <div class="detail-title-row">
                  <div class="detail-avatar">{{ (selectedAccount?.name || '').charAt(0) }}</div>
                  <div class="detail-info">
                    <h2>{{ selectedAccount?.name }}</h2>
                    <span class="detail-type">{{ selectedAccount?.type }}</span>
                  </div>
                </div>
                <div class="detail-actions">
                  <button class="btn btn-outline" @click="goToTransactions">
                    <span class="material-icons">receipt_long</span>
                    交易记录
                  </button>
                  <button class="btn btn-outline" @click="goToFunds">
                    <span class="material-icons">account_balance</span>
                    资金明细
                  </button>
                </div>
              </div>

              <!-- 统计卡片 -->
              <div v-if="detailLoading" class="accounts-detail-loading">
                <div class="loading-spinner"></div>
                <p>加载详情中...</p>
              </div>
              <template v-else>
                <!-- 现金余额（多币种） -->
                <div v-if="selectedAccountCash && (selectedAccountCash.cash_balances?.length || selectedAccountCash.balance)" class="detail-section">
                  <h3 class="detail-section-title">
                    <span class="material-icons">account_balance_wallet</span>
                    现金余额
                  </h3>
                  <div v-if="(selectedAccountCash.cash_balances || []).length === 0" class="currency-grid">
                    <div class="currency-card">
                      <div class="currency-header">
                        <span class="currency-name">CNY</span>
                        <span :class="['currency-profit', (selectedAccountCash.balance || 0) >= 0 ? 'positive' : 'negative']">
                          {{ formatCurrency(selectedAccountCash.balance, 'CNY') }}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div v-else class="currency-grid">
                    <div v-for="cb in selectedAccountCash.cash_balances" :key="cb.currency" class="currency-card">
                      <div class="currency-header">
                        <span class="currency-name">{{ cb.currency }}</span>
                        <span :class="['currency-profit', (cb.balance || 0) >= 0 ? 'positive' : 'negative']">
                          {{ formatCurrency(cb.balance, cb.currency) }}
                        </span>
                      </div>
                      <div class="currency-body">
                        <div class="currency-row">
                          <span class="currency-label">约合人民币</span>
                          <span class="currency-value">{{ formatCurrency(cb.balance_cny) }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 资产统计（仅资产账户） -->
                <div v-if="isAssetAccount" class="detail-cards-grid">
                  <div class="detail-card">
                    <div class="detail-card-icon blue">
                      <span class="material-icons">payments</span>
                    </div>
                    <div class="detail-card-content">
                      <div class="detail-card-label">总成本</div>
                      <div class="detail-card-value">{{ formatCurrency(accountStats.total_cost_cny) }}</div>
                    </div>
                  </div>
                  <div class="detail-card">
                    <div class="detail-card-icon green">
                      <span class="material-icons">trending_up</span>
                    </div>
                    <div class="detail-card-content">
                      <div class="detail-card-label">当前市值</div>
                      <div class="detail-card-value">{{ formatCurrency(accountStats.total_value_cny) }}</div>
                    </div>
                  </div>
                  <div class="detail-card">
                    <div :class="['detail-card-icon', (accountStats.total_profit_cny || 0) >= 0 ? 'green' : 'red']">
                      <span class="material-icons">
                        {{ (accountStats.total_profit_cny || 0) >= 0 ? 'add_circle' : 'remove_circle' }}
                      </span>
                    </div>
                    <div class="detail-card-content">
                      <div class="detail-card-label">浮动盈亏</div>
                      <div :class="['detail-card-value', (accountStats.total_profit_cny || 0) >= 0 ? 'positive' : 'negative']">
                        {{ formatCurrency(accountStats.total_profit_cny) }}
                      </div>
                    </div>
                  </div>
                  <div class="detail-card">
                    <div :class="['detail-card-icon', (accountStats.profit_rate || 0) >= 0 ? 'green' : 'red']">
                      <span class="material-icons">percent</span>
                    </div>
                    <div class="detail-card-content">
                      <div class="detail-card-label">收益率</div>
                      <div :class="['detail-card-value', (accountStats.profit_rate || 0) >= 0 ? 'positive' : 'negative']">
                        {{ (accountStats.profit_rate != null ? Number(accountStats.profit_rate).toFixed(2) : '0') }}%
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 按币种统计（仅资产账户） -->
                <div v-if="isAssetAccount && balanceByCurrency.length > 0" class="detail-section">
                  <h3 class="detail-section-title">
                    <span class="material-icons">currency_exchange</span>
                    币种分布
                  </h3>
                  <div class="currency-grid">
                    <div v-for="row in balanceByCurrency" :key="row.currency" class="currency-card">
                      <div class="currency-header">
                        <span class="currency-name">{{ row.currency }}</span>
                        <span :class="['currency-profit', row.profit >= 0 ? 'positive' : 'negative']">
                          {{ formatCurrency(row.profit, row.currency) }}
                        </span>
                      </div>
                      <div class="currency-body">
                        <div class="currency-row">
                          <span class="currency-label">成本</span>
                          <span class="currency-value">{{ formatCurrency(row.cost, row.currency) }}</span>
                        </div>
                        <div class="currency-row">
                          <span class="currency-label">市值</span>
                          <span class="currency-value">{{ formatCurrency(row.market_value, row.currency) }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 持仓明细（仅资产账户） -->
                <div v-if="isAssetAccount" class="detail-section">
                  <h3 class="detail-section-title">
                    <span class="material-icons">inventory_2</span>
                    持仓明细
                    <span v-if="accountPositions.length > 0" class="section-badge">{{ accountPositions.length }}</span>
                  </h3>
                  <div v-if="accountPositions.length === 0" class="detail-empty">
                    <span class="material-icons">inbox</span>
                    <p>暂无持仓</p>
                  </div>
                  <div v-else class="positions-table-container">
                    <table class="detail-table">
                      <thead>
                        <tr>
                          <th>代码</th>
                          <th>名称</th>
                          <th>数量</th>
                          <th>成本</th>
                          <th>市值</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="p in accountPositions" :key="(p.id != null ? p.id : (p.account_id || '') + '-' + p.code)">
                          <td class="table-code">{{ p.code }}</td>
                          <td>{{ p.name }}</td>
                          <td>{{ p.quantity }}</td>
                          <td>{{ formatCurrency(p.cost_cny) }}</td>
                          <td>{{ formatCurrency(p.market_value_cny) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- 最近交易（仅资产账户） -->
                <div v-if="isAssetAccount" class="detail-section">
                  <h3 class="detail-section-title">
                    <span class="material-icons">swap_horiz</span>
                    最近交易
                  </h3>
                  <div v-if="accountTransactions.length === 0" class="detail-empty">
                    <span class="material-icons">inbox</span>
                    <p>暂无交易记录</p>
                  </div>
                  <div v-else>
                    <table class="detail-table">
                      <thead>
                        <tr>
                          <th>日期</th>
                          <th>类型</th>
                          <th>标的</th>
                          <th>金额</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="t in accountTransactions" :key="t.id">
                          <td>{{ t.date }}</td>
                          <td>
                            <span :class="['table-badge', t.type === '开仓' ? 'success' : t.type === '平仓' ? 'danger' : 'neutral']">
                              {{ t.type }}
                            </span>
                          </td>
                          <td>{{ t.code }} {{ t.name }}</td>
                          <td>{{ formatCurrency(t.amount, t.currency) }}</td>
                        </tr>
                      </tbody>
                    </table>
                    <button type="button" class="detail-link-btn" @click="goToTransactions">
                      查看全部交易 <span class="material-icons">arrow_forward</span>
                    </button>
                  </div>
                </div>

                <!-- 最近资金流水 -->
                <div class="detail-section">
                  <h3 class="detail-section-title">
                    <span class="material-icons">account_balance_wallet</span>
                    最近资金流水
                  </h3>
                  <div v-if="accountFunds.length === 0" class="detail-empty">
                    <span class="material-icons">inbox</span>
                    <p>暂无资金流水</p>
                  </div>
                  <div v-else>
                    <table class="detail-table">
                      <thead>
                        <tr>
                          <th>日期</th>
                          <th>类型</th>
                          <th>金额</th>
                          <th>备注</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="f in accountFunds" :key="f.id">
                          <td>{{ f.date }}</td>
                          <td>{{ f.type }}</td>
                          <td>{{ formatCurrency(f.amount_cny ?? f.amount, f.currency || 'CNY') }}</td>
                          <td class="table-notes">{{ f.notes || '—' }}</td>
                        </tr>
                      </tbody>
                    </table>
                    <button type="button" class="detail-link-btn" @click="goToFunds">
                      查看全部资金明细 <span class="material-icons">arrow_forward</span>
                    </button>
                  </div>
                </div>
              </template>
            </template>

            <!-- 未选中账户时显示提示 -->
            <div v-else class="accounts-empty-detail">
              <span class="material-icons">touch_app</span>
              <h3>选择一个账户</h3>
              <p>从左侧列表中选择一个账户查看详细信息</p>
            </div>
          </div>
        </div>
      </template>
    </div>
  `
}
