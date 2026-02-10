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

    const totalPages = () => Math.ceil(total.value / perPage) || 1
    const goToPage = (p) => { page.value = p }

    const showAddModal = ref(false)
    const handleAddSubmitted = () => {
      showAddModal.value = false
      load()
      emit('transaction-changed')
    }

    const onDeleteSuccess = () => {
      load()
      emit('transaction-changed')
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
      showAdd: () => { showAddModal.value = true },
      handleAddSubmitted,
      deleteTransaction: (id) => actions.deleteTransaction(id, onDeleteSuccess)
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
                  <td colspan="10" class="empty-message">暂无交易记录</td>
                </tr>
                <tr v-for="t in transactions" :key="t.id">
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
        @close="showAddModal = false"
        @submitted="handleAddSubmitted"
      />
    </div>
  `
}
