import { ref, watch } from 'vue'

export default {
  name: 'LoginPage',
  props: {
    error: String
  },
  emits: ['login', 'show-register'],
  setup(props, { emit }) {
    const username = ref('')
    const password = ref('')
    const passwordVisible = ref(false)
    const displayError = ref('')
    const loading = ref(false)

    watch(() => props.error, (v) => { displayError.value = v || '' })

    const handleSubmit = async () => {
      displayError.value = ''
      loading.value = true
      try {
        await emit('login', { username: username.value, password: password.value })
      } finally {
        loading.value = false
      }
    }

    return {
      username,
      password,
      passwordVisible,
      displayError,
      loading,
      handleSubmit,
      showRegister: () => emit('show-register')
    }
  },
  template: `
    <div id="login-page" class="page active">
      <div class="login-container">
        <div class="login-card">
          <div class="fino-logo">
            <div class="logo-text">Fino</div>
            <div class="logo-tagline">Investment</div>
          </div>
          <form @submit.prevent="handleSubmit">
            <div class="form-group">
              <label for="username">用户名</label>
              <input type="text" id="username" v-model="username" required placeholder="请输入用户名">
            </div>
            <div class="form-group">
              <label for="password">密码</label>
              <div class="password-input-wrap">
                <input
                  :type="passwordVisible ? 'text' : 'password'"
                  id="password"
                  v-model="password"
                  required
                  placeholder="请输入密码"
                >
                <button
                  type="button"
                  class="password-toggle-btn"
                  :title="passwordVisible ? '隐藏密码' : '显示密码'"
                  @click="passwordVisible = !passwordVisible"
                  tabindex="-1"
                >
                  <span class="material-icons">{{ passwordVisible ? 'visibility_off' : 'visibility' }}</span>
                </button>
              </div>
            </div>
            <button type="submit" class="btn btn-primary btn-block" :disabled="loading">
              {{ loading ? '登录中...' : '登录' }}
            </button>
            <div v-if="displayError" class="error-message">{{ displayError }}</div>
          </form>
          <div class="login-footer">
            <p>还没有账号？<a href="#" @click.prevent="showRegister">立即注册</a></p>
          </div>
        </div>
      </div>
    </div>
  `
}
