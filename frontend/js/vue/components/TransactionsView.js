import { ref, onMounted, watch } from 'vue'
import { useStore } from '../store/index.js'
import { formatCurrency } from '../utils/formatters.js'
import AddTransactionModal from './AddTransactionModal.js'

export default {
  name: 'TransactionsView',
  components: { AddTransactionModal },
  emits: ['transaction-changed'],
  setup(props, { emit }) {
    const { state, actions } = useStore()
    const transactions = ref([])
    const total = ref(0)
    const page = ref(1)
    const typeFilter = ref('')
    const startDate = ref('')
    const endDate = ref('')
    const perPage = 20

    const load = async () => {
      if (!state.currentLedgerId) {
        transactions.value = []
        return
      }
      const data = await actions.fetchTransactions({
        type: typeFilter.value,
        start_date: startDate.value,
        end_date: endDate.value,
        limit: perPage,
        offset: (page.value - 1) * perPage
      })
      transactions.value = data?.transactions || []
      total.value = data?.total || 0
    }

    onMounted(load)
    watch(() => [state.currentLedgerId, state.currentAccountId, page, typeFilter, startDate, endDate], load, { deep: true })
    watch(() => state.dashboardRefreshTrigger, load)

    const totalPages = () => Math.ceil(total.value / perPage) || 1
    const goToPage = (p) => { page.value = p }

    const showAddModal = ref(false)
    const editingTransaction = ref(null)
    const selectedIds = ref([])

    const handleAddSubmitted = () => {
      showAddModal.value = false
      editingTransaction.value = null
      load()
      emit('transaction-changed')
    }
    const handleCloseModal = () => {
      showAddModal.value = false
      editingTransaction.value = null
    }

    const onDeleteSuccess = () => {
      selectedIds.value = []
      load()
      emit('transaction-changed')
    }

    const toggleSelect = (id) => {
      const idx = selectedIds.value.indexOf(id)
      if (idx === -1) selectedIds.value = [...selectedIds.value, id]
      else selectedIds.value = selectedIds.value.filter((x) => x !== id)
    }
    const isSelected = (id) => selectedIds.value.includes(id)
    const selectAllOnPage = () => {
      if (selectedIds.value.length === transactions.value.length) {
        selectedIds.value = []
      } else {
        selectedIds.value = transactions.value.map((t) => t.id)
      }
    }
    const allSelectedOnPage = () => transactions.value.length > 0 && selectedIds.value.length === transactions.value.length

    const batchDelete = async () => {
      if (!selectedIds.value.length) return
      if (!confirm(`确定要删除所选 ${selectedIds.value.length} 条交易明细吗？`)) return
      await actions.deleteTransactions(selectedIds.value, onDeleteSuccess)
    }

    const editTransaction = async (t) => {
      const full = await actions.fetchTransaction(t.id)
      if (full) {
        editingTransaction.value = full
        showAddModal.value = true
      }
    }

    return {
      state,
      transactions,
      total,
      page,
      typeFilter,
      startDate,
      endDate,
      perPage,
      formatCurrency,
      totalPages,
      goToPage,
      load,
      showAddModal,
      editingTransaction,
      selectedIds,
      showAdd: () => { editingTransaction.value = null; showAddModal.value = true },
      handleAddSubmitted,
      handleCloseModal,
      deleteTransaction: (id) => actions.deleteTransaction(id, onDeleteSuccess),
      toggleSelect,
      isSelected,
      selectAllOnPage,
      allSelectedOnPage,
      batchDelete,
      editTransaction
    }
  },
  template: `
    <div id="transactions-view" class="view">
      <div class="toolbar">
        <div class="toolbar-left">
          <select v-model="typeFilter" class="select-control">
            <option value="">全部类型</option>
            <option value="开仓">开仓</option>
            <option value="平仓">平仓</option>
            <option value="分红">分红</option>
          </select>
          <input type="date" v-model="startDate" class="date-control">
          <span>至</span>
          <input type="date" v-model="endDate" class="date-control">
          <button class="btn btn-primary" @click="load">
            <span class="material-icons">search</span>
            查询
          </button>
        </div>
        <div class="toolbar-right">
          <button class="btn btn-danger" @click="batchDelete" :disabled="!selectedIds.length">
            <span class="material-icons">delete_sweep</span>
            批量删除 ({{ selectedIds.length }})
          </button>
          <button class="btn btn-success" @click="showAdd">
            <span class="material-icons">add</span>
            添加交易
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
                  <th>代码</th>
                  <th>名称</th>
                  <th>币种</th>
                  <th>价格</th>
                  <th>数量</th>
                  <th>金额</th>
                  <th>手续费</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="transactions.length === 0">
                  <td colspan="11" class="empty-message">暂无交易明细</td>
                </tr>
                <tr v-for="t in transactions" :key="t.id">
                  <td class="col-checkbox">
                    <input type="checkbox" :checked="isSelected(t.id)" @change="toggleSelect(t.id)">
                  </td>
                  <td>{{ t.date }}</td>
                  <td><span :class="['badge', 'badge-' + (t.type === '开仓' ? 'success' : t.type === '平仓' ? 'danger' : 'info')]">{{ t.type }}</span></td>
                  <td>{{ t.code }}</td>
                  <td>{{ t.name }}</td>
                  <td>{{ t.currency || 'CNY' }}</td>
                  <td>{{ formatCurrency(t.price) }}</td>
                  <td>{{ t.quantity }}</td>
                  <td>{{ formatCurrency(t.amount) }}</td>
                  <td>{{ formatCurrency(t.fee) }}</td>
                  <td class="actions">
                    <button class="btn-icon" @click="editTransaction(t)" title="编辑">
                      <span class="material-icons">edit</span>
                    </button>
                    <button class="btn-icon" @click="deleteTransaction(t.id)" title="删除">
                      <span class="material-icons">delete</span>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="totalPages() > 1" class="pagination">
            <button :disabled="page <= 1" @click="goToPage(page - 1)">上一页</button>
            <button
              v-for="i in totalPages()"
              :key="i"
              :class="{ active: page === i }"
              @click="goToPage(i)"
            >{{ i }}</button>
            <button :disabled="page >= totalPages()" @click="goToPage(page + 1)">下一页</button>
          </div>
        </div>
      </div>
      <AddTransactionModal
        :show="showAddModal"
        :edit-transaction="editingTransaction"
        @close="handleCloseModal"
        @submitted="handleAddSubmitted"
      />
    </div>
  `
}
