import { ref, onMounted, watch } from 'vue'
import { useStore } from '../store/index.js'
import { formatCurrency } from '../utils/formatters.js'

export default {
  name: 'PositionsView',
  setup() {
    const { state, actions } = useStore()
    const positions = ref([])

    const load = async () => {
      if (!state.currentLedgerId) {
        positions.value = []
        return
      }
      const data = await actions.fetchPositions()
      positions.value = data?.positions || []
    }

    onMounted(load)
    watch(() => [state.currentLedgerId, state.currentAccountId], load)

    return { state, positions, formatCurrency }
  },
  template: `
    <div id="positions-view" class="view">
      <div class="data-card">
        <div class="card-header"><h3>持仓列表</h3></div>
        <div class="card-body">
          <div class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th>持仓数量</th>
                  <th>成本价</th>
                  <th>当前价</th>
                  <th>市值(CNY)</th>
                  <th>收益</th>
                  <th>收益率</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="positions.length === 0">
                  <td colspan="8" class="empty-message">暂无持仓数据</td>
                </tr>
                <tr v-for="pos in positions" :key="pos.code">
                  <td>{{ pos.code }}</td>
                  <td>{{ pos.name }}</td>
                  <td>{{ pos.quantity }}</td>
                  <td>{{ formatCurrency(pos.avg_cost) }}</td>
                  <td>{{ formatCurrency(pos.current_price) }}</td>
                  <td>{{ formatCurrency(pos.market_value_cny) }}</td>
                  <td :class="[(pos.market_value_cny || 0) - (pos.cost_cny || 0) >= 0 ? 'profit-positive' : 'profit-negative']">
                    {{ formatCurrency((pos.market_value_cny || 0) - (pos.cost_cny || 0)) }}
                  </td>
                  <td :class="[pos.cost_cny ? ((pos.market_value_cny - pos.cost_cny) / pos.cost_cny * 100) >= 0 ? 'profit-positive' : 'profit-negative' : '']">
                    {{ pos.cost_cny ? (((pos.market_value_cny - pos.cost_cny) / pos.cost_cny * 100)).toFixed(2) : 0 }}%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `
}
