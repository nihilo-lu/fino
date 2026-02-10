import { ref, onMounted, watch } from 'vue'
import { useStore } from '../store/index.js'
import { formatCurrency } from '../utils/formatters.js'

export default {
  name: 'FundsView',
  props: {
    refreshTrigger: Number
  },
  emits: ['show-add-fund'],
  setup(props, { emit }) {
    const { state, actions } = useStore()
    const funds = ref([])
    const typeFilter = ref('')

    const load = async () => {
      if (!state.currentLedgerId) {
        funds.value = []
        return
      }
      const data = await actions.fetchFundTransactions({ type: typeFilter.value })
      funds.value = data?.fund_transactions || []
    }

    onMounted(load)
    watch(() => [state.currentLedgerId, state.currentAccountId, typeFilter], load, { deep: true })
    watch(() => props.refreshTrigger, load)

    return {
      state,
      funds,
      typeFilter,
      formatCurrency,
      showAdd: () => emit('show-add-fund')
    }
  },
  template: `
    <div id="funds-view" class="view">
      <div class="toolbar">
        <div class="toolbar-left">
          <select v-model="typeFilter" class="select-control">
            <option value="">全部类型</option>
            <option value="开仓">开仓</option>
            <option value="平仓">平仓</option>
            <option value="分红">分红</option>
            <option value="本金投入">本金投入</option>
            <option value="本金撤出">本金撤出</option>
            <option value="收入">收入</option>
            <option value="支出">支出</option>
            <option value="内转">内转</option>
          </select>
          <button class="btn btn-success" @click="showAdd">
            <span class="material-icons">add</span>
            添加资金明细
          </button>
        </div>
      </div>
      <div class="data-card">
        <div class="card-body">
          <div class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>类型</th>
                  <th>借方（账户-持仓/现金）</th>
                  <th>贷方（账户-持仓/现金）</th>
                  <th>金额</th>
                  <th>备注</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="funds.length === 0">
                  <td colspan="6" class="empty-message">暂无资金明细</td>
                </tr>
                <tr v-for="f in funds" :key="f.id">
                  <td>{{ f.date }}</td>
                  <td>{{ f.type }}</td>
                  <td>{{ f.debit_display || f.debit_accounts || '-' }}</td>
                  <td>{{ f.credit_display || f.credit_accounts || '-' }}</td>
                  <td>{{ formatCurrency(f.total_debit ?? f.total_credit ?? f.amount, f.currency) }}</td>
                  <td>{{ f.notes || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `
}
