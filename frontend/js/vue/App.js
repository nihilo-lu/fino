import { ref, computed, onMounted, defineAsyncComponent } from 'vue'
import { useStore } from './store/index.js'
import { getPageFromPath, pushState, replaceState, initRouter } from './utils/router.js'

// 首屏登录/注册/选账本必须同步加载，其余按需懒加载以加快登录页打开速度
import LoginPage from './components/LoginPage.js'
import RegisterPage from './components/RegisterPage.js'
import LedgerSelectPage from './components/LedgerSelectPage.js'
import Toast from './components/Toast.js'

const Sidebar = defineAsyncComponent(() => import('./components/Sidebar.js'))
const Header = defineAsyncComponent(() => import('./components/Header.js'))
const DashboardView = defineAsyncComponent(() => import('./components/DashboardView.js'))
const AccountsView = defineAsyncComponent(() => import('./components/AccountsView.js'))
const TransactionsView = defineAsyncComponent(() => import('./components/TransactionsView.js'))
const FundsView = defineAsyncComponent(() => import('./components/FundsView.js'))
const AnalysisView = defineAsyncComponent(() => import('./components/AnalysisView.js'))
const SettingsView = defineAsyncComponent(() => import('./components/SettingsView.js'))
const ApiDocsView = defineAsyncComponent(() => import('./components/ApiDocsView.js'))
const CloudStorageView = defineAsyncComponent(() => import('./components/CloudStorageView.js'))
const FundModal = defineAsyncComponent(() => import('./components/FundModal.js'))
const AddLedgerModal = defineAsyncComponent(() => import('./components/AddLedgerModal.js'))
const AiChatButton = defineAsyncComponent(() => import('./components/AiChatButton.js'))
const AiChatWindow = defineAsyncComponent(() => import('./components/AiChatWindow.js'))
const AiChatPage = defineAsyncComponent(() => import('./components/AiChatPage.js'))

const PAGE_TITLES = {
  dashboard: '仪表盘',
  accounts: '账户管理',
  transactions: '交易明细',
  funds: '资金明细',
  analysis: '收益分析',
  'cloud-storage': '网盘',
  settings: '设置',
  'api-docs': 'API 文档',
  chat: 'AI 助手'
}

const NAV_ITEMS_BASE = [
  { id: 'dashboard', label: '仪表盘', icon: 'dashboard' },
  { id: 'accounts', label: '账户管理', icon: 'account_balance' },
  { id: 'transactions', label: '交易明细', icon: 'receipt_long' },
  { id: 'funds', label: '资金明细', icon: 'payments' },
  { id: 'analysis', label: '收益分析', icon: 'analytics' },
  { id: 'api-docs', label: 'API 文档', icon: 'code' },
  { id: 'settings', label: '设置', icon: 'settings' }
]

