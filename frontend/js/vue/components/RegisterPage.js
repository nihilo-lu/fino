import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useStore } from '../store/index.js'

export default {
  name: 'RegisterPage',
  props: {
    error: String,
    success: String
  },
  emits: ['register', 'show-login'],
  setup(props, { emit }) {
    const { actions } = useStore()
    const email = ref('')
    const username = ref('')
    const password = ref('')
    const passwordConfirm = ref('')
    const passwordHint = ref('')
    const verificationCode = ref('')
    const displayError = ref('')
    const displaySuccess = ref('')
    const loading = ref(false)
    const requireEmailVerification = ref(false)
    const codeCooldown = ref(0)
    const codeSending = ref(false)
    let cooldownTimer = null

    const clearCooldownTimer = () => {
      if (cooldownTimer) {
        clearInterval(cooldownTimer)
        cooldownTimer = null
      }
    }

    const startCooldown = () => {
      codeCooldown.value = 60
      clearCooldownTimer()
      cooldownTimer = setInterval(() => {
        codeCooldown.value--
        if (codeCooldown.value <= 0) clearCooldownTimer()
      }, 1000)
    }

    onMounted(async () => {
      const settings = await actions.fetchRegisterSettings()
      requireEmailVerification.value = !!settings?.require_email_verification
    })
    onUnmounted(clearCooldownTimer)

    watch(() => props.error, (v) => { displayError.value = v || '' })
    watch(() => props.success, (v) => { displaySuccess.value = v || '' })

    const handleSendCode = async () => {
      const em = email.value?.trim()
      if (!em) {
        displayError.value = '请先填写邮箱'
        return
      }
      if (!/^[^@]+@[^@]+\.[^@]+$/.test(em)) {
        displayError.value = '邮箱格式不正确'
        return
      }
      displayError.value = ''
      codeSending.value = true
      const result = await actions.sendRegisterCode(em)
      codeSending.value = false
      if (result.success) {
        displaySuccess.value = result.message || '验证码已发送'
        startCooldown()
      } else {
        displayError.value = result.error || '发送失败'
      }
    }

    const handleSubmit = async () => {
      displayError.value = ''
      displaySuccess.value = ''
      if (password.value !== passwordConfirm.value) {
        displayError.value = '两次输入的密码不一致'
        return
      }
      if (requireEmailVerification.value && !verificationCode.value?.trim()) {
        displayError.value = '请输入邮箱验证码'
        return
      }
      loading.value = true
      try {
        const payload = {
          email: email.value,
          username: username.value,
          password: password.value,
          password_confirm: passwordConfirm.value,
          password_hint: passwordHint.value
        }
        if (requireEmailVerification.value) {
          payload.verification_code = verificationCode.value.trim()
        }
        await emit('register', payload)
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
      verificationCode,
      displayError,
      displaySuccess,
      loading,
      requireEmailVerification,
      codeCooldown,
      codeSending,
      handleSendCode,
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
            <div v-if="requireEmailVerification" class="form-group">
              <label for="reg-code">邮箱验证码</label>
              <div class="verification-code-row">
                <input type="text" id="reg-code" v-model="verificationCode" maxlength="6" placeholder="请输入验证码" autocomplete="one-time-code">
                <button type="button" class="btn btn-outline" :disabled="codeCooldown > 0 || codeSending || !email" @click="handleSendCode">
                  {{ codeSending ? '发送中...' : codeCooldown > 0 ? codeCooldown + ' 秒后重试' : '获取验证码' }}
                </button>
              </div>
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
