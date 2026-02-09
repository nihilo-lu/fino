import { useStore } from '../store/index.js'

/**
 * API 文档页面 - 文档说明与自定义 GET/POST 测试
 */
export default {
  name: 'ApiDocsView',
  props: {
    apiBase: { type: String, default: '' }
  },
  setup() {
    const { actions } = useStore()
    return { actions }
  },
  data() {
    return {
      // 测试面板
      testMethod: 'GET',
      testUrl: '/api/health',
      testToken: '',
      testQueryParams: 'ledger_id=1',
      testBody: '{}',
      testLoading: false,
      testResponse: null,
      testError: null,
      // 文档折叠
      expandedSections: {
        auth: true,
        endpoints: true,
        test: true
      }
    }
  },
  computed: {
    baseUrl() {
      if (this.apiBase) return this.apiBase
      return typeof window !== 'undefined' ? `${window.location.origin}` : ''
    },
    endpointGroups() {
      return [
        {
          name: '系统',
          endpoints: [
            { method: 'GET', path: '/api/health', desc: '健康检查', auth: false },
            { method: 'GET', path: '/api/pwa/config', desc: 'PWA 配置' }
          ]
        },
        {
          name: '认证',
          endpoints: [
            { method: 'POST', path: '/api/auth/login', desc: '登录', auth: false, body: '{"username","password"}' },
            { method: 'POST', path: '/api/auth/register', desc: '注册', auth: false },
            { method: 'POST', path: '/api/auth/logout', desc: '退出登录' },
            { method: 'GET', path: '/api/auth/me', desc: '当前用户信息 (Session)' },
            { method: 'GET', path: '/api/auth/token', desc: '获取 API Token' },
            { method: 'POST', path: '/api/auth/token/generate', desc: '生成 API Token' },
            { method: 'POST', path: '/api/auth/token/reset', desc: '重置 API Token' }
          ]
        },
        {
          name: '账本',
          endpoints: [
            { method: 'GET', path: '/api/ledgers', desc: '获取账本列表', params: 'username' },
            { method: 'POST', path: '/api/ledgers', desc: '创建账本', body: '{"username","name","description?"}' },
            { method: 'DELETE', path: '/api/ledgers/{id}', desc: '删除账本', params: 'username' }
          ]
        },
        {
          name: '账户',
          endpoints: [
            { method: 'GET', path: '/api/accounts', desc: '获取账户列表', params: 'ledger_id' },
            { method: 'POST', path: '/api/accounts', desc: '创建账户', body: '{"ledger_id","name","type","currency?","description?"}' },
            { method: 'DELETE', path: '/api/accounts/{id}', desc: '删除账户' }
          ]
        },
        {
          name: '交易',
          endpoints: [
            { method: 'GET', path: '/api/transactions', desc: '获取交易记录', params: 'ledger_id, account_id?, type?, start_date?, end_date?, limit?, offset?' },
            { method: 'POST', path: '/api/transactions', desc: '添加交易', body: '{"ledger_id","account_id","type","code","name","date","price?","quantity?","amount?","fee?","category?","notes?"}' },
            { method: 'DELETE', path: '/api/transactions/{id}', desc: '删除交易' }
          ]
        },
        {
          name: '资金明细',
          endpoints: [
            { method: 'GET', path: '/api/fund-transactions', desc: '获取资金流水', params: 'ledger_id, account_id?, type?, start_date?, end_date?, limit?, offset?' },
            { method: 'POST', path: '/api/fund-transactions', desc: '添加资金明细', body: '{"ledger_id","account_id","type","date","amount?","currency?","amount_cny?","description?"}' }
          ]
        },
        {
          name: '持仓与组合',
          endpoints: [
            { method: 'GET', path: '/api/portfolio/stats', desc: '组合统计', params: 'ledger_id, account_id?' },
            { method: 'GET', path: '/api/positions', desc: '持仓列表', params: 'ledger_id, account_id?' },
            { method: 'DELETE', path: '/api/positions/{id}', desc: '删除持仓' }
          ]
        },
        {
          name: '分析',
          endpoints: [
            { method: 'GET', path: '/api/analysis/returns', desc: '收益分析', params: 'ledger_id, account_id?' }
          ]
        },
        {
          name: '行情',
          endpoints: [
            { method: 'POST', path: '/api/market/price', desc: '获取股票价格', body: '{"code"}' },
            { method: 'POST', path: '/api/exchange-rate', desc: '获取汇率', body: '{"currency"}' }
          ]
        },
        {
          name: '参考数据',
          endpoints: [
            { method: 'GET', path: '/api/categories', desc: '投资分类' },
            { method: 'GET', path: '/api/currencies', desc: '币种列表' }
          ]
        }
      ]
    }
  },
  methods: {
    toggleSection(key) {
      this.expandedSections[key] = !this.expandedSections[key]
    },
    async runTest() {
      this.testLoading = true
      this.testError = null
      this.testResponse = null

      try {
        let url = this.testUrl.startsWith('http') ? this.testUrl : this.baseUrl + this.testUrl
        if (this.testMethod === 'GET' && this.testQueryParams.trim()) {
          const sep = url.includes('?') ? '&' : '?'
          url += sep + this.testQueryParams.trim()
        }

        const headers = { 'Content-Type': 'application/json' }
        if (this.testToken.trim()) {
          headers['Authorization'] = 'Bearer ' + this.testToken.trim()
        }

        const options = { method: this.testMethod, headers }
        if (this.testMethod === 'POST' || this.testMethod === 'PUT') {
          const body = this.testBody.trim() || '{}'
          try {
            JSON.parse(body)
            options.body = body
          } catch (e) {
            this.testError = '请求体不是有效的 JSON: ' + e.message
            return
          }
        }

        const resp = await fetch(url, { ...options, credentials: 'include' })
        const text = await resp.text()
        let parsed = null
        try {
          parsed = JSON.parse(text)
        } catch {
          parsed = text
        }

        this.testResponse = {
          status: resp.status,
          statusText: resp.statusText,
          headers: Object.fromEntries(resp.headers.entries()),
          body: typeof parsed === 'object' ? parsed : parsed
        }
      } catch (err) {
        this.testError = err.message || '请求失败'
      } finally {
        this.testLoading = false
      }
    },
    async loadToken() {
      const token = await this.actions.fetchToken()
      if (token) this.testToken = token
    },
    fillExample(ep) {
      const path = ep.path
      const method = ep.method
      this.testMethod = method
      this.testUrl = path.replace(/\{[^}]+\}/g, '1')
      this.testQueryParams = ''
      this.testBody = '{}'

      if (path.includes('/api/auth/login')) {
        this.testBody = '{"username":"your_username","password":"your_password"}'
      } else if (path.includes('/api/health')) {
        this.testQueryParams = ''
      } else if (path.includes('/api/ledgers')) {
        if (method === 'GET') this.testQueryParams = 'username=your_username'
      } else if (path.includes('/api/accounts')) {
        if (method === 'GET') this.testQueryParams = 'ledger_id=1'
        else if (method === 'POST') this.testBody = '{"ledger_id":1,"name":"主账户","type":"stock","currency":"CNY"}'
      } else if (path.includes('/api/transactions')) {
        if (method === 'GET') this.testQueryParams = 'ledger_id=1'
        else if (method === 'POST') this.testBody = '{"ledger_id":1,"account_id":1,"type":"buy","code":"600000","name":"浦发银行","date":"2024-01-15","price":10.5,"quantity":100}'
      } else if (path.includes('/api/fund-transactions')) {
        if (method === 'GET') this.testQueryParams = 'ledger_id=1'
        else if (method === 'POST') this.testBody = '{"ledger_id":1,"account_id":1,"type":"deposit","date":"2024-01-15","amount":10000,"currency":"CNY"}'
      } else if (path.includes('/api/portfolio') || path.includes('/api/positions')) {
        this.testQueryParams = 'ledger_id=1'
      } else if (path.includes('/api/analysis')) {
        this.testQueryParams = 'ledger_id=1'
      } else if (path.includes('/api/market/price')) {
        this.testBody = '{"code":"600000"}'
      } else if (path.includes('/api/exchange-rate')) {
        this.testBody = '{"currency":"USD"}'
      }
    }
  },
  template: `
    <div class="api-docs-view">
      <h1 class="api-docs-title">
        <span class="material-icons">api</span>
        API 文档
      </h1>

      <section class="api-docs-section">
        <h2 class="section-header" @click="expandedSections.auth = !expandedSections.auth">
          <span class="material-icons">lock</span>
          认证与 Token 使用
          <span class="material-icons expand-icon">{{ expandedSections.auth ? 'expand_less' : 'expand_more' }}</span>
        </h2>
        <div v-show="expandedSections.auth" class="section-content">
          <h3>1. 认证方式</h3>
          <p>除登录、注册、健康检查外，所有 API 均需认证。支持两种方式：</p>
          <ul>
            <li><strong>Session Cookie</strong>：Web 端登录后自动携带，无需额外配置</li>
            <li><strong>Bearer Token</strong>：在请求头添加 <code>Authorization: Bearer &lt;token&gt;</code></li>
          </ul>

          <h3>2. 获取 API Token</h3>
          <ol>
            <li>登录后进入「设置」→ 在 API Token 区域可查看或生成 Token</li>
            <li>或调用 <code>GET /api/auth/token</code> 查看已有 Token</li>
            <li>调用 <code>POST /api/auth/token/generate</code> 生成新 Token</li>
            <li>调用 <code>POST /api/auth/token/reset</code> 重置 Token（旧 Token 立即失效）</li>
          </ol>

          <h3>3. 调用示例</h3>
          <pre class="code-block">curl -X GET "{{ baseUrl }}/api/ledgers?username=your_username" \\
  -H "Authorization: Bearer YOUR_API_TOKEN"</pre>

          <pre class="code-block">curl -X POST "{{ baseUrl }}/api/auth/login" \\
  -H "Content-Type: application/json" \\
  -d '{"username":"your_username","password":"your_password"}'</pre>
        </div>
      </section>

      <section class="api-docs-section">
        <h2 class="section-header" @click="expandedSections.endpoints = !expandedSections.endpoints">
          <span class="material-icons">list</span>
          API 端点列表
          <span class="material-icons expand-icon">{{ expandedSections.endpoints ? 'expand_less' : 'expand_more' }}</span>
        </h2>
        <div v-show="expandedSections.endpoints" class="section-content">
          <div v-for="group in endpointGroups" :key="group.name" class="endpoint-group">
            <h4>{{ group.name }}</h4>
            <table class="endpoint-table">
              <thead>
                <tr>
                  <th>方法</th>
                  <th>路径</th>
                  <th>说明</th>
                  <th>参数/Body</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="ep in group.endpoints" :key="ep.path + ep.method">
                  <td><span :class="['method-badge', ep.method.toLowerCase()]">{{ ep.method }}</span></td>
                  <td><code>{{ ep.path }}</code></td>
                  <td>{{ ep.desc }}</td>
                  <td>
                    <span v-if="ep.params" class="param-hint">{{ ep.params }}</span>
                    <span v-else-if="ep.body" class="param-hint">{{ ep.body }}</span>
                    <span v-else>-</span>
                  </td>
                  <td>
                    <button class="btn-link" @click="fillExample(ep)" title="填充到测试">填充</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section class="api-docs-section">
        <h2 class="section-header" @click="expandedSections.test = !expandedSections.test">
          <span class="material-icons">play_circle</span>
          自定义 API 测试
          <span class="material-icons expand-icon">{{ expandedSections.test ? 'expand_less' : 'expand_more' }}</span>
        </h2>
        <div v-show="expandedSections.test" class="section-content">
          <div class="test-panel">
            <div class="test-row">
              <select v-model="testMethod" class="method-select">
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="DELETE">DELETE</option>
              </select>
              <input v-model="testUrl" type="text" class="url-input" placeholder="路径，如 /api/health" />
              <button class="btn btn-primary" :disabled="testLoading" @click="runTest">
                {{ testLoading ? '请求中...' : '发送' }}
              </button>
            </div>
            <div class="test-row">
              <label>Token (Bearer):</label>
              <input v-model="testToken" type="password" class="token-input" placeholder="可选，API Token" />
              <button class="btn btn-outline btn-sm" @click="loadToken">获取我的 Token</button>
            </div>
            <div v-if="testMethod === 'GET'" class="test-row">
              <label>Query 参数:</label>
              <input v-model="testQueryParams" type="text" class="query-input" placeholder="如 ledger_id=1&account_id=2" />
            </div>
            <div v-if="testMethod === 'POST' || testMethod === 'PUT'" class="test-row">
              <label>请求体 (JSON):</label>
              <textarea v-model="testBody" class="body-textarea" rows="6" placeholder='{"key": "value"}'></textarea>
            </div>
          </div>

          <div v-if="testError" class="test-error">
            <span class="material-icons">error</span> {{ testError }}
          </div>
          <div v-if="testResponse" class="test-response">
            <h4>响应 <span class="status-badge" :class="testResponse.status >= 400 ? 'error' : 'ok'">{{ testResponse.status }} {{ testResponse.statusText }}</span></h4>
            <pre class="response-body">{{ typeof testResponse.body === 'object' ? JSON.stringify(testResponse.body, null, 2) : testResponse.body }}</pre>
          </div>
        </div>
      </section>
    </div>
  `
}
