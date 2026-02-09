import { ref, onMounted, watch } from 'vue'
import { useStore } from '../store/index.js'

export default {
  name: 'AnalysisView',
  setup() {
    const { state, actions } = useStore()
    const navReturn = ref('0.00')
    const simpleReturn = ref('0.00')

    const load = async () => {
      if (!state.currentLedgerId) return
      const data = await actions.fetchAnalysis()
      if (data) {
        navReturn.value = (data.nav_return != null ? (data.nav_return * 100).toFixed(2) : '0.00') + '%'
        simpleReturn.value = (data.simple_return != null ? (data.simple_return * 100).toFixed(2) : '0.00') + '%'
      }
    }

    onMounted(load)
    watch(() => [state.currentLedgerId, state.currentAccountId], load)

    return { state, navReturn, simpleReturn }
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
    </div>
  `
}
