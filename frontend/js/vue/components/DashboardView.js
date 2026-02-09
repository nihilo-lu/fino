import { ref, onMounted, watch } from 'vue'
import { useStore } from '../store/index.js'
import { formatCurrency } from '../utils/formatters.js'

export default {
  name: 'DashboardView',
  emits: ['navigate'],
  setup(props, { emit }) {
    const { state, actions } = useStore()
    const stats = ref({
      total_cost_cny: 0,
      total_value_cny: 0,
      total_profit_cny: 0,
      profit_rate: 0,
      position_count: 0
    })
    const positions = ref([])
    const recentTransactions = ref([])

    const loadDashboard = async () => {
      if (!state.currentLedgerId) {
        stats.value = { total_cost_cny: 0, total_value_cny: 0, total_profit_cny: 0, profit_rate: 0, position_count: 0 }
        positions.value = []
        recentTransactions.value = []
        return
      }
      const data = await actions.fetchPortfolioStats()
      if (data) {
        stats.value = data.stats || stats.value
      }
      const posData = await actions.fetchPositions()
      positions.value = posData?.positions || []
      const transData = await actions.fetchRecentTransactions()
      recentTransactions.value = transData?.transactions || []
    }

    onMounted(loadDashboard)
    watch(
      () => [state.currentLedgerId, state.currentAccountId],
      loadDashboard
    )

    const drawCharts = () => {
      if (positions.value.length === 0) return
      const allocationChart = document.getElementById('allocation-chart')
      const profitChart = document.getElementById('profit-chart')
      if (!allocationChart || !profitChart) return

      const labels = positions.value.map(p => p.name)
      const values = positions.value.map(p => p.market_value_cny || 0)
      const profits = positions.value.map(p => (p.market_value_cny || 0) - (p.cost_cny || 0))

      actions.drawPieChart(allocationChart, labels, values, '市值 (CNY)')
      actions.drawBarChart(profitChart, labels, profits, '收益 (CNY)')
    }

    watch(() => positions.value, () => {
      setTimeout(drawCharts, 100)
    }, { deep: true })

    return {
      state,
      stats,
      positions,
      recentTransactions,
      formatCurrency,
      navigateTo: (page) => emit('navigate', page)
    }
  },
  template: `
    <div id="dashboard-view" class="view active">
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-icon blue">
            <span class="material-icons">payments</span>
          </div>
          <div class="stat-content">
            <span class="stat-label">总投入成本</span>
            <span class="stat-value">{{ formatCurrency(stats.total_cost_cny) }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon green">
            <span class="material-icons">show_chart</span>
          </div>
          <div class="stat-content">
            <span class="stat-label">当前市值</span>
            <span class="stat-value">{{ formatCurrency(stats.total_value_cny) }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div :class="['stat-icon', stats.profit_rate >= 0 ? 'green' : 'red']">
            <span class="material-icons">trending_up</span>
          </div>
          <div class="stat-content">
            <span class="stat-label">总收益</span>
            <span class="stat-value">{{ formatCurrency(stats.total_profit_cny) }}</span>
            <span :class="['stat-rate', stats.profit_rate >= 0 ? 'profit-positive' : 'profit-negative']">
              {{ (stats.profit_rate || 0).toFixed(2) }}%
            </span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon orange">
            <span class="material-icons">inventory_2</span>
          </div>
          <div class="stat-content">
            <span class="stat-label">持仓数量</span>
            <span class="stat-value">{{ stats.position_count || 0 }}</span>
          </div>
        </div>
      </div>

      <div class="charts-grid">
        <div class="chart-card">
          <div class="card-header"><h3>资产配置</h3></div>
          <div class="card-body">
            <div id="allocation-chart" class="chart-container">
              <div v-if="positions.length === 0" class="empty-state">
                <span class="material-icons">pie_chart</span>
                <p>暂无持仓数据</p>
              </div>
            </div>
          </div>
        </div>
        <div class="chart-card">
          <div class="card-header"><h3>持仓收益</h3></div>
          <div class="card-body">
            <div id="profit-chart" class="chart-container">
              <div v-if="positions.length === 0" class="empty-state">
                <span class="material-icons">bar_chart</span>
                <p>暂无持仓数据</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="data-card">
        <div class="card-header">
          <h3>最近交易</h3>
          <button class="btn btn-sm" @click="navigateTo('transactions')">
            查看全部
            <span class="material-icons">arrow_forward</span>
          </button>
        </div>
        <div class="card-body">
          <div class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>类型</th>
                  <th>代码</th>
                  <th>名称</th>
                  <th>价格</th>
                  <th>数量</th>
                  <th>金额</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="recentTransactions.length === 0">
                  <td colspan="7" class="empty-message">暂无交易记录</td>
                </tr>
                <tr v-for="t in recentTransactions" :key="t.id">
                  <td>{{ t.date }}</td>
                  <td>{{ t.type }}</td>
                  <td>{{ t.code }}</td>
                  <td>{{ t.name }}</td>
                  <td>{{ formatCurrency(t.price) }}</td>
                  <td>{{ t.quantity }}</td>
                  <td>{{ formatCurrency(t.amount) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `
}
