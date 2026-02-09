import { ref, watch } from 'vue'

export default {
  name: 'RegisterPage',
  props: {
    error: String,
    success: String
  },
  emits: ['register', 'show-login'],
  setup(props, { emit }) {
    const email = ref('')
    const username = ref('')
    const password = ref('')
    const passwordConfirm = ref('')
    const passwordHint = ref('')
    const displayError = ref('')
    const displaySuccess = ref('')
    const loading = ref(false)

    watch(() => props.error, (v) => { displayError.value = v || '' })
    watch(() => props.success, (v) => { displaySuccess.value = v || '' })

    const handleSubmit = async () => {
      displayError.value = ''
      displaySuccess.value = ''
      if (password.value !== passwordConfirm.value) {
        displayError.value = '两次输入的密码不一致'
        return
      }
      loading.value = true
      try {
        await emit('register', {
          email: email.value,
          username: username.value,
          password: password.value,
          password_confirm: passwordConfirm.value,
          password_hint: passwordHint.value
        })
      } finally {
        loading.value = false
      }
    }

    return {
      email,
      username,
      password,
      passwordConfirm,
      passwordHint,
      displayError,
      displaySuccess,
      loading,
      handleSubmit,
      showLogin: () => emit('show-login')
    }
  },
  template: `
    <div id="register-page" class="page">
      <div class="login-container">
        <div class="login-card">
          <div class="fino-logo">
            <div class="logo-text">Fino</div>
            <div class="logo-tagline">Investment</div>
          </div>
          <form @submit.prevent="handleSubmit">
            <div class="form-group">
              <label for="reg-email">邮箱</label>
              <input type="email" id="reg-email" v-model="email" required placeholder="请输入邮箱">
            </div>
            <div class="form-group">
              <label for="reg-username">用户名</label>
              <input type="text" id="reg-username" v-model="username" required placeholder="请输入用户名">
            </div>
            <div class="form-group">
              <label for="reg-password">密码</label>
              <input type="password" id="reg-password" v-model="password" required placeholder="请输入密码">
            </div>
            <div class="form-group">
              <label for="reg-password-confirm">确认密码</label>
              <input type="password" id="reg-password-confirm" v-model="passwordConfirm" required placeholder="请再次输入密码">
            </div>
            <div class="form-group">
              <label for="reg-password-hint">密码提示</label>
              <input type="text" id="reg-password-hint" v-model="passwordHint" placeholder="用于找回密码的提示">
            </div>
            <button type="submit" class="btn btn-primary btn-block" :disabled="loading">
              {{ loading ? '注册中...' : '注册' }}
            </button>
            <div v-if="displayError" class="error-message">{{ displayError }}</div>
            <div v-if="displaySuccess" class="success-message">{{ displaySuccess }}</div>
          </form>
          <div class="login-footer">
            <p>已有账号？<a href="#" @click.prevent="showLogin">返回登录</a></p>
          </div>
        </div>
      </div>
    </div>
  `
}
