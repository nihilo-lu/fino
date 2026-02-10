

export default {
  name: 'LedgerSelectPage',
  props: {
    ledgers: Array,
    userName: String
  },
  emits: ['select-ledger', 'show-add-ledger-modal', 'logout'],
  setup(props, { emit }) {
    const handleSelectLedger = (ledger) => {
      emit('select-ledger', ledger.id)
    }

    const handleShowAddLedgerModal = () => {
      emit('show-add-ledger-modal')
    }

    return {
      handleSelectLedger,
      handleShowAddLedgerModal
    }
  },
  template: `
    <div id="ledger-select-page" class="page active ledger-select-page">
      <div class="ledger-select-container">
        <div class="ledger-select-card">
          <div class="fino-logo">
            <div class="logo-text">Fino</div>
            <div class="logo-tagline">Investment</div>
          </div>
          <p class="welcome-text">欢迎，{{ userName }}</p>
          <p class="select-hint">请选择要使用的账本</p>

          <div v-if="ledgers.length > 0" class="ledger-list">
            <div
              v-for="ledger in ledgers"
              :key="ledger.id"
              class="ledger-card"
              @click="handleSelectLedger(ledger)"
            >
              <span class="material-icons ledger-icon">book</span>
              <div class="ledger-info">
                <span class="ledger-name">{{ ledger.name }}</span>
                <span class="ledger-desc">{{ ledger.description || '无描述' }}</span>
              </div>
              <span class="material-icons arrow-icon">arrow_forward</span>
            </div>
          </div>

          <div v-else class="empty-ledgers">
            <span class="material-icons empty-icon">folder_open</span>
            <p>暂无账本</p>
            <p class="empty-hint">创建您的第一个账本开始使用</p>
          </div>

          <div class="create-ledger-section">
            <button type="button" class="btn btn-primary btn-block" @click="handleShowAddLedgerModal">
              <span class="material-icons">add</span>
              {{ ledgers.length > 0 ? '添加账本' : '创建账本' }}
            </button>
          </div>

          <div class="ledger-select-footer">
            <button type="button" class="btn-link" @click="$emit('logout')">
              退出登录
            </button>
          </div>
        </div>
      </div>
    </div>
  `
}
