export default {
  name: 'Header',
  props: {
    pageTitle: String,
    ledgers: Array,
    accounts: Array,
    currentLedgerId: [Number, String],
    currentAccountId: [Number, String]
  },
  emits: ['toggle-sidebar', 'ledger-change', 'account-change'],
  template: `
    <header class="top-bar">
      <button class="btn-icon" @click="$emit('toggle-sidebar')">
        <span class="material-icons">menu</span>
      </button>
      <div class="page-title">
        <h2>{{ pageTitle }}</h2>
      </div>
      <div class="header-actions">
        <select
          class="select-control"
          :value="currentLedgerId"
          @change="$emit('ledger-change', $event.target.value)"
        >
          <option value="">选择账本</option>
          <option v-for="l in ledgers" :key="l.id" :value="l.id">{{ l.name }}</option>
        </select>
        <select
          class="select-control"
          :value="currentAccountId"
          @change="$emit('account-change', $event.target.value)"
        >
          <option value="">选择账户</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }} ({{ a.currency }})</option>
        </select>
      </div>
    </header>
  `
}
