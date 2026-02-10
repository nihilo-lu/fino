import { ref, onMounted, watch } from 'vue'
import { useStore } from '../store/index.js'
import { formatCurrency } from '../utils/formatters.js'

export default {
  name: 'FundsView',
  props: {
    refreshTrigger: Number
  },
  emits: ['show-add-fund', 'edit-fund'],
  setup(props, { emit }) {
    const { state, actions } = useStore()
    const funds = ref([])
    const typeFilter = ref('')
    const selectedIds = ref([])

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

    const toggleSelect = (id) => {
      const idx = selectedIds.value.indexOf(id)
      if (idx === -1) selectedIds.value = [...selectedIds.value, id]
      else selectedIds.value = selectedIds.value.filter((x) => x !== id)
    }
    const isSelected = (id) => selectedIds.value.includes(id)
    const selectAllOnPage = () => {
      if (selectedIds.value.length === funds.value.length) {
        selectedIds.value = []
      } else {
        selectedIds.value = funds.value.map((f) => f.id)
      }
    }
    const allSelectedOnPage = () => funds.value.length > 0 && selectedIds.value.length === funds.value.length

    const onDeleteSuccess = () => {
      selectedIds.value = []
      load()
    }
    const batchDelete = async () => {
      if (!selectedIds.value.length) return
      if (!confirm(`确定要删除所选 ${selectedIds.value.length} 条资金明细吗？`)) return
      await actions.deleteFundTransactions(selectedIds.value, onDeleteSuccess)
    }

    const editFund = (f) => emit('edit-fund', f.id)

    return {
      state,
      funds,
      typeFilter,
      selectedIds,
      formatCurrency,
      showAdd: () => emit('show-add-fund'),
      toggleSelect,
      isSelected,
      selectAllOnPage,
      allSelectedOnPage,
      batchDelete,
      editFund
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
          <button class="btn btn-danger" @click="batchDelete" :disabled="!selectedIds.length">
            <span class="material-icons">delete_sweep</span>
            批量删除 ({{ selectedIds.length }})
          </button>
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
                  <th class="col-checkbox">
                    <input type="checkbox" :checked="allSelectedOnPage()" @change="selectAllOnPage" title="全选本页">
                  </th>
                  <th>日期</th>
                  <th>类型</th>
                  <th>借方（账户-持仓/现金）</th>
                  <th>贷方（账户-持仓/现金）</th>
                  <th>金额</th>
                  <th>备注</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="funds.length === 0">
                  <td colspan="8" class="empty-message">暂无资金明细</td>
                </tr>
                <tr v-for="f in funds" :key="f.id">
                  <td class="col-checkbox">
                    <input type="checkbox" :checked="isSelected(f.id)" @change="toggleSelect(f.id)">
                  </td>
                  <td>{{ f.date }}</td>
                  <td>{{ f.type }}</td>
                  <td>{{ f.debit_display || f.debit_accounts || '-' }}</td>
                  <td>{{ f.credit_display || f.credit_accounts || '-' }}</td>
                  <td>{{ formatCurrency(f.total_debit ?? f.total_credit ?? f.amount, f.currency) }}</td>
                  <td>{{ f.notes || '-' }}</td>
                  <td class="actions">
                    <button class="btn-icon" @click="editFund(f)" title="编辑">
                      <span class="material-icons">edit</span>
                    </button>
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