export default {
  name: 'App',
components: {
    LoginPage,
    RegisterPage,
    LedgerSelectPage,
    Sidebar,
    Header,
    DashboardView,
    AccountsView,
    TransactionsView,
    FundsView,
    AnalysisView,
    SettingsView,
    ApiDocsView,
    CloudStorageView,
    Toast,
    FundModal,
    AddLedgerModal,
    AiChatButton,
    AiChatWindow,
    AiChatPage
  },
  setup() {
    const { state, actions } = useStore()
    const showRegister = ref(false)
    const currentPage = ref(getPageFromPath())
    const sidebarCollapsed = ref(false)
const showFundModal = ref(false)
    const editingFund = ref(null)
    const fundsRefreshTrigger = ref(0)
    const showAddLedgerModal = ref(false)
    const showAiChat = ref(false)
    const loginError = ref('')
    const registerError = ref('')
    const registerSuccess = ref('')
    const pageTitle = computed(() => PAGE_TITLES[currentPage.value] || '仪表盘')
    const currentLedgerName = computed(() => {
      if (!state.currentLedgerId) return ''
      const ledger = state.ledgers.find((l) => l.id === state.currentLedgerId)
      return ledger?.name || ''
    })
    const userName = computed(() => state.user?.name || state.user?.username || '用户名')
    const navItems = computed(() => {
      const items = [...NAV_ITEMS_BASE]
      // 插件中心关闭时所有插件禁用；开启时由 enabledPlugins 控制
      const showCloudreve = state.pluginCenterEnabled && state.cloudreveEnabled && state.enabledPlugins?.includes('fino-cloudreve')
      if (showCloudreve) {
        const cloudIdx = items.findIndex((i) => i.id === 'analysis')
        items.splice(cloudIdx + 1, 0, { id: 'cloud-storage', label: '网盘', icon: 'cloud' })
      }
      return items
    })

    const handleLogin = async ({ username, password }) => {
      loginError.value = ''
      const result = await actions.login(username, password)
      if (result.success) {
        await actions.fetchLedgers()
        try {
          await actions.fetchPluginCenterSetting()
          await actions.fetchCloudreveConfig()
          await actions.fetchCloudreveStatus()
          if (state.pluginCenterEnabled) await actions.fetchInstalledPlugins()
        } catch (e) {
          console.warn('Post-login fetch failed:', e)
        }
      } else {
        loginError.value = result.error || '登录失败'
      }
    }

    const handleLedgerSelect = async (ledgerId) => {
      actions.setCurrentLedger(ledgerId)
      await actions.fetchAccounts()
      currentPage.value = getPageFromPath()
      replaceState(currentPage.value)
    }

const handleCreateLedger = async ({ name, description }) => {
      const ok = await actions.createLedger(name, description)
      if (ok) await actions.fetchLedgers()
    }

    const handleShowAddLedgerModal = () => {
      showAddLedgerModal.value = true
    }

    const handleAddLedgerModalClose = () => {
      showAddLedgerModal.value = false
    }

    const handleOpenAiChat = () => {
      actions.setAiChatUnread(false)
      showAiChat.value = true
    }

    const handleRegister = async (formData) => {
      registerError.value = ''
      registerSuccess.value = ''
      const result = await actions.register(formData)
      if (result.success) {
        registerSuccess.value = '注册成功，请登录'
        setTimeout(() => {
          showRegister.value = false
          registerSuccess.value = ''
        }, 1500)
      } else {
        registerError.value = result.error || '注册失败'
      }
    }

    const handleLogout = async () => {
      await actions.logout()
      showRegister.value = false
    }

    const handleSwitchLedger = () => {
      actions.clearCurrentLedger()
    }

    const navigateTo = (pageId) => {
      currentPage.value = pageId
      pushState(pageId)
    }

    const handleShowFundModal = () => {
      if (!state.currentLedgerId) {
        actions.showToast('请先选择账本', 'warning')
        return
      }
      editingFund.value = null
      showFundModal.value = true
    }

    const handleEditFund = async (fundId) => {
      const data = await actions.fetchFundTransaction(fundId)
      if (data) {
        editingFund.value = data
        showFundModal.value = true
      }
    }

    const handleFundSubmitted = () => {
      showFundModal.value = false
      editingFund.value = null
      fundsRefreshTrigger.value++
    }

    const handleFundModalClose = () => {
      showFundModal.value = false
      editingFund.value = null
    }

    const refreshFundsList = () => {
      fundsRefreshTrigger.value++
    }

      onMounted(async () => {
      initRouter((pageId) => {
        currentPage.value = pageId
      })
      const isAuth = await actions.checkAuth()
      if (!isAuth) {
        await actions.logout()
        return
      }
      await actions.fetchLedgers()
      actions.tryRestoreLastLedger()
      if (state.currentLedgerId) {
        await actions.fetchAccounts()
      }
      try {
        await actions.fetchPluginCenterSetting()
        await actions.fetchCloudreveConfig()
        await actions.fetchCloudreveStatus()
        if (state.pluginCenterEnabled) await actions.fetchInstalledPlugins()
      } catch (e) {
        console.warn('Auth fetch failed:', e)
      }
      if (state.isAuthenticated && state.currentLedgerId) {
        currentPage.value = getPageFromPath()
      }
    })

    return {
      state,
      actions,
      showRegister,
      currentPage,
      sidebarCollapsed,
      showFundModal,
      editingFund,
      showAiChat,
      pageTitle,
      currentLedgerName,
      userName,
      navItems,
      handleLogin,
      handleRegister,
      handleLogout,
handleLedgerSelect,
      handleCreateLedger,
      handleSwitchLedger,
      navigateTo,
      handleShowFundModal,
      handleEditFund,
      handleFundSubmitted,
      handleFundModalClose,
      refreshFundsList,
      fundsRefreshTrigger,
      showAddLedgerModal,
      handleShowAddLedgerModal,
      handleAddLedgerModalClose,
      handleOpenAiChat,
      loginError,
      registerError,
      registerSuccess
    }
  },
  template: `
    <div id="app">
      <button
        v-if="!state.isAuthenticated || !state.currentLedgerId"
        type="button"
        class="theme-toggle-float btn-icon"
        :title="state.darkMode ? '切换到日间模式' : '切换到夜间模式'"
        @click="actions.toggleDarkMode()"
        aria-label="切换夜间模式"
      >
        <span class="material-icons">{{ state.darkMode ? 'light_mode' : 'dark_mode' }}</span>
      </button>
      <div v-if="!state.isAuthenticated" :class="['auth-pages', { 'show-register': showRegister }]">
        <LoginPage
          v-show="!showRegister"
          :error="loginError"
          @login="handleLogin"
          @show-register="showRegister = true"
        />
        <RegisterPage
          v-show="showRegister"
          :error="registerError"
          :success="registerSuccess"
          @register="handleRegister"
          @show-login="showRegister = false"
        />
      </div>

<LedgerSelectPage
        v-else-if="!state.currentLedgerId"
        :ledgers="state.ledgers"
        :user-name="userName"
        @select-ledger="handleLedgerSelect"
        @show-add-ledger-modal="handleShowAddLedgerModal"
        @logout="handleLogout"
      />

      <div v-else id="main-page" class="page active">
        <Sidebar
          v-if="currentPage !== 'chat'"
          :nav-items="navItems"
          :current-page="currentPage"
          :user-name="userName"
          :user-avatar="state.user?.avatar"
          :collapsed="sidebarCollapsed"
          @navigate="navigateTo"
          @logout="handleLogout"
          @switch-ledger="handleSwitchLedger"
        />
        <main class="main-content" :class="{ 'main-content-chat': currentPage === 'chat' }">
          <Header
            v-if="currentPage !== 'chat'"
            :page-title="pageTitle"
            :current-ledger-name="currentLedgerName"
            @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed"
          />
          <div v-if="currentPage === 'chat'" class="content-area content-area-chat">
            <AiChatPage @close="navigateTo('dashboard')" />
          </div>
          <div v-else class="content-area">
            <DashboardView
              v-show="currentPage === 'dashboard'"
              :current-page="currentPage"
              :class="['view', { active: currentPage === 'dashboard' }]"
              @navigate="navigateTo"
            />
            <AccountsView
              v-show="currentPage === 'accounts'"
              :class="['view', { active: currentPage === 'accounts' }]"
              @navigate="navigateTo"
            />
            <TransactionsView
              v-show="currentPage === 'transactions'"
              :class="['view', { active: currentPage === 'transactions' }]"
              @transaction-changed="refreshFundsList"
            />
            <FundsView
              v-show="currentPage === 'funds'"
              :class="['view', { active: currentPage === 'funds' }]"
              :refresh-trigger="fundsRefreshTrigger"
              @show-add-fund="handleShowFundModal"
              @edit-fund="handleEditFund"
            />
            <AnalysisView
              v-show="currentPage === 'analysis'"
              :class="['view', { active: currentPage === 'analysis' }]"
              :current-page="currentPage"
            />
            <CloudStorageView
              v-show="currentPage === 'cloud-storage'"
              :class="['view', { active: currentPage === 'cloud-storage' }]"
              @navigate="navigateTo"
            />
            <ApiDocsView
              v-show="currentPage === 'api-docs'"
              :class="['view', { active: currentPage === 'api-docs' }]"
            />
            <SettingsView
              v-show="currentPage === 'settings'"
              :class="['view', { active: currentPage === 'settings' }]"
              @navigate="navigateTo"
            />
          </div>
        </main>
      </div>

      <Toast />
      <FundModal
        v-if="showFundModal"
        :show="true"
        :edit-fund="editingFund"
        @close="handleFundModalClose"
        @submitted="handleFundSubmitted"
      />
      <AddLedgerModal
        v-if="showAddLedgerModal"
        :show="true"
        @close="handleAddLedgerModalClose"
        @create="handleCreateLedger"
      />
      <AiChatButton v-if="state.isAuthenticated && state.currentLedgerId && state.pluginCenterEnabled && state.enabledPlugins?.includes('fino-ai-chat') && currentPage !== 'chat'" @click="handleOpenAiChat" />
      <AiChatWindow
        v-if="currentPage !== 'chat' && showAiChat"
        :show="true"
        @close="showAiChat = false"
      />
    </div>
  `
}
