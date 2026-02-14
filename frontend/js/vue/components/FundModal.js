import { ref, watch, computed } from 'vue'
import { useStore } from '../store/index.js'

function parseNum(v) {
  if (v === '' || v == null) return 0
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : 0
}

export default {
  name: 'FundModal',
  props: {
    show: Boolean,
    editFund: { type: Object, default: null }
  },
  emits: ['close', 'submitted'],
  setup(props, { emit }) {
    const { state, actions } = useStore()
    const CURRENCIES = ['CNY', 'USD', 'HKD', 'EUR']
    const form = ref({
      ledger_id: '',
      type: '',
      date: new Date().toISOString().split('T')[0],
      notes: ''
    })
    const debitRows = ref([{ account_id: '', amount: '', currency: 'CNY' }])
    const creditRows = ref([{ account_id: '', amount: '', currency: 'CNY' }])
    const loading = ref(false)
    const modalAccounts = ref([])
    const rates = ref({})

    function getRate(currency) {
      return rates.value[currency || 'CNY'] ?? 1
    }
    function rowCny(row) {
      return parseNum(row.amount) * getRate(row.currency || 'CNY')
    }

    const totalDebit = computed(() =>
      debitRows.value.reduce((sum, r) => sum + parseNum(r.amount), 0)
    )
    const totalCredit = computed(() =>
      creditRows.value.reduce((sum, r) => sum + parseNum(r.amount), 0)
    )
    const totalDebitCny = computed(() =>
      debitRows.value.reduce((sum, r) => sum + rowCny(r), 0)
    )
    const totalCreditCny = computed(() =>
      creditRows.value.reduce((sum, r) => sum + rowCny(r), 0)
    )
    const diff = computed(() => totalDebit.value - totalCredit.value)
    const diffCny = computed(() => totalDebitCny.value - totalCreditCny.value)
    const mixedCurrencies = computed(() => {
      const all = [...debitRows.value, ...creditRows.value].filter(r => parseNum(r.amount) > 0)
      const codes = [...new Set(all.map(r => r.currency || 'CNY'))]
      return codes.length > 1
    })
    const isBalanced = computed(() => Math.abs(diff.value) < 0.005)
    const isBalancedCny = computed(() => Math.abs(diffCny.value) < 0.01)

    async function loadRates() {
      const date = form.value.date
      if (!date) return
      const r = await actions.fetchExchangeRatesAtDate(date)
      rates.value = r && typeof r === 'object' ? r : {}
    }

    watch(() => [props.show, props.editFund], async ([v, edit]) => {
      if (v) {
        // 确保账本列表已加载，避免打开弹窗时 ledgers 为空导致无账本可选
        if (!state.ledgers?.length) {
          await actions.fetchLedgers()
        }
        const ledgerId = state.currentLedgerId || state.ledgers?.[0]?.id || ''
        let accounts = []
        if (ledgerId) {
          accounts = await actions.fetchAccountsForLedger(parseInt(ledgerId, 10))
          // 若接口未返回账户且当前 store 里已有该账本的账户，用 store 作为回退（例如刚在设置里添加了账户）
          if (!accounts?.length && state.accounts?.length && state.currentLedgerId === parseInt(ledgerId, 10)) {
            accounts = state.accounts
          }
        } else {
          accounts = state.accounts || []
        }
        modalAccounts.value = Array.isArray(accounts) ? accounts : []
        const defaultAccountId = state.currentAccountId || modalAccounts.value[0]?.id || ''
        if (edit?.id) {
          form.value = {
            ledger_id: edit.ledger_id ?? ledgerId,
            type: edit.type || '',
            date: edit.date || new Date().toISOString().split('T')[0],
            notes: (edit.notes || '').trim()
          }
          const entries = edit.entries || []
          const mainCurrency = edit.currency || 'CNY'
          const debits = entries.filter((e) => e.side === 'debit').map((e) => ({
            account_id: e.account_id || '',
            amount: e.amount != null ? String(e.amount) : '',
            currency: e.currency || mainCurrency
          }))
          const credits = entries.filter((e) => e.side === 'credit').map((e) => ({
            account_id: e.account_id || '',
            amount: e.amount != null ? String(e.amount) : '',
            currency: e.currency || mainCurrency
          }))
          debitRows.value = debits.length ? debits : [{ account_id: defaultAccountId || '', amount: '', currency: 'CNY' }]
          creditRows.value = credits.length ? credits : [{ account_id: defaultAccountId || '', amount: '', currency: 'CNY' }]
        } else {
          form.value = {
            ledger_id: ledgerId,
            type: '',
            date: new Date().toISOString().split('T')[0],
            notes: ''
          }
          debitRows.value = [{ account_id: defaultAccountId || '', amount: '', currency: 'CNY' }]
          creditRows.value = [{ account_id: defaultAccountId || '', amount: '', currency: 'CNY' }]
        }
        await loadRates()
      }
    })
    watch(() => form.value.date, () => { if (props.show) loadRates() })

    function addDebitRow() {
      debitRows.value = [...debitRows.value, { account_id: '', amount: '', currency: 'CNY' }]
    }
    function removeDebitRow(index) {
      if (debitRows.value.length <= 1) return
      debitRows.value = debitRows.value.filter((_, i) => i !== index)
    }
    function addCreditRow() {
      creditRows.value = [...creditRows.value, { account_id: '', amount: '', currency: 'CNY' }]
    }
    function removeCreditRow(index) {
      if (creditRows.value.length <= 1) return
      creditRows.value = creditRows.value.filter((_, i) => i !== index)
    }

    function autoBalance() {
      const allDebit = debitRows.value.map((r, i) => ({ ...r, side: 'debit', index: i }))
      const allCredit = creditRows.value.map((r, i) => ({ ...r, side: 'credit', index: i }))
      const emptyDebit = allDebit.filter(r => !r.amount || parseNum(r.amount) <= 0)
      const emptyCredit = allCredit.filter(r => !r.amount || parseNum(r.amount) <= 0)
      const filledDebitCny = allDebit.filter(r => parseNum(r.amount) > 0).reduce((s, r) => s + rowCny(r), 0)
      const filledCreditCny = allCredit.filter(r => parseNum(r.amount) > 0).reduce((s, r) => s + rowCny(r), 0)
      if (emptyDebit.length === 1 && emptyCredit.length === 0) {
        const row = emptyDebit[0]
        const rate = getRate(row.currency || 'CNY')
        if (rate <= 0) return
        const amount = (totalCreditCny.value - filledDebitCny) / rate
        if (amount < 0) return
        debitRows.value[row.index].amount = amount.toFixed(2)
      } else if (emptyCredit.length === 1 && emptyDebit.length === 0) {
        const row = emptyCredit[0]
        const rate = getRate(row.currency || 'CNY')
        if (rate <= 0) return
        const amount = (totalDebitCny.value - filledCreditCny) / rate
        if (amount < 0) return
        creditRows.value[row.index].amount = amount.toFixed(2)
      } else {
        actions.showToast?.('请保留恰好一行为空（金额留空或 0），再点击自动平衡', 'info')
      }
    }

    const canAutoBalance = computed(() => {
      const emptyDebit = debitRows.value.filter(r => !r.amount || parseNum(r.amount) <= 0)
      const emptyCredit = creditRows.value.filter(r => !r.amount || parseNum(r.amount) <= 0)
      return (emptyDebit.length === 1 && emptyCredit.length === 0) || (emptyCredit.length === 1 && emptyDebit.length === 0)
    })

    const canSubmit = computed(() => {
      if (!form.value.type || !form.value.date) return false
      const hasDebit = debitRows.value.some(r => r.account_id && parseNum(r.amount) > 0)
      const hasCredit = creditRows.value.some(r => r.account_id && parseNum(r.amount) > 0)
      if (!hasDebit || !hasCredit) return false
      return mixedCurrencies.value ? isBalancedCny.value : isBalanced.value
    })

    const handleSubmit = async (e) => {
      e.preventDefault()
      if (!canSubmit.value) return
      loading.value = true
      try {
        const ledgerId = parseInt(form.value.ledger_id) || state.currentLedgerId || state.ledgers[0]?.id
        const entries = [
          ...debitRows.value
            .filter(r => r.account_id && parseNum(r.amount) > 0)
            .map(r => ({ account_id: parseInt(r.account_id), side: 'debit', amount: parseNum(r.amount), currency: r.currency || 'CNY' })),
          ...creditRows.value
            .filter(r => r.account_id && parseNum(r.amount) > 0)
            .map(r => ({ account_id: parseInt(r.account_id), side: 'credit', amount: parseNum(r.amount), currency: r.currency || 'CNY' }))
        ]
        const payload = {
          ledger_id: ledgerId,
          type: form.value.type,
          date: form.value.date,
          notes: (form.value.notes || '').trim(),
          entries
        }
        const isEdit = props.editFund?.id
        const ok = isEdit
          ? await actions.updateFundTransaction(props.editFund.id, payload)
          : await actions.createFundTransaction(payload)
        if (ok) {
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
      modalAccounts,
      debitRows,
      creditRows,
      loading,
      rates,
      parseNum,
      getRate,
      rowCny,
      totalDebit,
      totalCredit,
      totalDebitCny,
      totalCreditCny,
      diff,
      diffCny,
      isBalanced,
      isBalancedCny,
      mixedCurrencies,
      CURRENCIES,
      canSubmit,
      canAutoBalance,
      addDebitRow,
      removeDebitRow,
      addCreditRow,
      removeCreditRow,
      autoBalance,
      handleSubmit
    }
  },
  template: `
    <div :class="['modal', { active: show }]">
      <div class="modal-content fund-modal-content">
        <div class="modal-header">
          <h3>{{ editFund?.id ? '编辑资金明细' : '添加资金明细（借贷记账）' }}</h3>
          <button class="modal-close" type="button" @click="$emit('close')">
            <span class="material-icons">close</span>
          </button>
        </div>
        <div class="modal-body fund-modal-body">
          <form @submit="handleSubmit" class="fund-form">
            <div class="form-row form-row-2">
              <div class="form-group">
                <label>日期</label>
                <input type="date" v-model="form.date" required>
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
            </div>
            <div class="form-group">
              <label>备注</label>
              <input type="text" v-model="form.notes" placeholder="可选">
            </div>

            <div class="entries-section">
              <div class="entries-block entries-debit">
                <div class="entries-block-header">
                  <span class="entries-title">借方</span>
                  <button type="button" class="btn btn-sm btn-outline" @click="addDebitRow">
                    <span class="material-icons">add</span> 添加一行
                  </button>
                </div>
                <div class="entries-table-wrap">
                  <table class="entries-table">
                    <thead>
                      <tr>
                        <th class="col-account">账户</th>
                        <th class="col-amount">金额</th>
                        <th class="col-currency">币种</th>
                        <th class="col-rate">汇率</th>
                        <th class="col-cny">折合¥</th>
                        <th class="col-action"></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, i) in debitRows" :key="'d-' + i">
                        <td class="col-account">
                          <select v-model="row.account_id" class="input-select input-account">
                            <option value="">选择账户</option>
                            <option v-for="a in modalAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
                          </select>
                        </td>
                        <td class="col-amount">
                          <input type="number" v-model="row.amount" step="0.01" min="0" placeholder="0.00" class="input-amount">
                        </td>
                        <td class="col-currency">
                          <select v-model="row.currency" class="input-select input-currency">
                            <option v-for="c in CURRENCIES" :key="c" :value="c">{{ c }}</option>
                          </select>
                        </td>
                        <td class="col-rate">{{ (row.currency || 'CNY') === 'CNY' ? '1' : (getRate(row.currency) != null ? Number(getRate(row.currency)).toFixed(4) : '-') }}</td>
                        <td class="col-cny">{{ parseNum(row.amount) > 0 ? rowCny(row).toFixed(2) : '-' }}</td>
                        <td class="col-action">
                          <button type="button" class="btn-icon" @click="removeDebitRow(i)" :disabled="debitRows.length <= 1" title="删除行">
                            <span class="material-icons">remove_circle_outline</span>
                          </button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div class="entries-block entries-credit">
                <div class="entries-block-header">
                  <span class="entries-title">贷方</span>
                  <button type="button" class="btn btn-sm btn-outline" @click="addCreditRow">
                    <span class="material-icons">add</span> 添加一行
                  </button>
                </div>
                <div class="entries-table-wrap">
                  <table class="entries-table">
                    <thead>
                      <tr>
                        <th class="col-account">账户</th>
                        <th class="col-amount">金额</th>
                        <th class="col-currency">币种</th>
                        <th class="col-rate">汇率</th>
                        <th class="col-cny">折合¥</th>
                        <th class="col-action"></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, i) in creditRows" :key="'c-' + i">
                        <td class="col-account">
                          <select v-model="row.account_id" class="input-select input-account">
                            <option value="">选择账户</option>
                            <option v-for="a in modalAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
                          </select>
                        </td>
                        <td class="col-amount">
                          <input type="number" v-model="row.amount" step="0.01" min="0" placeholder="0.00" class="input-amount">
                        </td>
                        <td class="col-currency">
                          <select v-model="row.currency" class="input-select input-currency">
                            <option v-for="c in CURRENCIES" :key="c" :value="c">{{ c }}</option>
                          </select>
                        </td>
                        <td class="col-rate">{{ (row.currency || 'CNY') === 'CNY' ? '1' : (getRate(row.currency) != null ? Number(getRate(row.currency)).toFixed(4) : '-') }}</td>
                        <td class="col-cny">{{ parseNum(row.amount) > 0 ? rowCny(row).toFixed(2) : '-' }}</td>
                        <td class="col-action">
                          <button type="button" class="btn-icon" @click="removeCreditRow(i)" :disabled="creditRows.length <= 1" title="删除行">
                            <span class="material-icons">remove_circle_outline</span>
                          </button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div :class="['trial-balance', { balanced: mixedCurrencies ? isBalancedCny : isBalanced, unbalanced: mixedCurrencies ? !isBalancedCny : !isBalanced }]">
              <template v-if="mixedCurrencies">
                <div class="trial-row">
                  <span>借方折合¥</span>
                  <strong>{{ totalDebitCny.toFixed(2) }}</strong>
                </div>
                <div class="trial-row">
                  <span>贷方折合¥</span>
                  <strong>{{ totalCreditCny.toFixed(2) }}</strong>
                </div>
                <div class="trial-row trial-diff">
                  <span>差额（¥）</span>
                  <strong>{{ diffCny.toFixed(2) }}</strong>
                </div>
              </template>
              <template v-else>
                <div class="trial-row">
                  <span>借方合计</span>
                  <strong>{{ totalDebit.toFixed(2) }}</strong>
                </div>
                <div class="trial-row">
                  <span>贷方合计</span>
                  <strong>{{ totalCredit.toFixed(2) }}</strong>
                </div>
                <div class="trial-row trial-diff">
                  <span>差额</span>
                  <strong>{{ diff.toFixed(2) }}</strong>
                </div>
              </template>
              <div class="trial-status" v-if="totalDebit > 0 || totalCredit > 0">
                <span v-if="(mixedCurrencies ? isBalancedCny : isBalanced)" class="status-ok"><span class="material-icons">check_circle</span> 借贷平衡</span>
                <span v-else-if="mixedCurrencies" class="status-warn"><span class="material-icons">info</span> 请调整金额使折合人民币后平衡，或留空一行点「自动平衡」</span>
                <span v-else class="status-err"><span class="material-icons">error</span> 借贷不平衡，请调整金额</span>
              </div>
              <div class="trial-actions" v-if="mixedCurrencies">
                <button type="button" class="btn btn-sm btn-outline" @click="autoBalance" :disabled="!canAutoBalance" title="保留恰好一行为空时，按汇率自动计算该行金额使借贷平衡">
                  <span class="material-icons">balance</span> 自动平衡
                </button>
              </div>
            </div>

            <div class="form-actions">
              <button type="submit" class="btn btn-primary" :disabled="loading || !canSubmit">保存</button>
              <button type="button" class="btn btn-outline" @click="$emit('close')">取消</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  `
}
