import { ref, watch, computed } from 'vue'
import { useStore } from '../store/index.js'

export default {
  name: 'AddTransactionView',
  emits: ['submitted', 'navigate'],
  setup(props, { emit }) {
    const { state, actions } = useStore()
    const form = ref({
      ledger_id: '',
      account_id: '',
      type: '',
      date: new Date().toISOString().split('T')[0],
      code: '',
      name: '',
      price: '',
      quantity: '',
      amount: '',
      fee: 0,
      category: '',
      notes: ''
    })
    const categories = ref([])
    const loading = ref(false)

    const amount = computed(() => {
      const p = parseFloat(form.value.price) || 0
      const q = parseFloat(form.value.quantity) || 0
      return (p * q).toFixed(2)
    })

    watch(amount, (v) => { form.value.amount = v })
    watch(() => state.currentLedgerId, (v) => { form.value.ledger_id = v || '' })
    watch(() => state.ledgers, (v) => {
      if (v.length && !form.value.ledger_id) form.value.ledger_id = state.currentLedgerId
    }, { deep: true })
    watch(() => state.accounts, (v) => {
      if (v.length && !form.value.account_id) form.value.account_id = state.currentAccountId || state.accounts[0]?.id
    }, { deep: true })

    const loadCategories = async () => {
      const data = await actions.fetchCategories()
      categories.value = data?.categories || []
    }

    const handleSubmit = async (e) => {
      e.preventDefault()
      loading.value = true
      try {
        const success = await actions.createTransaction({
          ...form.value,
          ledger_id: parseInt(form.value.ledger_id),
          account_id: parseInt(form.value.account_id),
          price: parseFloat(form.value.price),
          quantity: parseFloat(form.value.quantity),
          amount: parseFloat(form.value.amount || amount.value),
          fee: parseFloat(form.value.fee) || 0,
          category: form.value.category || null,
          notes: form.value.notes || ''
        })
        if (success) {
          emit('submitted')
          emit('navigate', 'transactions')
        }
      } finally {
        loading.value = false
      }
    }

    const initForm = () => {
      form.value.ledger_id = state.currentLedgerId || ''
      form.value.account_id = state.currentAccountId || state.accounts[0]?.id || ''
      form.value.date = new Date().toISOString().split('T')[0]
      loadCategories()
    }

    return {
      state,
      form,
      categories,
      loading,
      amount,
      handleSubmit,
      initForm
    }
  },
  mounted() {
    this.initForm()
  },
  template: `
    <div id="add-transaction-view" class="view">
      <div class="form-card">
        <div class="card-header"><h3>添加交易记录</h3></div>
        <div class="card-body">
          <form @submit="handleSubmit">
            <div class="form-row">
              <div class="form-group">
                <label>账本 *</label>
                <select v-model="form.ledger_id" required>
                  <option value="">选择账本</option>
                  <option v-for="l in state.ledgers" :key="l.id" :value="l.id">{{ l.name }}</option>
                </select>
              </div>
              <div class="form-group">
                <label>账户 *</label>
                <select v-model="form.account_id" required>
                  <option value="">选择账户</option>
                  <option v-for="a in state.accounts" :key="a.id" :value="a.id">{{ a.name }} ({{ a.currency }})</option>
                </select>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>交易类型 *</label>
                <select v-model="form.type" required>
                  <option value="">选择类型</option>
                  <option value="买入">买入</option>
                  <option value="卖出">卖出</option>
                  <option value="分红">分红</option>
                </select>
              </div>
              <div class="form-group">
                <label>交易日期 *</label>
                <input type="date" v-model="form.date" required>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>证券代码 *</label>
                <input type="text" v-model="form.code" required placeholder="如: SH.600519">
              </div>
              <div class="form-group">
                <label>证券名称 *</label>
                <input type="text" v-model="form.name" required placeholder="如: 贵州茅台">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>价格 *</label>
                <input type="number" v-model="form.price" step="0.01" required placeholder="0.00">
              </div>
              <div class="form-group">
                <label>数量 *</label>
                <input type="number" v-model="form.quantity" step="0.01" required placeholder="0">
              </div>
              <div class="form-group">
                <label>成交金额</label>
                <input type="number" :value="amount" readonly>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>手续费</label>
                <input type="number" v-model="form.fee" step="0.01">
              </div>
              <div class="form-group">
                <label>类别</label>
                <select v-model="form.category">
                  <option value="">选择类别</option>
                  <option v-for="c in categories" :key="c.name" :value="c.name">{{ c.name }}</option>
                </select>
              </div>
            </div>
            <div class="form-group">
              <label>备注</label>
              <textarea v-model="form.notes" rows="3" placeholder="添加备注..."></textarea>
            </div>
            <div class="form-actions">
              <button type="submit" class="btn btn-primary" :disabled="loading">
                <span class="material-icons">save</span>
                保存
              </button>
              <button type="reset" class="btn btn-outline">
                <span class="material-icons">clear</span>
                重置
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  `
}
