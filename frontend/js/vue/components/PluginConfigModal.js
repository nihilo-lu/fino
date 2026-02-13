import { ref, watch } from 'vue'
import { useStore } from '../store/index.js'

export default {
  name: 'PluginConfigModal',
  props: {
    show: Boolean,
    pluginId: String,
    pluginName: String
  },
  emits: ['close'],
  setup(props, { emit }) {
    const { state, actions, isAdmin } = useStore()
    const aiConfig = ref({
      base_url: 'https://api.openai.com/v1',
      api_key: '',
      model: 'gpt-4o-mini',
      show_thinking: true,
      context_messages: 20,
      avatar_url: '',
      system_prompt: ''
    })
    const aiConfigSaving = ref(false)
    const cloudreveConfig = ref({ enabled: false })
    const cloudreveStatus = ref({ bound: false })
    const cloudreveServerUrl = ref('')
    const cloudreveVerifyResult = ref(null)
    const cloudreveBindEmail = ref('')
    const cloudreveBindPassword = ref('')
    const cloudreveCaptcha = ref(null)
    const cloudreveCaptchaTicket = ref('')
    const cloudreveCaptchaInput = ref('')
    const cloudreveBinding = ref(false)
    const cloudreveVerifying = ref(false)
    const cloudreveConfigSaving = ref(false)

    const loadConfig = async () => {
      if (!props.pluginId) return
      if (props.pluginId === 'fino-ai-chat' && isAdmin.value) {
        const cfg = await actions.fetchAiConfig()
        if (cfg) aiConfig.value = { ...aiConfig.value, ...cfg }
      } else if (props.pluginId === 'fino-cloudreve') {
        const cfg = await actions.fetchCloudreveConfig()
        if (cfg) cloudreveConfig.value = cfg
        const st = await actions.fetchCloudreveStatus()
        if (st) cloudreveStatus.value = st
      }
    }

    watch(() => [props.show, props.pluginId], ([show, id]) => {
      if (show && id) {
        cloudreveVerifyResult.value = null
        cloudreveCaptcha.value = null
        loadConfig()
      }
    })

    const handleAiConfigSave = async (e) => {
      e.preventDefault()
      if (!isAdmin.value) return
      aiConfigSaving.value = true
      const ok = await actions.saveAiConfig(aiConfig.value)
      aiConfigSaving.value = false
      if (ok) loadConfig()
    }

    const handleCloudreveConfigSave = async (e) => {
      e.preventDefault()
      if (!isAdmin.value) return
      cloudreveConfigSaving.value = true
      const ok = await actions.saveCloudreveConfig(cloudreveConfig.value)
      cloudreveConfigSaving.value = false
      if (ok) loadConfig()
    }

    const handleCloudreveVerify = async () => {
      if (!cloudreveServerUrl.value.trim()) {
        actions.showToast('请输入服务器地址', 'warning')
        return
      }
      cloudreveVerifying.value = true
      cloudreveVerifyResult.value = null
      try {
        const result = await actions.verifyCloudreveServer(cloudreveServerUrl.value.trim())
        cloudreveVerifyResult.value = result
        if (result?.valid) actions.showToast('验证成功', 'success')
        else actions.showToast(result?.error || '无法连接该服务器', 'error')
      } catch (e) {
        actions.showToast('验证失败，请检查网络或服务器地址', 'error')
      } finally {
        cloudreveVerifying.value = false
      }
    }

    const handleCloudreveFetchCaptcha = async () => {
      if (!cloudreveServerUrl.value.trim()) {
        actions.showToast('请先验证服务器', 'warning')
        return
      }
      const cap = await actions.fetchCloudreveCaptcha(cloudreveServerUrl.value.trim())
      if (cap) {
        cloudreveCaptcha.value = cap
        cloudreveCaptchaTicket.value = cap.ticket || ''
        cloudreveCaptchaInput.value = ''
      }
    }

    const handleCloudreveBind = async (e) => {
      e.preventDefault()
      if (!cloudreveServerUrl.value.trim() || !cloudreveBindEmail.value.trim() || !cloudreveBindPassword.value) {
        actions.showToast('请填写完整', 'warning')
        return
      }
      cloudreveBinding.value = true
      const ok = await actions.bindCloudreve({
        url: cloudreveServerUrl.value.trim(),
        email: cloudreveBindEmail.value.trim(),
        password: cloudreveBindPassword.value,
        captcha: cloudreveCaptchaInput.value.trim(),
        ticket: cloudreveCaptchaTicket.value || ''
      })
      cloudreveBinding.value = false
      if (ok) {
        cloudreveBindEmail.value = ''
        cloudreveBindPassword.value = ''
        cloudreveCaptchaInput.value = ''
        cloudreveCaptcha.value = null
        loadConfig()
      }
    }

    const handleCloudreveUnbind = async () => {
      if (!confirm('确定要解绑 Cloudreve 吗？')) return
      const ok = await actions.unbindCloudreve()
      if (ok) loadConfig()
    }

    const handleCloudreveOpenLogin = () => {
      if (cloudreveVerifyResult.value?.login_url) {
        window.open(cloudreveVerifyResult.value.login_url, '_blank')
      }
    }

    const hasConfig = () => {
      return props.pluginId === 'fino-ai-chat' || props.pluginId === 'fino-cloudreve'
    }

    return {
      state,
      actions,
      isAdmin,
      aiConfig,
      aiConfigSaving,
      cloudreveConfig,
      cloudreveStatus,
      cloudreveServerUrl,
      cloudreveVerifyResult,
      cloudreveBindEmail,
      cloudreveBindPassword,
      cloudreveCaptcha,
      cloudreveCaptchaInput,
      cloudreveCaptchaTicket,
      cloudreveBinding,
      cloudreveVerifying,
      cloudreveConfigSaving,
      handleAiConfigSave,
      handleCloudreveConfigSave,
      handleCloudreveVerify,
      handleCloudreveFetchCaptcha,
      handleCloudreveBind,
      handleCloudreveUnbind,
      handleCloudreveOpenLogin,
      hasConfig
    }
  },
  template: `
    <div :class="['modal', { active: show }]" @click.self="$emit('close')">
      <div class="modal-content modal-content-wide plugin-config-modal">
        <div class="modal-header">
          <h3>{{ pluginName || '插件' }} 配置</h3>
          <button class="modal-close" @click="$emit('close')">
            <span class="material-icons">close</span>
          </button>
        </div>
        <div class="modal-body">
          <template v-if="pluginId === 'fino-ai-chat' && isAdmin">
            <p class="form-hint" style="margin-bottom: 16px;">配置 AI 聊天功能，支持 OpenAI 通用格式 API。</p>
            <form @submit="handleAiConfigSave">
              <div class="form-group">
                <label>API 地址</label>
                <input v-model="aiConfig.base_url" type="text" placeholder="https://api.openai.com/v1">
              </div>
              <div class="form-group">
                <label>API Key</label>
                <input v-model="aiConfig.api_key" type="password" placeholder="sk-xxx（留空保留原配置）">
              </div>
              <div class="form-group">
                <label>模型名称</label>
                <input v-model="aiConfig.model" type="text" placeholder="gpt-4o-mini">
              </div>
              <div class="form-group ai-config-thinking-option">
                <div class="thinking-option-card">
                  <span class="thinking-option-icon" aria-hidden="true">
                    <span class="material-icons">psychology</span>
                  </span>
                  <div class="thinking-option-body">
                    <span class="thinking-option-title">显示思维链</span>
                    <span class="thinking-option-desc">推理模型（如 o1/o3）会在回复中展示中间推理过程</span>
                  </div>
                  <label class="toggle-switch">
                    <input v-model="aiConfig.show_thinking" type="checkbox" aria-label="显示思维链">
                    <span class="toggle-slider"></span>
                  </label>
                </div>
              </div>
              <div class="form-group">
                <label>上下文记忆条数</label>
                <input v-model.number="aiConfig.context_messages" type="number" min="1" max="100" placeholder="20">
              </div>
              <div class="form-group">
                <label>AI 头像 URL</label>
                <input v-model="aiConfig.avatar_url" type="url" placeholder="https://...（留空使用默认图标）">
                <p class="form-hint">设置后将在聊天窗口标题和助手消息旁显示该头像。</p>
              </div>
              <div class="form-group">
                <label>系统提示词</label>
                <textarea v-model="aiConfig.system_prompt" rows="6" placeholder="设定 AI 助手的角色与行为，留空使用默认提示词。"></textarea>
                <p class="form-hint">用于设定助手身份与回答风格，对话时会作为 system 消息发送给模型。</p>
              </div>
              <div class="form-actions">
                <button type="submit" class="btn btn-primary" :disabled="aiConfigSaving">
                  {{ aiConfigSaving ? '保存中...' : '保存' }}
                </button>
              </div>
            </form>
          </template>
          <template v-else-if="pluginId === 'fino-cloudreve'">
            <p class="form-hint" style="margin-bottom: 16px;">绑定 Cloudreve 网盘，在 Fino 中管理、上传文件。<a href="https://cloudrevev4.apifox.cn/" target="_blank" rel="noopener">API 文档</a></p>
            <div v-if="isAdmin" style="margin-bottom: 20px;">
              <form @submit="handleCloudreveConfigSave" class="inline-form">
                <label class="checkbox-label" style="margin-right: 12px;">
                  <input v-model="cloudreveConfig.enabled" type="checkbox">
                  <span>开启网盘功能</span>
                </label>
                <button type="submit" class="btn btn-primary btn-sm" :disabled="cloudreveConfigSaving">
                  {{ cloudreveConfigSaving ? '保存中...' : '保存' }}
                </button>
              </form>
            </div>
            <template v-if="cloudreveConfig.enabled">
              <div v-if="!cloudreveStatus.bound" class="cloudreve-bind-section">
                <div class="form-group">
                  <label>Cloudreve 服务器地址</label>
                  <input v-model="cloudreveServerUrl" type="url" placeholder="https://your-cloudreve.com">
                </div>
                <div class="form-actions" style="margin-bottom: 16px;">
                  <button type="button" class="btn btn-outline" :disabled="cloudreveVerifying" @click="handleCloudreveVerify">
                    {{ cloudreveVerifying ? '验证中...' : '验证' }}
                  </button>
                  <button v-if="cloudreveVerifyResult?.valid" type="button" class="btn btn-primary" @click="handleCloudreveOpenLogin">
                    在新窗口打开 Cloudreve
                  </button>
                </div>
                <p v-if="cloudreveVerifyResult?.valid" class="form-hint" style="margin-bottom: 16px;">验证成功，填写 Cloudreve 账号密码即可绑定。</p>
                <form v-if="cloudreveVerifyResult?.valid" @submit="handleCloudreveBind">
                  <div class="form-row">
                    <div class="form-group">
                      <label>邮箱</label>
                      <input v-model="cloudreveBindEmail" type="email" placeholder="Cloudreve 登录邮箱" required>
                    </div>
                    <div class="form-group">
                      <label>密码</label>
                      <input v-model="cloudreveBindPassword" type="password" placeholder="Cloudreve 密码" required>
                    </div>
                  </div>
                  <div class="form-row">
                    <div class="form-group">
                      <label>验证码（可选）</label>
                      <div class="captcha-row">
                        <img v-if="cloudreveCaptcha?.image" :src="cloudreveCaptcha.image" alt="验证码" class="captcha-img">
                        <button type="button" class="btn btn-outline btn-sm" @click="handleCloudreveFetchCaptcha">获取验证码</button>
                        <input v-model="cloudreveCaptchaInput" type="text" placeholder="输入验证码" style="width: 100px;">
                      </div>
                    </div>
                  </div>
                  <div class="form-actions">
                    <button type="submit" class="btn btn-primary" :disabled="cloudreveBinding">
                      {{ cloudreveBinding ? '绑定中...' : '绑定' }}
                    </button>
                  </div>
                </form>
              </div>
              <div v-else>
                <p class="form-hint">已绑定 Cloudreve：{{ cloudreveStatus.cloudreve_url }}</p>
                <button type="button" class="btn btn-outline" @click="handleCloudreveUnbind">解绑</button>
              </div>
            </template>
            <p v-else class="form-hint">网盘功能未开启，请联系管理员开启。</p>
          </template>
          <p v-else-if="!hasConfig()" class="form-hint">该插件暂无配置项。</p>
        </div>
      </div>
    </div>
  `
}
