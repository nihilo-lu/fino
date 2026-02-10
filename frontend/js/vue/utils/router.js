/**
 * 简易路由：URL 与页面 ID 同步
 * 使用 History API，刷新时保持当前页面
 */

const PATH_TO_PAGE = {
  '/': 'dashboard',
  '/dashboard': 'dashboard',
  '/transactions': 'transactions',
  '/funds': 'funds',
  '/analysis': 'analysis',
  '/cloud-storage': 'cloud-storage',
  '/settings': 'settings',
  '/api-docs': 'api-docs'
}

const PAGE_TO_PATH = {
  dashboard: '/dashboard',
  transactions: '/transactions',
  funds: '/funds',
  analysis: '/analysis',
  'cloud-storage': '/cloud-storage',
  settings: '/settings',
  'api-docs': '/api-docs'
}

export function getPageFromPath() {
  const path = window.location.pathname || '/'
  return PATH_TO_PAGE[path] || 'dashboard'
}

export function getPathFromPage(pageId) {
  return PAGE_TO_PATH[pageId] || '/dashboard'
}

export function pushState(pageId) {
  const path = getPathFromPage(pageId)
  if (window.location.pathname !== path) {
    window.history.pushState({ pageId }, '', path)
  }
}

export function replaceState(pageId) {
  const path = getPathFromPage(pageId)
  window.history.replaceState({ pageId }, '', path)
}

export function initRouter(onPopState) {
  window.addEventListener('popstate', (e) => {
    const pageId = e.state?.pageId ?? getPageFromPath()
    onPopState(pageId)
  })
}
