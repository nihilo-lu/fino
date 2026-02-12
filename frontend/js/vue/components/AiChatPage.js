/**
 * 独立 AI 聊天页：左侧会话历史 + 右侧当前对话
 */
import { ref, watch, onMounted } from 'vue'
import { API_BASE } from '../utils/api.js'
import { useStore } from '../store/index.js'
import AiChatWindow from './AiChatWindow.js'

export default {
  name: 'AiChatPage',
  components: { AiChatWindow },
  props: {
    /** 从外部传入的关闭回调（如返回仪表盘） */
    onClose: { type: Function, default: null }
  },
  emits: ['close'],
  setup(props, { emit }) {
    const { actions } = useStore()
    const sessions = ref([])
    const currentSessionId = ref(null)
    const loadingSessions = ref(true)
    const deletingId = ref(null)

    const fetchSessions = async () => {
      loadingSessions.value = true
      try {
        const res = await fetch(`${API_BASE}/ai/chat/sessions`, { credentials: 'include' })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) return
        const list = data?.data ?? data
        sessions.value = Array.isArray(list) ? list : []
        if (sessions.value.length > 0 && !currentSessionId.value) {
          currentSessionId.value = sessions.value[0].id
        }
      } catch (_) {}
      loadingSessions.value = false
    }

    const createSession = async () => {
      try {
        const res = await fetch(`${API_BASE}/ai/chat/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ title: '新对话' })
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          actions.showToast(data?.message || '创建失败', 'error')
          return
        }
        const sess = data?.data ?? data
        const id = sess?.id
        if (id) {
          sessions.value = [{ id, title: sess.title || '新对话', created_at: sess.created_at, updated_at: sess.updated_at }, ...sessions.value]
          currentSessionId.value = id
        }
      } catch (_) {
        actions.showToast('创建失败', 'error')
      }
    }

    const deleteSession = async (id, e) => {
      e?.stopPropagation()
      if (deletingId.value) return
      deletingId.value = id
      try {
        const res = await fetch(`${API_BASE}/ai/chat/sessions/${id}`, {
          method: 'DELETE',
          credentials: 'include'
        })
        if (!res.ok) {
          actions.showToast('删除失败', 'error')
          return
        }
        sessions.value = sessions.value.filter((s) => s.id !== id)
        if (currentSessionId.value === id) {
          currentSessionId.value = sessions.value.length > 0 ? sessions.value[0].id : null
        }
      } catch (_) {
        actions.showToast('删除失败', 'error')
      } finally {
        deletingId.value = null
      }
    }

    const formatTime = (iso) => {
      if (!iso) return ''
      try {
        const d = new Date(iso)
        const now = new Date()
        const sameDay = d.getDate() === now.getDate() && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
        if (sameDay) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
        return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
      } catch {
        return iso
      }
    }

    const handleClose = () => {
      emit('close')
      if (props.onClose) props.onClose()
    }

    const onSessionSaved = () => {
      fetchSessions()
    }

    watch(currentSessionId, () => {
      // 切换会话时由 AiChatWindow 通过 sessionId 的 watch 自己加载
    })

    onMounted(() => {
      fetchSessions()
    })

    return {
      sessions,
      currentSessionId,
      loadingSessions,
      deletingId,
      fetchSessions,
      createSession,
      deleteSession,
      formatTime,
      handleClose,
      onSessionSaved
    }
  },
  template: `
    <div class="ai-chat-page">
      <aside class="ai-chat-page-sidebar">
        <div class="ai-chat-page-sidebar-header">
          <h2 class="ai-chat-page-sidebar-title">对话历史</h2>
          <button type="button" class="ai-chat-page-new-btn" @click="createSession">
            <span class="material-icons">add</span>
            <span>新建对话</span>
          </button>
        </div>
        <div class="ai-chat-page-sessions">
          <template v-if="loadingSessions">
            <div class="ai-chat-page-sessions-loading">加载中…</div>
          </template>
          <template v-else-if="sessions.length === 0">
            <div class="ai-chat-page-sessions-empty">暂无对话，点击上方「新建对话」开始</div>
          </template>
          <template v-else>
            <button
              v-for="s in sessions"
              :key="s.id"
              type="button"
              class="ai-chat-page-session-item"
              :class="{ active: currentSessionId === s.id }"
              @click="currentSessionId = s.id"
            >
              <span class="ai-chat-page-session-title">{{ s.title || '新对话' }}</span>
              <span class="ai-chat-page-session-time">{{ formatTime(s.updated_at || s.created_at) }}</span>
              <button
                type="button"
                class="ai-chat-page-session-delete"
                title="删除"
                :disabled="deletingId === s.id"
                @click="deleteSession(s.id, $event)"
              >
                <span class="material-icons">delete_outline</span>
              </button>
            </button>
          </template>
        </div>
      </aside>
      <div class="ai-chat-page-main">
        <template v-if="currentSessionId">
          <AiChatWindow
            :show="true"
            :standalone="true"
            :session-id="currentSessionId"
            @close="handleClose"
            @session-saved="onSessionSaved"
          />
        </template>
        <template v-else>
          <div class="ai-chat-page-welcome">
            <p>选择左侧对话或点击「新建对话」开始</p>
            <button type="button" class="btn btn-primary" @click="createSession">新建对话</button>
          </div>
        </template>
      </div>
    </div>
  `
}
