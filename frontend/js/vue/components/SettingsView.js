import { ref, onMounted, watch, computed } from 'vue'
import { useStore } from '../store/index.js'
import PluginConfigModal from './PluginConfigModal.js'

export default {
  name: 'SettingsView',
  components: { PluginConfigModal },
  emits: ['navigate'],
  setup(props, { emit }) {
    const { state, actions, isAdmin } = useStore()
    const apiToken = ref('')
    const tokenVisible = ref(false)
    const pwaConfig = ref({
      name: '投资追踪器',
      short_name: '投资追踪',
      description: '投资组合追踪与收益分析工具',
      theme_color: '#E8A317',
      background_color: '#ffffff',
      display: 'standalone',
      icon_192: '/frontend/icons/icon-192.png',
      icon_512: '/frontend/icons/icon-512.png'
    })
    const pwaSaving = ref(false)
    const newLedgerName = ref('')
    const newLedgerDesc = ref('')
    const accountLedgerId = ref('')
    const newAccountName = ref('')
    const newAccountType = ref('股票')
    const newAccountCurrency = ref('CNY')
    const settingsAccounts = ref([])

    // 用户资料
    const profileUsername = ref('')
    const profileNickname = ref('')
    const profileEmail = ref('')
    const profileSaving = ref(false)
    const currentPassword = ref('')
    const newPassword = ref('')
    const newPasswordRepeat = ref('')
    const passwordSaving = ref(false)
    const avatarFile = ref(null)
    const avatarUploading = ref(false)
    const avatarInputKey = ref(0)

    // 用户管理（仅管理员）
    const users = ref([])
    const newUserUsername = ref('')
    const newUserEmail = ref('')
    const newUserPassword = ref('')
    const newUserIsAdmin = ref(false)
    const usersLoading = ref(false)

    // 数据库配置（仅管理员）
    const dbConfig = ref({
      type: 'sqlite',
      sqlite: { path: 'investment.db' },
      postgresql: { host: 'localhost', port: 5432, database: 'investment', user: 'postgres', password: '', sslmode: 'prefer' },
      d1: { account_id: '', database_id: '', api_token: '' }
    })
    const dbConfigSaving = ref(false)
    const dbConfigTesting = ref(false)

    // 插件中心
    const pluginRegistry = ref([])
    const installedPlugins = ref({ installed: [], enabled: [] })
    const pluginsLoading = ref(false)
    const pluginToggling = ref(null)
    const showPluginConfigModal = ref(false)
    const pluginConfigTarget = ref(null)

    const activeTab = ref('profile')

    const tabs = computed(() => {
      const base = [
        { id: 'profile', label: '个人', icon: 'person' },
        { id: 'data', label: '数据', icon: 'folder' },
        { id: 'system', label: '系统', icon: 'settings' }
      ]
      if (state.pluginCenterEnabled) {
        base.push({ id: 'plugins', label: '插件中心', icon: 'extension' })
      }
      return base
    })

    const switchTab = (id) => {
      activeTab.value = id
    }

    const displayAccounts = computed(() => {
      if (accountLedgerId.value === state.currentLedgerId) return state.accounts
      return settingsAccounts.value
    })

    const loadSettingsAccounts = async () => {
      if (accountLedgerId.value) {
        settingsAccounts.value = await actions.fetchAccountsForLedger(parseInt(accountLedgerId.value))
      } else {
        settingsAccounts.value = []
      }
    }

    const loadToken = async () => {
      apiToken.value = await actions.fetchToken()
    }

    const loadPwaConfig = async () => {
      const cfg = await actions.fetchPwaConfig()
      if (cfg) pwaConfig.value = { ...pwaConfig.value, ...cfg }
    }

    const loadDatabaseConfig = async () => {
      if (!isAdmin.value) return
      const cfg = await actions.fetchDatabaseConfig()
      if (cfg) dbConfig.value = { ...dbConfig.value, ...cfg }
    }

    const loadPluginRegistry = async () => {
      pluginRegistry.value = await actions.fetchPluginRegistry()
    }

    const loadInstalledPlugins = async () => {
      installedPlugins.value = await actions.fetchInstalledPlugins()
    }

    const loadPlugins = async () => {
      pluginsLoading.value = true
      await Promise.all([loadPluginRegistry(), loadInstalledPlugins()])
      pluginsLoading.value = false
    }

    const handlePluginEnable = async (pluginId) => {
      pluginToggling.value = pluginId
      const ok = await actions.enablePlugin(pluginId)
      pluginToggling.value = null
      if (ok) loadInstalledPlugins()
    }

    const handlePluginDisable = async (pluginId) => {
      pluginToggling.value = pluginId
      const ok = await actions.disablePlugin(pluginId)
      pluginToggling.value = null
      if (ok) loadInstalledPlugins()
    }

    const handlePluginUninstall = async (pluginId) => {
      if (!confirm(`确定要卸载「${installedPlugins.value.installed?.find(p => p.id === pluginId)?.name || pluginId}」吗？卸载后需重启应用，可通过「可安装」列表重新安装。`)) return
      pluginToggling.value = pluginId
      const ok = await actions.uninstallPlugin(pluginId)
      pluginToggling.value = null
      if (ok) {
        activeTab.value = 'plugins'
        await loadPlugins()
      }
    }

    const handlePluginInstall = async (pluginId) => {
      pluginToggling.value = pluginId
      const ok = await actions.installPlugin(pluginId)
      pluginToggling.value = null
      if (ok) loadPlugins()
    }

    const handlePluginConfig = (plugin) => {
      pluginConfigTarget.value = plugin
      showPluginConfigModal.value = true
    }

    const pluginCenterSaving = ref(false)
    const pluginCenterEnabled = ref(true)

    // 检测升级
    const updateCheckLoading = ref(false)
    const updateInfo = ref(null)

    const loadPluginCenterSetting = async () => {
      await actions.fetchPluginCenterSetting()
      pluginCenterEnabled.value = state.pluginCenterEnabled
    }

    const handlePluginCenterSave = async (e) => {
      e.preventDefault()
      pluginCenterSaving.value = true
      const ok = await actions.savePluginCenterSetting(pluginCenterEnabled.value)
      pluginCenterSaving.value = false
      if (ok) loadPluginCenterSetting()
    }

    const handleCheckUpdate = async () => {
      updateCheckLoading.value = true
      updateInfo.value = null
      try {
        const data = await actions.fetchCheckUpdate()
        updateInfo.value = data
      } catch (e) {
        updateInfo.value = { error: '检测失败' }
      }
      updateCheckLoading.value = false
    }

    const isPluginEnabled = (pluginId) => installedPlugins.value.enabled?.includes(pluginId) ?? false
    const isPluginInstalled = (pluginId) => installedPlugins.value.installed?.some(p => p.id === pluginId) ?? false
    const availableToInstall = computed(() =>
      (pluginRegistry.value || []).filter(p => p.install_type === 'builtin' && !isPluginInstalled(p.id))
    )

    const handleDatabaseSave = async (e) => {
      e.preventDefault()
      dbConfigSaving.value = true
      const ok = await actions.saveDatabaseConfig(dbConfig.value)
      dbConfigSaving.value = false
      if (ok) loadDatabaseConfig()
    }

    const handleDatabaseTest = async () => {
      dbConfigTesting.value = true
      await actions.testDatabaseConnection(dbConfig.value)
      dbConfigTesting.value = false
    }

    const handlePwaSave = async (e) => {
      e.preventDefault()
      pwaSaving.value = true
      const ok = await actions.savePwaConfig(pwaConfig.value)
      pwaSaving.value = false
      if (ok) loadPwaConfig()
    }

    const generateToken = async () => {
      const token = await actions.generateToken()
      if (token) apiToken.value = token
    }

    const resetToken = async () => {
      const token = await actions.resetToken()
      if (token) apiToken.value = token
    }

    const copyToken = () => {
      if (!apiToken.value) {
        actions.showToast('请先生成 Token', 'warning')
        return
      }
      navigator.clipboard.writeText(apiToken.value).then(() => {
        actions.showToast('Token 已复制到剪贴板', 'success')
      }).catch(() => actions.showToast('复制失败', 'error'))
    }

    const toggleTokenVisibility = () => {
      tokenVisible.value = !tokenVisible.value
    }

    const handleLedgerSubmit = async (e) => {
      e.preventDefault()
      if (!newLedgerName.value.trim()) {
        actions.showToast('请输入账本名称', 'warning')
        return
      }
      const ok = await actions.createLedger(newLedgerName.value.trim(), newLedgerDesc.value.trim())
      if (ok) {
        newLedgerName.value = ''
        newLedgerDesc.value = ''
        await actions.fetchLedgers()
      }
    }

    const handleAccountSubmit = async (e) => {
      e.preventDefault()
      if (!accountLedgerId.value || !newAccountName.value.trim()) {
        actions.showToast('请填写完整信息', 'warning')
        return
      }
      const ok = await actions.createAccount(
        parseInt(accountLedgerId.value),
        newAccountName.value.trim(),
        newAccountType.value,
        newAccountCurrency.value
      )
      if (ok) {
        newAccountName.value = ''
        await actions.fetchAccounts()
        await actions.fetchLedgers()
      }
    }

    const deleteLedger = async (id) => {
      const ok = await actions.deleteLedger(id)
      if (ok) await actions.fetchLedgers()
    }

    const deleteAccount = async (id) => {
      const ok = await actions.deleteAccount(id)
      if (ok) {
        await actions.fetchAccounts()
        await actions.fetchLedgers()
      }
    }

    const loadProfile = () => {
      profileUsername.value = state.user?.username || ''
      profileNickname.value = state.user?.name || ''
      profileEmail.value = state.user?.email || ''
    }

    const handleProfileSubmit = async (e) => {
      e.preventDefault()
      profileSaving.value = true
      const result = await actions.updateProfile({
        username: profileUsername.value.trim(),
        nickname: profileNickname.value.trim(),
        email: profileEmail.value.trim()
      })
      profileSaving.value = false
      if (result.success) loadProfile()
    }

    const handlePasswordSubmit = async (e) => {
      e.preventDefault()
      if (!currentPassword.value || !newPassword.value || !newPasswordRepeat.value) {
        actions.showToast('请填写完整', 'warning')
        return
      }
      if (newPassword.value.length < 6) {
        actions.showToast('新密码至少 6 位', 'warning')
        return
      }
      if (newPassword.value !== newPasswordRepeat.value) {
        actions.showToast('两次输入的新密码不一致', 'warning')
        return
      }
      passwordSaving.value = true
      const result = await actions.updatePassword({
        current_password: currentPassword.value,
        new_password: newPassword.value,
        new_password_repeat: newPasswordRepeat.value
      })
      passwordSaving.value = false
      if (result.success) {
        currentPassword.value = ''
        newPassword.value = ''
        newPasswordRepeat.value = ''
      }
    }

    const onAvatarChange = (e) => {
      avatarFile.value = e.target.files?.[0]
    }

    const loadUsers = async () => {
      if (!isAdmin.value) return
      usersLoading.value = true
      users.value = await actions.fetchUsers()
      usersLoading.value = false
    }

    const handleAddUser = async (e) => {
      e.preventDefault()
      if (!newUserUsername.value.trim() || !newUserPassword.value) {
        actions.showToast('请填写用户名和密码', 'warning')
        return
      }
      if (newUserPassword.value.length < 6) {
        actions.showToast('密码至少 6 位', 'warning')
        return
      }
      const ok = await actions.addUser({
        username: newUserUsername.value.trim().toLowerCase(),
        email: newUserEmail.value.trim(),
        password: newUserPassword.value,
        is_admin: newUserIsAdmin.value
      })
      if (ok) {
        newUserUsername.value = ''
        newUserEmail.value = ''
        newUserPassword.value = ''
        newUserIsAdmin.value = false
        loadUsers()
      }
    }

    const toggleUserDisabled = async (user) => {
      const ok = await actions.updateUser(user.username, { disabled: !user.disabled })
      if (ok) loadUsers()
    }

    const toggleUserAdmin = async (user) => {
      const ok = await actions.updateUser(user.username, { is_admin: !user.roles?.includes('admin') })
      if (ok) loadUsers()
    }

    const handleDeleteUser = async (user) => {
      if (!confirm(`确定要删除用户「${user.username}」吗？此操作不可恢复。`)) return
      const ok = await actions.deleteUser(user.username)
      if (ok) loadUsers()
    }

    const handleAvatarUpload = async () => {
      if (!avatarFile.value) {
        actions.showToast('请选择图片', 'warning')
        return
      }
      const allowed = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp']
      if (!allowed.includes(avatarFile.value.type)) {
        actions.showToast('仅支持 PNG、JPG、GIF、WebP 格式', 'warning')
        return
      }
      avatarUploading.value = true
      const result = await actions.uploadAvatar(avatarFile.value)
      avatarUploading.value = false
      if (result.success) {
        avatarFile.value = null
        avatarInputKey.value++
      }
    }

    onMounted(async () => {
      loadProfile()
      loadToken()
      loadPwaConfig()
      try {
        await loadPluginCenterSetting()
      } catch (e) {
        console.warn('loadPluginCenterSetting failed:', e)
      }
      actions.fetchLedgers()
      accountLedgerId.value = state.currentLedgerId || state.ledgers[0]?.id
      loadSettingsAccounts()
      try {
        await loadPlugins()
      } catch (e) {
        console.warn('loadPlugins failed:', e)
      }
      if (isAdmin.value) {
        loadUsers()
        loadDatabaseConfig()
      }
    })
    watch(() => state.ledgers, () => {
      if (state.ledgers.length && !accountLedgerId.value) accountLedgerId.value = state.currentLedgerId || state.ledgers[0]?.id
    }, { deep: true })
    watch(accountLedgerId, loadSettingsAccounts)
    watch(activeTab, (tab) => {
      if (tab === 'plugins') loadPlugins()
    })

    return {
      activeTab,
      tabs,
      switchTab,
      displayAccounts,
      state,
      actions,
      apiToken,
      tokenVisible,
      pwaConfig,
      pwaSaving,
      loadPwaConfig,
      handlePwaSave,
      newLedgerName,
      newLedgerDesc,
      accountLedgerId,
      newAccountName,
      newAccountType,
      newAccountCurrency,
      generateToken,
      resetToken,
      copyToken,
      toggleTokenVisibility,
      handleLedgerSubmit,
      handleAccountSubmit,
      deleteLedger,
      deleteAccount,
      profileUsername,
      profileNickname,
      profileEmail,
      profileSaving,
      currentPassword,
      newPassword,
      newPasswordRepeat,
      passwordSaving,
      avatarFile,
      avatarUploading,
      loadProfile,
      handleProfileSubmit,
      handlePasswordSubmit,
      onAvatarChange,
      handleAvatarUpload,
      avatarInputKey,
      isAdmin,
      users,
      newUserUsername,
      newUserEmail,
      newUserPassword,
      newUserIsAdmin,
      usersLoading,
      loadUsers,
      handleAddUser,
      toggleUserDisabled,
      toggleUserAdmin,
      handleDeleteUser,
      dbConfig,
      dbConfigSaving,
      dbConfigTesting,
      loadDatabaseConfig,
      handleDatabaseSave,
      handleDatabaseTest,
      pluginRegistry,
      installedPlugins,
      pluginsLoading,
      pluginToggling,
      loadPlugins,
      handlePluginEnable,
      handlePluginDisable,
      handlePluginUninstall,
      handlePluginInstall,
      handlePluginConfig,
      pluginConfigTarget,
      availableToInstall,
      isPluginEnabled,
      showPluginConfigModal,
      pluginCenterSaving,
      pluginCenterEnabled,
      loadPluginCenterSetting,
      handlePluginCenterSave,
      updateCheckLoading,
      updateInfo,
      handleCheckUpdate
    }
  },
  template: `
    <div id="settings-view" class="view">
      <div class="settings-tabs-wrap">
        <div class="settings-tabs">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            :class="['settings-tab', { active: activeTab === tab.id }]"
            @click="switchTab(tab.id)"
          >
            <span class="material-icons">{{ tab.icon }}</span>
            {{ tab.label }}
            <span v-if="tab.badge" class="settings-tab-badge">{{ tab.badge }}</span>
          </button>
        </div>
      </div>

      <div v-show="activeTab === 'profile'" class="settings-panel">
      <div class="form-card">
        <div class="card-header"><h3>👤 用户资料</h3></div>
        <div class="card-body">
          <form @submit="handleProfileSubmit">
            <div class="profile-avatar-row">
              <div class="avatar-preview">
                <img v-if="state.user?.avatar" :src="state.user.avatar" alt="头像" class="avatar-img">
                <span v-else class="avatar-placeholder material-icons">person</span>
              </div>
              <div class="avatar-upload">
                <input :key="avatarInputKey" type="file" accept="image/png,image/jpeg,image/jpg,image/gif,image/webp" @change="onAvatarChange">
                <button type="button" class="btn btn-outline" :disabled="!avatarFile || avatarUploading" @click="handleAvatarUpload">
                  {{ avatarUploading ? '上传中...' : '上传头像' }}
                </button>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>用户名</label>
                <input v-model="profileUsername" type="text" placeholder="登录用户名" required>
              </div>
              <div class="form-group">
                <label>昵称</label>
                <input v-model="profileNickname" type="text" placeholder="显示名称">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>邮箱</label>
                <input v-model="profileEmail" type="email" placeholder="邮箱地址">
              </div>
            </div>
            <div class="form-actions">
              <button type="submit" class="btn btn-primary" :disabled="profileSaving">
                {{ profileSaving ? '保存中...' : '💾 保存资料' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      <div class="form-card">
        <div class="card-header"><h3>🔐 修改密码</h3></div>
        <div class="card-body">
          <form @submit="handlePasswordSubmit">
            <div class="form-row">
              <div class="form-group">
                <label>当前密码</label>
                <input v-model="currentPassword" type="password" placeholder="输入当前密码">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>新密码</label>
                <input v-model="newPassword" type="password" placeholder="至少 6 位">
              </div>
              <div class="form-group">
                <label>确认新密码</label>
                <input v-model="newPasswordRepeat" type="password" placeholder="再次输入新密码">
              </div>
            </div>
            <div class="form-actions">
              <button type="submit" class="btn btn-primary" :disabled="passwordSaving">
                {{ passwordSaving ? '保存中...' : '🔑 修改密码' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      <div class="form-card">
        <div class="card-header"><h3>API 访问令牌</h3></div>
        <div class="card-body">
          <div class="form-group">
            <label>Token 用于 API 调用（如脚本、第三方工具），退出登录和修改密码后仍有效</label>
            <div class="token-display">
              <input
                :type="tokenVisible ? 'text' : 'password'"
                v-model="apiToken"
                readonly
                class="token-input"
                :placeholder="apiToken ? '' : '点击「生成」创建 Token'"
              >
              <button v-if="!apiToken" type="button" class="btn btn-primary" @click="generateToken" title="生成">
                <span class="material-icons">add</span>
                生成
              </button>
              <button v-if="apiToken" type="button" class="btn btn-outline" @click="resetToken" title="重置">
                <span class="material-icons">refresh</span>
                重置
              </button>
              <button type="button" class="btn btn-outline" @click="copyToken" title="复制">
                <span class="material-icons">content_copy</span>
                复制
              </button>
              <button type="button" class="btn btn-outline" @click="toggleTokenVisibility" title="显示/隐藏">
                <span class="material-icons">{{ tokenVisible ? 'visibility_off' : 'visibility' }}</span>
              </button>
            </div>
            <p class="form-hint">Token 在设置中生成，永久有效。重置后旧 Token 失效。请勿泄露给他人。</p>
          </div>
        </div>
      </div>
      </div>

      <div v-show="activeTab === 'data'" class="settings-panel">
      <div class="form-card">
        <div class="card-header"><h3>账本管理</h3></div>
        <div class="card-body">
          <form @submit="handleLedgerSubmit" class="inline-form">
            <div class="form-group">
              <input v-model="newLedgerName" type="text" placeholder="新账本名称">
            </div>
            <div class="form-group">
              <input v-model="newLedgerDesc" type="text" placeholder="账本描述">
            </div>
            <button type="submit" class="btn btn-primary">
              <span class="material-icons">add</span>
              添加账本
            </button>
          </form>
          <div class="items-list">
            <div v-for="ledger in state.ledgers" :key="ledger.id" class="item-card">
              <div class="item-info">
                <span class="item-name">{{ ledger.name }}</span>
                <span class="item-desc">{{ ledger.description || '无描述' }} | {{ ledger.cost_method }}</span>
              </div>
              <div class="item-actions">
                <button class="btn-icon" @click="deleteLedger(ledger.id)" title="删除">
                  <span class="material-icons">delete</span>
                </button>
              </div>
            </div>
            <p v-if="state.ledgers.length === 0" class="empty-message">暂无账本</p>
          </div>
        </div>
      </div>
      <div class="form-card">
        <div class="card-header"><h3>账户管理</h3></div>
        <div class="card-body">
          <form @submit="handleAccountSubmit" class="inline-form">
            <div class="form-group">
              <select v-model="accountLedgerId">
                <option value="">选择账本</option>
                <option v-for="l in state.ledgers" :key="l.id" :value="l.id">{{ l.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <input v-model="newAccountName" type="text" placeholder="账户名称">
            </div>
            <div class="form-group">
              <select v-model="newAccountType">
                <option value="股票">股票</option>
                <option value="基金">基金</option>
                <option value="债券">债券</option>
                <option value="期货">期货</option>
                <option value="现金">现金</option>
              </select>
            </div>
            <div class="form-group">
              <select v-model="newAccountCurrency">
                <option value="CNY">CNY</option>
                <option value="USD">USD</option>
                <option value="HKD">HKD</option>
                <option value="EUR">EUR</option>
              </select>
            </div>
            <button type="submit" class="btn btn-primary">
              <span class="material-icons">add</span>
              添加账户
            </button>
          </form>
          <div class="items-list">
            <div v-for="account in displayAccounts" :key="account.id" class="item-card">
              <div class="item-info">
                <span class="item-name">{{ account.name }}</span>
                <span class="item-desc">{{ account.type }} | {{ account.currency }}</span>
              </div>
              <div class="item-actions">
                <button class="btn-icon" @click="deleteAccount(account.id)" title="删除">
                  <span class="material-icons">delete</span>
                </button>
              </div>
            </div>
            <p v-if="displayAccounts.length === 0" class="empty-message">暂无账户</p>
          </div>
        </div>
      </div>
      </div>

      <div v-show="activeTab === 'system'" class="settings-panel">
      <div class="form-card">
        <div class="card-header"><h3>🔄 检测升级</h3></div>
        <div class="card-body">
          <p class="form-hint" style="margin-bottom: 16px;">检查 GitHub 是否有新版本发布</p>
          <div class="form-actions">
            <button type="button" class="btn btn-primary" :disabled="updateCheckLoading" @click="handleCheckUpdate">
              <span class="material-icons" style="vertical-align: middle; font-size: 18px;">refresh</span>
              {{ updateCheckLoading ? '检测中...' : '检测升级' }}
            </button>
          </div>
          <div v-if="updateInfo && !updateInfo.error" class="update-result" style="margin-top: 16px; padding: 12px; background: var(--color-bg-secondary, #f8fafc); border-radius: 8px;">
            <p v-if="updateInfo.has_update" style="margin: 0 0 8px 0; color: var(--color-success, #10b981);">
              <strong>有新版本可用</strong>：v{{ updateInfo.latest }}（当前 v{{ updateInfo.current }}）
            </p>
            <p v-else style="margin: 0 0 8px 0; color: var(--color-text-secondary, #64748b);">
              当前已是最新版本 v{{ updateInfo.current }}
            </p>
            <a v-if="updateInfo.has_update && updateInfo.release_url" :href="updateInfo.release_url" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-primary" style="margin-top: 8px;">
              前往 GitHub 下载 ↗
            </a>
          </div>
          <p v-else-if="updateInfo?.error" class="form-hint" style="margin-top: 16px; color: var(--color-warning);">{{ updateInfo.error }}</p>
        </div>
      </div>
      <div class="form-card">
        <div class="card-header"><h3>📱 PWA 应用配置</h3></div>
        <div class="card-body">
          <p class="form-hint" style="margin-bottom: 16px;">自定义安装到主屏幕时的应用名称、图标和主题色</p>
          <form @submit="handlePwaSave">
            <div class="form-row">
              <div class="form-group">
                <label>应用名称</label>
                <input v-model="pwaConfig.name" type="text" placeholder="如：投资追踪器">
              </div>
              <div class="form-group">
                <label>短名称</label>
                <input v-model="pwaConfig.short_name" type="text" placeholder="如：投资追踪">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>应用描述</label>
                <input v-model="pwaConfig.description" type="text" placeholder="投资组合追踪与收益分析工具">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>主题色</label>
                <input v-model="pwaConfig.theme_color" type="text" placeholder="#E8A317">
              </div>
              <div class="form-group">
                <label>背景色</label>
                <input v-model="pwaConfig.background_color" type="text" placeholder="#ffffff">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>启动方式</label>
                <select v-model="pwaConfig.display">
                  <option value="standalone">独立应用（推荐）</option>
                  <option value="minimal-ui">最小浏览器 UI</option>
                  <option value="browser">浏览器</option>
                </select>
              </div>
              <div class="form-group">
                <label>图标 192×192</label>
                <input v-model="pwaConfig.icon_192" type="text" placeholder="/frontend/icons/icon-192.png">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>图标 512×512</label>
                <input v-model="pwaConfig.icon_512" type="text" placeholder="/frontend/icons/icon-512.png">
              </div>
            </div>
            <div class="form-actions">
              <button type="submit" class="btn btn-primary" :disabled="pwaSaving">
                {{ pwaSaving ? '保存中...' : '💾 保存 PWA 配置' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      <div v-if="isAdmin" class="form-card">
        <div class="card-header"><h3>🧩 插件中心</h3></div>
        <div class="card-body">
          <p class="form-hint" style="margin-bottom: 16px;">开启后，设置中将显示「插件中心」标签，可管理 AI、网盘等插件。</p>
          <form @submit="handlePluginCenterSave">
            <div class="form-group checkbox-group">
              <label class="checkbox-label">
                <input v-model="pluginCenterEnabled" type="checkbox">
                <span>开启插件中心</span>
              </label>
            </div>
            <div class="form-actions">
              <button type="submit" class="btn btn-primary" :disabled="pluginCenterSaving">
                {{ pluginCenterSaving ? '保存中...' : '保存' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      <div v-if="isAdmin" class="form-card">
        <div class="card-header"><h3>👥 用户管理</h3></div>
        <div class="card-body">
          <form @submit="handleAddUser" class="inline-form">
            <div class="form-group">
              <input v-model="newUserUsername" type="text" placeholder="登录名" required>
            </div>
            <div class="form-group">
              <input v-model="newUserEmail" type="email" placeholder="邮箱">
            </div>
            <div class="form-group">
              <input v-model="newUserPassword" type="password" placeholder="密码（至少6位）" required minlength="6">
            </div>
            <div class="form-group checkbox-group">
              <label class="checkbox-label">
                <input v-model="newUserIsAdmin" type="checkbox">
                <span>管理员</span>
              </label>
            </div>
            <button type="submit" class="btn btn-primary">
              <span class="material-icons">person_add</span>
              添加用户
            </button>
          </form>
          <div class="items-list" style="margin-top: 20px;">
            <div v-for="user in users" :key="user.username" class="item-card">
              <div class="item-info">
                <span class="item-name">
                  {{ user.username }}
                  <span v-if="user.disabled" class="badge badge-danger">已停用</span>
                  <span v-else-if="user.roles?.includes('admin')" class="badge badge-admin">管理员</span>
                  <span v-else class="badge">普通用户</span>
                </span>
                <span class="item-desc">{{ user.email || '无邮箱' }} · {{ user.name || user.username }}</span>
              </div>
              <div class="item-actions">
                <button
                  type="button"
                  class="btn btn-sm"
                  :class="user.disabled ? 'btn-primary' : 'btn-outline'"
                  :title="user.disabled ? '启用' : '停用'"
                  :disabled="user.username === state.user?.username"
                  @click="toggleUserDisabled(user)"
                >
                  {{ user.disabled ? '启用' : '停用' }}
                </button>
                <button
                  type="button"
                  class="btn btn-sm"
                  :class="user.roles?.includes('admin') ? 'btn-primary' : 'btn-outline'"
                  :title="user.roles?.includes('admin') ? '取消管理员' : '设为管理员'"
                  :disabled="user.username === state.user?.username"
                  @click="toggleUserAdmin(user)"
                >
                  {{ user.roles?.includes('admin') ? '取消管理员' : '设为管理员' }}
                </button>
                <button
                  type="button"
                  class="btn btn-sm btn-outline"
                  :disabled="user.username === state.user?.username"
                  title="删除"
                  @click="handleDeleteUser(user)"
                >
                  <span class="material-icons">delete</span>
                </button>
              </div>
            </div>
            <p v-if="users.length === 0 && !usersLoading" class="empty-message">暂无用户</p>
            <p v-if="usersLoading" class="empty-message">加载中...</p>
          </div>
        </div>
      </div>
      <div v-if="isAdmin" class="form-card">
        <div class="card-header"><h3>🗄️ 数据库设置</h3></div>
        <div class="card-body">
          <p class="form-hint" style="margin-bottom: 16px;">配置数据存储方式，支持 SQLite、PostgreSQL、Cloudflare D1。修改后需重启应用生效。</p>
          <form @submit="handleDatabaseSave">
            <div class="form-group">
              <label>数据库类型</label>
              <select v-model="dbConfig.type">
                <option value="sqlite">🗃️ SQLite（本地文件）</option>
                <option value="postgresql">🖥️ PostgreSQL（远程/本地）</option>
                <option value="d1">☁️ Cloudflare D1（边缘数据库）</option>
              </select>
            </div>
            <div v-if="dbConfig.type === 'sqlite'" class="form-group">
              <label>数据库文件路径</label>
              <input v-model="dbConfig.sqlite.path" type="text" placeholder="investment.db">
            </div>
            <template v-if="dbConfig.type === 'postgresql'">
              <div class="form-row">
                <div class="form-group">
                  <label>主机</label>
                  <input v-model="dbConfig.postgresql.host" type="text" placeholder="localhost">
                </div>
                <div class="form-group">
                  <label>端口</label>
                  <input v-model.number="dbConfig.postgresql.port" type="number" placeholder="5432">
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label>数据库名</label>
                  <input v-model="dbConfig.postgresql.database" type="text" placeholder="investment">
                </div>
                <div class="form-group">
                  <label>用户名</label>
                  <input v-model="dbConfig.postgresql.user" type="text" placeholder="postgres">
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label>密码</label>
                  <input v-model="dbConfig.postgresql.password" type="password" placeholder="密码">
                </div>
                <div class="form-group">
                  <label>SSL 模式</label>
                  <select v-model="dbConfig.postgresql.sslmode">
                    <option value="prefer">prefer</option>
                    <option value="disable">disable</option>
                    <option value="require">require</option>
                  </select>
                </div>
              </div>
            </template>
            <template v-if="dbConfig.type === 'd1'">
              <div class="form-group">
                <label>Account ID</label>
                <input v-model="dbConfig.d1.account_id" type="text" placeholder="Cloudflare 账户 ID">
              </div>
              <div class="form-group">
                <label>Database ID</label>
                <input v-model="dbConfig.d1.database_id" type="text" placeholder="D1 数据库 UUID">
              </div>
              <div class="form-group">
                <label>API Token</label>
                <input v-model="dbConfig.d1.api_token" type="password" placeholder="D1 读写权限的 API Token">
              </div>
            </template>
            <div class="form-actions">
              <button type="button" class="btn btn-outline" :disabled="dbConfigTesting" @click="handleDatabaseTest">
                {{ dbConfigTesting ? '测试中...' : '🔌 测试连接' }}
              </button>
              <button type="submit" class="btn btn-primary" :disabled="dbConfigSaving">
                {{ dbConfigSaving ? '保存中...' : '💾 保存配置' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      </div>

      <div v-show="activeTab === 'plugins'" class="settings-panel">
      <div class="form-card">
        <div class="card-header"><h3>🧩 插件中心</h3></div>
        <div class="card-body">
          <p class="form-hint" style="margin-bottom: 16px;">AI 智能助手与 Cloudreve 网盘均为插件，可自由启用、禁用或卸载。</p>
          <p v-if="!isAdmin" class="form-hint" style="margin-bottom: 16px; color: var(--color-warning);">启用/禁用/卸载插件需要管理员权限。</p>
          <div v-if="pluginsLoading" class="empty-message">加载中...</div>
          <template v-else>
            <h4 style="margin: 0 0 12px 0; font-size: 14px;">已安装</h4>
            <div class="items-list">
              <div v-for="p in (installedPlugins.installed || [])" :key="p.id" class="item-card">
                <div class="item-info">
                  <span class="item-name">{{ p.name }}</span>
                  <span class="item-desc">{{ p.manifest?.description || p.id }} · v{{ p.version }}</span>
                  <span v-if="isPluginEnabled(p.id)" class="badge badge-success">已启用</span>
                  <span v-else class="badge">已禁用</span>
                </div>
                <div class="item-actions">
                  <button
                    v-if="isPluginEnabled(p.id)"
                    type="button"
                    class="btn btn-sm btn-outline"
                    :disabled="pluginToggling === p.id || !isAdmin"
                    @click="handlePluginDisable(p.id)"
                  >
                    {{ pluginToggling === p.id ? '处理中...' : '禁用' }}
                  </button>
                  <button
                    v-else
                    type="button"
                    class="btn btn-sm btn-primary"
                    :disabled="pluginToggling === p.id || !isAdmin"
                    @click="handlePluginEnable(p.id)"
                  >
                    {{ pluginToggling === p.id ? '处理中...' : '启用' }}
                  </button>
                  <button
                    type="button"
                    class="btn btn-sm btn-outline"
                    title="配置"
                    :disabled="pluginToggling === p.id"
                    @click="handlePluginConfig(p)"
                  >
                    <span class="material-icons" style="font-size:16px;">settings</span> 配置
                  </button>
                  <button
                    type="button"
                    class="btn btn-sm btn-outline"
                    :disabled="pluginToggling === p.id || !isAdmin"
                    title="卸载后需重启应用"
                    @click="handlePluginUninstall(p.id)"
                  >
                    <span class="material-icons" style="font-size:16px;">delete</span> 卸载
                  </button>
                </div>
              </div>
              <p v-if="!installedPlugins.installed?.length" class="empty-message">暂无已安装插件</p>
            </div>
            <template v-if="(availableToInstall || []).length">
              <h4 style="margin: 24px 0 12px 0; font-size: 14px;">可安装</h4>
              <div class="items-list">
                <div v-for="p in availableToInstall" :key="p.id" class="item-card">
                  <div class="item-info">
                    <span class="item-name">{{ p.name }}</span>
                    <span class="item-desc">{{ p.description }} · v{{ p.version }}</span>
                  </div>
                  <div class="item-actions">
                    <button
                      type="button"
                      class="btn btn-sm btn-primary"
                      :disabled="pluginToggling === p.id || !isAdmin"
                      @click="handlePluginInstall(p.id)"
                    >
                      {{ pluginToggling === p.id ? '安装中...' : '安装' }}
                    </button>
                  </div>
                </div>
              </div>
            </template>
            <div class="form-hint" style="margin-top: 16px;">
              <strong>开发插件：</strong>按照 <code>docs/插件接口规范.md</code> 开发后放入 <code>plugins/</code> 目录即可。
            </div>
          </template>
        </div>
      </div>
      </div>
      <PluginConfigModal
        :show="showPluginConfigModal"
        :plugin-id="pluginConfigTarget ? pluginConfigTarget.id : ''"
        :plugin-name="pluginConfigTarget ? pluginConfigTarget.name : ''"
        @close="showPluginConfigModal = false"
      />
    </div>
  `
}
