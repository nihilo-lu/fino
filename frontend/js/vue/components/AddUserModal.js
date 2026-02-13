import { ref } from 'vue'

export default {
  name: 'AddUserModal',
  props: {
    show: Boolean,
    createUser: { type: Function, required: true }
  },
  emits: ['close', 'create'],
  setup(props, { emit }) {
    const username = ref('')
    const email = ref('')
    const password = ref('')
    const isAdmin = ref(false)
    const creating = ref(false)
    const displayError = ref('')

    const handleCreate = async () => {
      displayError.value = ''
      if (!username.value.trim()) {
        displayError.value = '请输入登录名'
        return
      }
      if (!password.value) {
        displayError.value = '请输入密码'
        return
      }
      if (password.value.length < 6) {
        displayError.value = '密码至少 6 位'
        return
      }
      creating.value = true
      try {
        const payload = {
          username: username.value.trim().toLowerCase(),
          email: email.value.trim(),
          password: password.value,
          is_admin: isAdmin.value
        }
        const ok = await props.createUser(payload)
        if (ok) {
          username.value = ''
          email.value = ''
          password.value = ''
          isAdmin.value = false
          emit('close')
        }
      } finally {
        creating.value = false
      }
    }

    const handleClose = () => {
      username.value = ''
      email.value = ''
      password.value = ''
      isAdmin.value = false
      displayError.value = ''
      emit('close')
    }

    return {
      username,
      email,
      password,
      isAdmin,
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
          <h3>添加用户</h3>
          <button class="modal-close" type="button" @click="handleClose">
            <span class="material-icons">close</span>
          </button>
        </div>
        <div class="modal-body">
          <form @submit.prevent="handleCreate">
            <div class="form-group">
              <label>登录名</label>
              <input
                v-model="username"
                type="text"
                placeholder="请输入登录名"
                required
              >
            </div>
            <div class="form-group">
              <label>邮箱</label>
              <input
                v-model="email"
                type="email"
                placeholder="选填"
              >
            </div>
            <div class="form-group">
              <label>密码</label>
              <input
                v-model="password"
                type="password"
                placeholder="至少 6 位"
                required
                minlength="6"
              >
            </div>
            <div class="form-group checkbox-group">
              <label class="checkbox-label">
                <input v-model="isAdmin" type="checkbox">
                <span>管理员</span>
              </label>
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
