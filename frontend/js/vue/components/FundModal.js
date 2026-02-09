import { ref, watch } from 'vue'
import { useStore } from '../store/index.js'

export default {
  name: 'FundModal',
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
      amount: '',
      currency: 'CNY',
      description: ''
    })
    const loading = ref(false)
    const modalAccounts = ref([])

    watch(() => props.show, async (v) => {
      if (v) {
        const ledgerId = state.currentLedgerId || state.ledgers[0]?.id || ''
        const accounts = ledgerId ? await actions.fetchAccountsForLedger(parseInt(ledgerId)) : state.accounts
        modalAccounts.value = accounts
        form.value = {
          ledger_id: ledgerId,
          account_id: state.currentAccountId || accounts[0]?.id || '',
          type: '',
          date: new Date().toISOString().split('T')[0],
          amount: '',
          currency: 'CNY',
          description: ''
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
        const ok = await actions.createFundTransaction({
          ledger_id: parseInt(form.value.ledger_id),
          account_id: parseInt(form.value.account_id),
          type: form.value.type,
          date: form.value.date,
          amount: parseFloat(form.value.amount),
          currency: form.value.currency,
          description: form.value.description || ''
        })
        if (ok) {
          emit('close')
          emit('submitted')
        }
      } finally {
        loading.value = false
      }
    }

    return { state, form, modalAccounts, loading, handleSubmit }
  },
  template: `
    <div :class="['modal', { active: show }]">
      <div class="modal-content">
        <div class="modal-header">
          <h3>添加资金明细</h3>
          <button class="modal-close" @click="$emit('close')">
            <span class="material-icons">close</span>
          </button>
        </div>
        <div class="modal-body">
          <form @submit="handleSubmit">
            <div class="form-group">
              <label>账本</label>
              <select v-model="form.ledger_id" required>
                <option value="">选择账本</option>
                <option v-for="l in state.ledgers" :key="l.id" :value="l.id">{{ l.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>账户</label>
              <select v-model="form.account_id" required>
                <option value="">选择账户</option>
                <option v-for="a in modalAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>类型</label>
              <select v-model="form.type" required>
                <option value="">选择类型</option>
                <option value="本金投入">本金投入</option>
                <option value="本金撤出">本金撤出</option>
                <option value="收入">收入</option>
                <option value="支出">支出</option>
                <option value="内转">内转</option>
              </select>
            </div>
            <div class="form-group">
              <label>日期</label>
              <input type="date" v-model="form.date" required>
            </div>
            <div class="form-group">
              <label>金额</label>
              <input type="number" v-model="form.amount" step="0.01" required placeholder="0.00">
            </div>
            <div class="form-group">
              <label>币种</label>
              <select v-model="form.currency">
                <option value="CNY">CNY</option>
                <option value="USD">USD</option>
                <option value="HKD">HKD</option>
                <option value="EUR">EUR</option>
              </select>
            </div>
            <div class="form-group">
              <label>描述</label>
              <textarea v-model="form.description" rows="3" placeholder="添加描述..."></textarea>
            </div>
            <div class="form-actions">
              <button type="submit" class="btn btn-primary" :disabled="loading">保存</button>
              <button type="button" class="btn btn-outline" @click="$emit('close')">取消</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  `
}
