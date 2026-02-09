import { ref, computed, onMounted } from 'vue'
import { useStore } from './store/index.js'
import { getPageFromPath, pushState, replaceState, initRouter } from './utils/router.js'

import LoginPage from './components/LoginPage.js'
import RegisterPage from './components/RegisterPage.js'
import LedgerSelectPage from './components/LedgerSelectPage.js'
import Sidebar from './components/Sidebar.js'
import Header from './components/Header.js'
import DashboardView from './components/DashboardView.js'
import PositionsView from './components/PositionsView.js'
import TransactionsView from './components/TransactionsView.js'
import FundsView from './components/FundsView.js'
import AnalysisView from './components/AnalysisView.js'
import SettingsView from './components/SettingsView.js'
import ApiDocsView from './components/ApiDocsView.js'
import CloudStorageView from './components/CloudStorageView.js'
import Toast from './components/Toast.js'
import FundModal from './components/FundModal.js'
import AiChatButton from './components/AiChatButton.js'
import AiChatWindow from './components/AiChatWindow.js'

const PAGE_TITLES = {
  dashboard: '仪表盘',
  positions: '持仓管理',
  transactions: '交易记录',
  funds: '资金明细',
  analysis: '收益分析',
  'cloud-storage': '网盘',
  settings: '设置',
  'api-docs': 'API 文档'
}

const NAV_ITEMS_BASE = [
  { id: 'dashboard', label: '仪表盘', icon: 'dashboard' },
  { id: 'positions', label: '持仓管理', icon: 'account_balance' },
  { id: 'transactions', label: '交易记录', icon: 'receipt_long' },
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
    PositionsView,
    TransactionsView,
    FundsView,
    AnalysisView,
    SettingsView,
    ApiDocsView,
    CloudStorageView,
    Toast,
    FundModal,
    AiChatButton,
    AiChatWindow
  },
  setup() {
    const { state, actions } = useStore()
    const showRegister = ref(false)
    const currentPage = ref('dashboard')
    const sidebarCollapsed = ref(false)
    const showFundModal = ref(false)
    const fundsRefreshTrigger = ref(0)
    const showAiChat = ref(false)
    const loginError = ref('')
    const registerError = ref('')
    const registerSuccess = ref('')
    const pageTitle = computed(() => PAGE_TITLES[currentPage.value] || '仪表盘')
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
      showFundModal.value = true
    }

    const handleFundSubmitted = () => {
      showFundModal.value = false
      fundsRefreshTrigger.value++
    }

      onMounted(async () => {
      initRouter((pageId) => {
        currentPage.value = pageId
      })
      const isAuth = await actions.checkAuth()
      if (isAuth) {
        await actions.fetchLedgers()
        const restored = actions.tryRestoreLastLedger()
        if (restored) {
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
      }
      if (state.isAuthenticated && state.currentLedgerId) {
        currentPage.value = getPageFromPath()
      }
    })

    return {
      state,
      showRegister,
      currentPage,
      sidebarCollapsed,
      showFundModal,
      showAiChat,
      pageTitle,
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
      handleFundSubmitted,
      fundsRefreshTrigger,
      loginError,
      registerError,
      registerSuccess
    }
  },
  template: `
    <div id="app">
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
        @create-ledger="handleCreateLedger"
        @logout="handleLogout"
      />

      <div v-else id="main-page" class="page active">
        <Sidebar
          :nav-items="navItems"
          :current-page="currentPage"
          :user-name="userName"
          :user-avatar="state.user?.avatar"
          :collapsed="sidebarCollapsed"
          @navigate="navigateTo"
          @logout="handleLogout"
          @switch-ledger="handleSwitchLedger"
        />
        <main class="main-content">
          <Header
            :page-title="pageTitle"
            @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed"
          />
          <div class="content-area">
            <DashboardView
              v-show="currentPage === 'dashboard'"
              :class="['view', { active: currentPage === 'dashboard' }]"
              @navigate="navigateTo"
            />
            <PositionsView
              v-show="currentPage === 'positions'"
              :class="['view', { active: currentPage === 'positions' }]"
            />
            <TransactionsView
              v-show="currentPage === 'transactions'"
              :class="['view', { active: currentPage === 'transactions' }]"
            />
            <FundsView
              v-show="currentPage === 'funds'"
              :class="['view', { active: currentPage === 'funds' }]"
              :refresh-trigger="fundsRefreshTrigger"
              @show-add-fund="handleShowFundModal"
            />
            <AnalysisView
              v-show="currentPage === 'analysis'"
              :class="['view', { active: currentPage === 'analysis' }]"
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
        :show="showFundModal"
        @close="showFundModal = false"
        @submitted="handleFundSubmitted"
      />
      <AiChatButton v-if="state.isAuthenticated && state.currentLedgerId && state.pluginCenterEnabled && state.enabledPlugins?.includes('fino-ai-chat')" @click="showAiChat = true" />
      <AiChatWindow
        :show="showAiChat"
        @close="showAiChat = false"
      />
    </div>
  `
}
