import { ref } from 'vue'

export default {
  name: 'AddCategoryModal',
  props: {
    show: Boolean
  },
  emits: ['close', 'create'],
  setup(props, { emit }) {
    const name = ref('')
    const description = ref('')
    const creating = ref(false)
    const displayError = ref('')

    const handleCreate = async () => {
      displayError.value = ''
      if (!name.value.trim()) {
        displayError.value = '请输入类别名称'
        return
      }
      creating.value = true
      try {
        await emit('create', {
          name: name.value.trim(),
          description: description.value.trim()
        })
        name.value = ''
        description.value = ''
        emit('close')
      } finally {
        creating.value = false
      }
    }

    const handleClose = () => {
      name.value = ''
      description.value = ''
      displayError.value = ''
      emit('close')
    }

    return {
      name,
      description,
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
          <h3>添加类别</h3>
          <button class="modal-close" type="button" @click="handleClose">
            <span class="material-icons">close</span>
          </button>
        </div>
        <div class="modal-body">
          <form @submit.prevent="handleCreate">
            <div class="form-group">
              <label>类别名称</label>
              <input
                v-model="name"
                type="text"
                placeholder="如：股票、基金、债券"
                required
              >
            </div>
            <div class="form-group">
              <label>类别描述（可选）</label>
              <input
                v-model="description"
                type="text"
                placeholder="请输入类别描述"
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
