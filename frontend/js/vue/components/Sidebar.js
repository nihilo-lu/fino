export default {
  name: 'Sidebar',
  props: {
    navItems: Array,
    currentPage: String,
    userName: String,
    collapsed: Boolean
  },
  emits: ['navigate', 'logout', 'switch-ledger'],
  template: `
    <nav :class="['sidebar', { collapsed }]" id="sidebar">
      <div class="sidebar-header">
        <div class="logo-small">
          <span class="material-icons">trending_up</span>
          <span>投资追踪器</span>
        </div>
      </div>
      <div class="user-info">
        <div class="user-avatar">
          <span class="material-icons">person</span>
        </div>
        <div class="user-details">
          <span class="user-name">{{ userName }}</span>
          <span class="user-role">普通用户</span>
        </div>
      </div>
      <ul class="nav-menu">
        <li
          v-for="item in navItems"
          :key="item.id"
          :class="['nav-item', { active: currentPage === item.id }]"
          @click="$emit('navigate', item.id)"
        >
          <span class="material-icons">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </li>
      </ul>
      <div class="sidebar-footer">
        <button class="btn btn-outline btn-outline-secondary" @click="$emit('switch-ledger')">
          <span class="material-icons">swap_horiz</span>
          切换账本
        </button>
        <button class="btn btn-outline" @click="$emit('logout')">
          <span class="material-icons">logout</span>
          退出登录
        </button>
      </div>
    </nav>
  `
}
