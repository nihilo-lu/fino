import { ref, onMounted, watch, computed } from 'vue'
import { useStore } from '../store/index.js'
import { formatCurrency } from '../utils/formatters.js'

export default {
  name: 'AnalysisView',
  setup() {
    const { state, actions } = useStore()
    const navReturn = ref('0.00')
    const simpleReturn = ref('0.00')
    const realizedPl = ref({ total_cny: 0, details: [] })

    const load = async () => {
      if (!state.currentLedgerId) return
      const data = await actions.fetchAnalysis()
      if (data) {
        navReturn.value = (data.nav_return != null ? (data.nav_return * 100).toFixed(2) : '0.00') + '%'
        simpleReturn.value = (data.simple_return != null ? (data.simple_return * 100).toFixed(2) : '0.00') + '%'
        realizedPl.value = data.realized_pl || { total_cny: 0, details: [] }
      }
    }

    const realizedPlTotalClass = computed(() => {
      const t = realizedPl.value.total_cny
      return t >= 0 ? 'profit-positive' : 'profit-negative'
    })

    const hasDetails = computed(() => (realizedPl.value.details || []).length > 0)

    onMounted(load)
    watch(() => [state.currentLedgerId, state.currentAccountId], load)

    return {
      state,
      navReturn,
      simpleReturn,
      realizedPl,
      realizedPlTotalClass,
      hasDetails,
      formatCurrency
    }
  },
  template: `
    <div id="analysis-view" class="view">
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-content">
            <span class="stat-label">净值法累计收益率</span>
            <span class="stat-value">{{ navReturn }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-content">
            <span class="stat-label">简单收益率</span>
            <span class="stat-value">{{ simpleReturn }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-content">
            <span class="stat-label">已实现损益（人民币）</span>
            <span :class="['stat-value', realizedPlTotalClass]">{{ formatCurrency(realizedPl.total_cny) }}</span>
          </div>
        </div>
      </div>
      <div class="chart-card">
        <div class="card-header"><h3>收益率走势</h3></div>
        <div class="card-body">
          <div class="chart-container">
            <div class="empty-state">
              <span class="material-icons">show_chart</span>
              <p>暂无收益数据</p>
            </div>
          </div>
        </div>
      </div>
      <div class="chart-card">
        <div class="card-header"><h3>已实现损益明细</h3></div>
        <div class="card-body">
          <div v-if="!hasDetails" class="empty-state">
            <span class="material-icons">receipt_long</span>
            <p>暂无已实现损益记录</p>
          </div>
          <div v-else class="table-responsive">
            <table class="data-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>代码</th>
                  <th>名称</th>
                  <th>账户</th>
                  <th>收入</th>
                  <th>成本</th>
                  <th>利润</th>
                  <th>报表币种损益</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in realizedPl.details" :key="i">
                  <td>{{ row['日期'] }}</td>
                  <td>{{ row['代码'] }}</td>
                  <td>{{ row['名称'] }}</td>
                  <td>{{ row['账户'] }}</td>
                  <td>{{ formatCurrency(row['收入']) }}</td>
                  <td>{{ formatCurrency(row['成本']) }}</td>
                  <td :class="(row['利润'] || 0) >= 0 ? 'profit-positive' : 'profit-negative'">{{ formatCurrency(row['利润']) }}</td>
                  <td :class="(row['报表币种损益'] ?? row['利润'] ?? 0) >= 0 ? 'profit-positive' : 'profit-negative'">{{ formatCurrency(row['报表币种损益'] ?? row['利润']) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `
}
