import { ref } from 'vue'

export default {
  name: 'LedgerSelectPage',
  props: {
    ledgers: Array,
    userName: String
  },
  emits: ['select-ledger', 'create-ledger', 'logout'],
  setup(props, { emit }) {
    const newLedgerName = ref('')
    const newLedgerDesc = ref('')
    const creating = ref(false)
    const displayError = ref('')

    const handleSelectLedger = (ledger) => {
      emit('select-ledger', ledger.id)
    }

    const handleCreateLedger = async (e) => {
      e.preventDefault()
      displayError.value = ''
      if (!newLedgerName.value.trim()) {
        displayError.value = '请输入账本名称'
        return
      }
      creating.value = true
      try {
        await emit('create-ledger', {
          name: newLedgerName.value.trim(),
          description: newLedgerDesc.value.trim()
        })
        if (props.ledgers.length > 0) {
          newLedgerName.value = ''
          newLedgerDesc.value = ''
        }
      } finally {
        creating.value = false
      }
    }

    return {
      newLedgerName,
      newLedgerDesc,
      creating,
      displayError,
      handleSelectLedger,
      handleCreateLedger
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
            <h4>{{ ledgers.length > 0 ? '添加新账本' : '创建账本' }}</h4>
            <form @submit="handleCreateLedger">
              <div class="form-group">
                <input
                  v-model="newLedgerName"
                  type="text"
                  placeholder="账本名称"
                  required
                >
              </div>
              <div class="form-group">
                <input
                  v-model="newLedgerDesc"
                  type="text"
                  placeholder="账本描述（可选）"
                >
              </div>
              <button type="submit" class="btn btn-primary btn-block" :disabled="creating">
                {{ creating ? '创建中...' : (ledgers.length > 0 ? '添加账本' : '创建账本') }}
              </button>
              <div v-if="displayError" class="error-message">{{ displayError }}</div>
            </form>
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
