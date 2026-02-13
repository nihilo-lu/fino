import { ref } from 'vue'

export default {
  name: 'AddAccountModal',
  props: {
    show: Boolean,
    currentLedgerId: { type: [Number, String], default: null }
  },
  emits: ['close', 'create'],
  setup(props, { emit }) {
    const name = ref('')
    const type = ref('资产')
    const creating = ref(false)
    const displayError = ref('')

    const types = ['资产', '收入', '支出', '权益']

    const handleCreate = async () => {
      displayError.value = ''
      const ledgerId = props.currentLedgerId != null ? parseInt(props.currentLedgerId) : null
      if (!ledgerId || !name.value.trim()) {
        displayError.value = ledgerId ? '请填写账户名称' : '请先选择账本'
        return
      }
      creating.value = true
      try {
        await emit('create', {
          ledgerId,
          name: name.value.trim(),
          type: type.value
        })
        name.value = ''
        emit('close')
      } finally {
        creating.value = false
      }
    }

    const handleClose = () => {
      name.value = ''
      displayError.value = ''
      emit('close')
    }

    return {
      name,
      type,
      types,
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
          <h3>添加账户</h3>
          <button class="modal-close" type="button" @click="handleClose">
            <span class="material-icons">close</span>
          </button>
        </div>
        <div class="modal-body">
          <form @submit.prevent="handleCreate">
            <div class="form-group">
              <label>账户名称</label>
              <input
                v-model="name"
                type="text"
                placeholder="请输入账户名称"
                required
              >
            </div>
            <div class="form-group">
              <label>账户类型</label>
              <select v-model="type">
                <option v-for="t in types" :key="t" :value="t">{{ t }}</option>
              </select>
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
