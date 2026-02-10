import { ref, watch, computed } from 'vue'
import { useStore } from '../store/index.js'

export default {
  name: 'AddTransactionModal',
  props: {
    show: Boolean
  },
  emits: ['close', 'submitted'],
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
      currency: 'CNY',
      notes: ''
    })
    const categories = ref([])
    const currencies = ref([])
    const loading = ref(false)
    const modalAccounts = ref([])

    const amount = computed(() => {
      const p = parseFloat(form.value.price) || 0
      const q = parseFloat(form.value.quantity) || 0
      const fee = parseFloat(form.value.fee) || 0
      const base = p * q
      if (form.value.type === '买入') return (base + fee).toFixed(2)
      if (form.value.type === '卖出') return (base - fee).toFixed(2)
      return base.toFixed(2)
    })

    watch(amount, (v) => { form.value.amount = v })
    watch(() => props.show, async (v) => {
      if (v) {
        const ledgerId = state.currentLedgerId || state.ledgers[0]?.id || ''
        const accounts = ledgerId ? await actions.fetchAccountsForLedger(parseInt(ledgerId)) : state.accounts
        modalAccounts.value = accounts
        form.value.ledger_id = ledgerId
        form.value.account_id = state.currentAccountId || accounts[0]?.id || ''
        form.value.date = new Date().toISOString().split('T')[0]
        form.value.type = ''
        form.value.code = ''
        form.value.name = ''
        form.value.price = ''
        form.value.quantity = ''
        form.value.amount = ''
        form.value.fee = 0
        form.value.category = ''
        form.value.currency = 'CNY'
        form.value.notes = ''
        const [catData, currData] = await Promise.all([
          actions.fetchCategories(),
          actions.fetchCurrencies()
        ])
        categories.value = catData?.categories || []
        currencies.value = currData?.currencies || []
        if (categories.value.length && !form.value.category) {
          form.value.category = categories.value[0].name
        }
        if (currencies.value.length && !form.value.currency) {
          form.value.currency = currencies.value[0].code || 'CNY'
        }
      }
    })
    watch(() => form.value.ledger_id, async (ledgerId) => {
      modalAccounts.value = ledgerId ? await actions.fetchAccountsForLedger(parseInt(ledgerId)) : []
      form.value.account_id = modalAccounts.value[0]?.id || ''
    })

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
          currency: form.value.currency || 'CNY',
          notes: form.value.notes || ''
        })
        if (success) {
          emit('close')
          emit('submitted')
        }
      } finally {
        loading.value = false
      }
    }

    return {
      state,
      form,
      categories,
      currencies,
      modalAccounts,
      loading,
      amount,
      handleSubmit
    }
  },
  template: `
    <div :class="['modal', { active: show }]">
      <div class="modal-content modal-content-wide">
        <div class="modal-header">
          <h3>添加交易记录</h3>
          <button class="modal-close" @click="$emit('close')">
            <span class="material-icons">close</span>
          </button>
        </div>
        <div class="modal-body">
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
                  <option v-for="a in modalAccounts" :key="a.id" :value="a.id">{{ a.name }} ({{ a.currency }})</option>
                </select>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>类别</label>
                <select v-model="form.category">
                  <option value="">选择类别</option>
                  <option v-for="c in categories" :key="c.name" :value="c.name">{{ c.name }}</option>
                </select>
              </div>
              <div class="form-group">
                <label>币种</label>
                <select v-model="form.currency">
                  <option v-if="currencies.length === 0" value="CNY">CNY - 人民币</option>
                  <option v-for="cur in currencies" :key="cur.id" :value="cur.code">{{ cur.code }} - {{ cur.name }}</option>
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
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>手续费</label>
                <input type="number" v-model="form.fee" step="0.01" placeholder="0">
              </div>
              <div class="form-group">
                <label>成交金额</label>
                <input type="number" :value="amount" readonly>
              </div>
            </div>
            <div class="form-group">
              <label>备注</label>
              <textarea v-model="form.notes" rows="2" placeholder="添加备注..."></textarea>
            </div>
            <div class="form-actions">
              <button type="submit" class="btn btn-primary" :disabled="loading">
                <span class="material-icons">save</span>
                保存
              </button>
              <button type="button" class="btn btn-outline" @click="$emit('close')">取消</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  `
}
