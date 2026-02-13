import { useStore } from '../store/index.js'

export default {
  name: 'Header',
  props: {
    pageTitle: String,
    currentLedgerName: { type: String, default: '' }
  },
  emits: ['toggle-sidebar'],
  setup() {
    const { state, actions } = useStore()
    return { state, actions }
  },
  template: `
    <header class="top-bar">
      <button class="btn-icon" @click="$emit('toggle-sidebar')">
        <span class="material-icons">menu</span>
      </button>
      <div class="page-title">
        <h2>{{ pageTitle }}</h2>
      </div>
      <div class="header-right">
        <div v-if="currentLedgerName" class="current-ledger" title="当前账本">
          <span class="material-icons current-ledger-icon">book</span>
          <span class="current-ledger-name">{{ currentLedgerName }}</span>
        </div>
        <div class="header-actions">
          <button type="button" class="btn-icon" :title="state.darkMode ? '切换到日间模式' : '切换到夜间模式'" @click="actions.toggleDarkMode()" aria-label="切换夜间模式">
            <span class="material-icons">{{ state.darkMode ? 'light_mode' : 'dark_mode' }}</span>
          </button>
        </div>
      </div>
    </header>
  `
}
