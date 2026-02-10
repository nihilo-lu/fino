import { ref } from 'vue'

export default {
  name: 'AddLedgerModal',
  props: {
    show: Boolean
  },
  emits: ['close', 'create'],
  setup(props, { emit }) {
    const newLedgerName = ref('')
    const newLedgerDesc = ref('')
    const creating = ref(false)
    const displayError = ref('')

    const handleCreate = async () => {
      displayError.value = ''
      if (!newLedgerName.value.trim()) {
        displayError.value = '请输入账本名称'
        return
      }
      creating.value = true
      try {
        await emit('create', {
          name: newLedgerName.value.trim(),
          description: newLedgerDesc.value.trim()
        })
        newLedgerName.value = ''
        newLedgerDesc.value = ''
        emit('close')
      } finally {
        creating.value = false
      }
    }

    const handleClose = () => {
      newLedgerName.value = ''
      newLedgerDesc.value = ''
      displayError.value = ''
      emit('close')
    }

    return {
      newLedgerName,
      newLedgerDesc,
      creating,
      displayError,
      handleCreate,
      handleClose
    }
  },
  template: `
    <div :class="['modal', { active: show }]" @click.self="handleClose">
      <div class="modal-content">
        <div class="modal-header">
          <h3>添加账本</h3>
          <button class="modal-close" @click="handleClose">
            <span class="material-icons">close</span>
          </button>
        </div>
        <div class="modal-body">
          <form @submit.prevent="handleCreate">
            <div class="form-group">
              <label>账本名称</label>
              <input
                v-model="newLedgerName"
                type="text"
                placeholder="请输入账本名称"
                required
              >
            </div>
            <div class="form-group">
              <label>账本描述（可选）</label>
              <input
                v-model="newLedgerDesc"
                type="text"
                placeholder="请输入账本描述"
              >
            </div>
            <div v-if="displayError" class="error-message">{{ displayError }}</div>
            <div class="form-actions">
              <button type="button" class="btn btn-outline" @click="handleClose">取消</button>
              <button type="submit" class="btn btn-primary" :disabled="creating">
                {{ creating ? '创建中...' : '创建' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  `
}
