import { ref, onMounted, watch, computed, nextTick } from 'vue'
import { useStore } from '../store/index.js'
import { formatCurrency } from '../utils/formatters.js'

export default {
  name: 'AnalysisView',
  props: { currentPage: { type: String, default: '' } },
  setup(props) {
    const { state, actions } = useStore()
    const navReturn = ref('0.00')
    const simpleReturn = ref('0.00')
    const realizedPl = ref({ total_cny: 0, details: [] })
    const navDetails = ref([])
    const navDetailsExpanded = ref(false)
    const navSortKey = ref('date')
    const navSortOrder = ref('desc')
    const navPage = ref(1)
    const navPageSize = 20

    const load = async () => {
      if (!state.currentLedgerId) return
      const data = await actions.fetchAnalysis()
      if (data) {
        navReturn.value = (data.nav_return != null ? (data.nav_return * 100).toFixed(2) : '0.00') + '%'
        simpleReturn.value = (data.simple_return != null ? (data.simple_return * 100).toFixed(2) : '0.00') + '%'
        realizedPl.value = data.realized_pl || { total_cny: 0, details: [] }
        navDetails.value = data.nav_details || []
        navPage.value = 1
      }
    }

    const formatPercent = (val) => {
      if (val == null) return '-'
      if (typeof val === 'string' && val.includes('%')) return val
      if (typeof val === 'number') return (val * 100).toFixed(2) + '%'
      return String(val)
    }

    const realizedPlTotalClass = computed(() => {
      const t = realizedPl.value.total_cny
      return t >= 0 ? 'profit-positive' : 'profit-negative'
    })

    const hasDetails = computed(() => (realizedPl.value.details || []).length > 0)
    const hasNavDetails = computed(() => (navDetails.value || []).length > 0)

    const navColumns = [
      { key: 'date', label: '日期' },
      { key: '发生金额', label: '发生金额' },
      { key: '确认份额', label: '确认份额' },
      { key: '确认净值', label: '确认净值' },
      { key: '总份额', label: '总份额' },
      { key: '单位净值', label: '单位净值' },
      { key: '当日净资产', label: '当日净资产' },
      { key: '当日损益', label: '当日损益' },
      { key: '当日收益率', label: '当日收益率' },
      { key: '累计收益率', label: '累计收益率' },
      { key: '总资产', label: '总资产' }
    ]

    const sortedNavDetails = computed(() => {
      const rows = [...(navDetails.value || [])]
      const key = navSortKey.value
      const order = navSortOrder.value
      const mul = order === 'asc' ? 1 : -1
      rows.sort((a, b) => {
        const va = a[key]
        const vb = b[key]
        if (va == null && vb == null) return 0
        if (va == null) return mul
        if (vb == null) return -mul
        if (key === 'date') return mul * String(va).localeCompare(String(vb))
        const na = Number(va)
        const nb = Number(vb)
        if (!isNaN(na) && !isNaN(nb)) return mul * (na - nb)
        return mul * String(va).localeCompare(String(vb))
      })
      return rows
    })

    const toggleNavSort = (key) => {
      if (navSortKey.value === key) {
        navSortOrder.value = navSortOrder.value === 'asc' ? 'desc' : 'asc'
      } else {
        navSortKey.value = key
        navSortOrder.value = key === 'date' ? 'desc' : 'asc'
      }
      navPage.value = 1
    }

    const navTotalPages = computed(() => Math.max(1, Math.ceil((sortedNavDetails.value?.length || 0) / navPageSize)))
    const paginatedNavDetails = computed(() => {
      const list = sortedNavDetails.value || []
      const start = (navPage.value - 1) * navPageSize
      return list.slice(start, start + navPageSize)
    })
    const navPageStart = computed(() => (navPage.value - 1) * navPageSize + 1)
    const navPageEnd = computed(() => Math.min(navPage.value * navPageSize, sortedNavDetails.value?.length || 0))
    const goToNavPage = (p) => { navPage.value = Math.max(1, Math.min(p, navTotalPages.value)) }

    const navPageNumbers = computed(() => {
      const total = navTotalPages.value
      const curr = navPage.value
      if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
      const pages = []
      if (curr <= 4) {
        for (let i = 1; i <= 5; i++) pages.push(i)
        pages.push('...')
        pages.push(total)
      } else if (curr >= total - 3) {
        pages.push(1)
        pages.push('...')
        for (let i = total - 4; i <= total; i++) pages.push(i)
      } else {
        pages.push(1)
        pages.push('...')
        for (let i = curr - 1; i <= curr + 1; i++) pages.push(i)
        pages.push('...')
        pages.push(total)
      }
      return pages
    })

    const navSortIcon = (key) => {
      if (navSortKey.value !== key) return 'unsorted'
      return navSortOrder.value === 'asc' ? 'asc' : 'desc'
    }

    const navSortActive = (key) => navSortKey.value === key

    const drawReturnChart = () => {
      if (props.currentPage !== 'analysis') return
      if (!hasNavDetails.value || navDetails.value.length === 0) return
      const el = document.getElementById('return-trend-chart-target')
      if (!el) return
      actions.drawReturnTrendChart(el, navDetails.value)
    }

    onMounted(() => {
      load().then(() => nextTick(() => setTimeout(drawReturnChart, 150)))
    })
    watch(() => [state.currentLedgerId, state.currentAccountId, state.dashboardRefreshTrigger], () => {
      load().then(() => nextTick(() => setTimeout(drawReturnChart, 150)))
    })
    watch(
      () => [props.currentPage, navDetails.value],
      () => nextTick(() => setTimeout(drawReturnChart, 150)),
      { deep: true }
    )

    return {
      state,
      navReturn,
      simpleReturn,
      realizedPl,
      navDetails,
      navDetailsExpanded,
      navSortKey,
      navSortOrder,
      navColumns,
      sortedNavDetails,
      paginatedNavDetails,
      navPage,
      navPageSize,
      navTotalPages,
      navPageNumbers,
      navPageStart,
      navPageEnd,
      goToNavPage,
      toggleNavSort,
      navSortIcon,
      navSortActive,
      realizedPlTotalClass,
      hasDetails,
      hasNavDetails,
      formatCurrency,
      formatPercent
    }
  },
  template: `
    <div id="analysis-view" class="view">
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-content">
            <span class="stat-label">净值法累计收益率</span>
            <span class="stat-value">{{ navReturn }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-content">
            <span class="stat-label">简单收益率</span>
            <span class="stat-value">{{ simpleReturn }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-content">
            <span class="stat-label">已实现损益（人民币）</span>
            <span :class="['stat-value', realizedPlTotalClass]">{{ formatCurrency(realizedPl.total_cny) }}</span>
          </div>
        </div>
      </div>
      <div class="chart-card">
        <div class="card-header"><h3>收益率走势</h3></div>
        <div class="card-body">
          <div class="chart-container">
            <div v-if="hasNavDetails" id="return-trend-chart-target" class="chart-target"></div>
            <div v-else class="empty-state">
              <span class="material-icons">show_chart</span>
              <p>暂无净值数据，请先有资金或交易记录并生成收益率</p>
            </div>
          </div>
        </div>
      </div>
      <div class="chart-card">
        <div class="card-header card-header-collapsible" :class="{ expanded: navDetailsExpanded }" @click="navDetailsExpanded = !navDetailsExpanded">
          <h3>净值明细表</h3>
          <span class="material-icons expand-icon">{{ navDetailsExpanded ? 'expand_less' : 'expand_more' }}</span>
        </div>
        <div v-show="navDetailsExpanded" class="card-body">
          <div v-if="!hasNavDetails" class="empty-state">
            <span class="material-icons">table_chart</span>
            <p>暂无净值明细数据</p>
          </div>
          <div v-else class="table-responsive">
            <table class="data-table data-table-sortable">
              <thead>
                <tr>
                  <th v-for="col in navColumns" :key="col.key" :class="['sortable', { active: navSortActive(col.key) }]" @click.stop="toggleNavSort(col.key)">
                    {{ col.label }}
                    <span class="sort-icon-wrap">
                      <span v-if="navSortIcon(col.key) === 'asc'" class="material-icons sort-icon sort-asc" title="升序">arrow_drop_up</span>
                      <span v-else-if="navSortIcon(col.key) === 'desc'" class="material-icons sort-icon sort-desc" title="降序">arrow_drop_down</span>
                      <span v-else class="material-icons sort-unsorted" title="点击排序">unfold_more</span>
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in paginatedNavDetails" :key="(navPage - 1) * navPageSize + i">
                  <td>{{ row.date }}</td>
                  <td>{{ formatCurrency(row['发生金额']) }}</td>
                  <td>{{ row['确认份额'] != null ? Number(row['确认份额']).toLocaleString(undefined, { maximumFractionDigits: 6 }) : '-' }}</td>
                  <td>{{ row['确认净值'] != null ? Number(row['确认净值']).toLocaleString(undefined, { maximumFractionDigits: 6 }) : '-' }}</td>
                  <td>{{ row['总份额'] != null ? Number(row['总份额']).toLocaleString(undefined, { maximumFractionDigits: 6 }) : '-' }}</td>
                  <td>{{ row['单位净值'] != null ? Number(row['单位净值']).toLocaleString(undefined, { maximumFractionDigits: 6 }) : '-' }}</td>
                  <td>{{ formatCurrency(row['当日净资产']) }}</td>
                  <td :class="(row['当日损益'] ?? 0) >= 0 ? 'profit-positive' : 'profit-negative'">{{ formatCurrency(row['当日损益']) }}</td>
                  <td>{{ formatPercent(row['当日收益率']) }}</td>
                  <td>{{ formatPercent(row['累计收益率']) }}</td>
                  <td>{{ formatCurrency(row['总资产']) }}</td>
                </tr>
              </tbody>
            </table>
            <div v-if="sortedNavDetails.length > navPageSize" class="pagination-wrapper">
              <span class="pagination-info">第 {{ navPageStart }}-{{ navPageEnd }} 条，共 {{ sortedNavDetails.length }} 条</span>
              <div class="pagination-group">
                <div class="pagination">
                  <button type="button" class="pagination-btn" title="首页" :disabled="navPage <= 1" @click="goToNavPage(1)">
                    <span class="material-icons">first_page</span>
                  </button>
                  <button type="button" class="pagination-btn" title="上一页" :disabled="navPage <= 1" @click="goToNavPage(navPage - 1)">
                    <span class="material-icons">chevron_left</span>
                  </button>
                  <template v-for="(p, idx) in navPageNumbers" :key="idx">
                    <button v-if="p === '...'" type="button" class="pagination-btn pagination-ellipsis" disabled>…</button>
                    <button v-else type="button" class="pagination-btn pagination-num" :class="{ active: navPage === p }" @click="goToNavPage(p)">{{ p }}</button>
                  </template>
                  <button type="button" class="pagination-btn" title="下一页" :disabled="navPage >= navTotalPages" @click="goToNavPage(navPage + 1)">
                    <span class="material-icons">chevron_right</span>
                  </button>
                  <button type="button" class="pagination-btn" title="末页" :disabled="navPage >= navTotalPages" @click="goToNavPage(navTotalPages)">
                    <span class="material-icons">last_page</span>
                  </button>
                </div>
                <div class="pagination-jump" title="输入页码后回车跳转">
                  <input type="number" :min="1" :max="navTotalPages" :value="navPage" @keyup.enter="(e) => { const v = parseInt(e.target.value, 10); if (!isNaN(v)) goToNavPage(v) }" @change="(e) => { const v = parseInt(e.target.value, 10); if (!isNaN(v)) goToNavPage(v) }" />
                  <span class="pagination-jump-suffix">/ {{ navTotalPages }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="chart-card">
        <div class="card-header"><h3>已实现损益明细</h3></div>
        <div class="card-body">
          <div v-if="!hasDetails" class="empty-state">
            <span class="material-icons">receipt_long</span>
            <p>暂无已实现损益记录</p>
          </div>
          <div v-else class="table-responsive">
            <table class="data-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>代码</th>
                  <th>名称</th>
                  <th>账户</th>
                  <th>收入</th>
                  <th>成本</th>
                  <th>利润</th>
                  <th>报表币种损益</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in realizedPl.details" :key="i">
                  <td>{{ row['日期'] }}</td>
                  <td>{{ row['代码'] }}</td>
                  <td>{{ row['名称'] }}</td>
                  <td>{{ row['账户'] }}</td>
                  <td>{{ formatCurrency(row['收入']) }}</td>
                  <td>{{ formatCurrency(row['成本']) }}</td>
                  <td :class="(row['利润'] || 0) >= 0 ? 'profit-positive' : 'profit-negative'">{{ formatCurrency(row['利润']) }}</td>
                  <td :class="(row['报表币种损益'] ?? row['利润'] ?? 0) >= 0 ? 'profit-positive' : 'profit-negative'">{{ formatCurrency(row['报表币种损益'] ?? row['利润']) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `
}
