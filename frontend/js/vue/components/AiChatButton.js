/**
 * 可拖动的 AI 聊天入口按钮
 * 固定在右下角，可拖动到任意位置；有未读消息时显示提醒角标
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useStore } from '../store/index.js'

const STORAGE_KEY = 'ai_chat_button_pos'

export default {
  name: 'AiChatButton',
  emits: ['click'],
  setup(props, { emit }) {
    const { state } = useStore()
    const x = ref(0)
    const y = ref(0)
    const isDragging = ref(false)
    const didMove = ref(false)
    const dragStart = ref({ x: 0, y: 0, elX: 0, elY: 0 })

    const loadPosition = () => {
      try {
        const saved = localStorage.getItem(STORAGE_KEY)
        if (saved) {
          const { x: sx, y: sy } = JSON.parse(saved)
          x.value = typeof sx === 'number' ? sx : null
          y.value = typeof sy === 'number' ? sy : null
        } else {
          x.value = null
          y.value = null
        }
      } catch {
        x.value = null
        y.value = null
      }
    }

    const savePosition = () => {
      try {
        if (x.value != null && y.value != null) {
          localStorage.setItem(STORAGE_KEY, JSON.stringify({ x: x.value, y: y.value }))
        }
      } catch {}
    }

    const getDefaultPos = () => ({
      x: window.innerWidth - 72,
      y: window.innerHeight - 72
    })

    const onPointerDown = (e) => {
      if (e.button !== 0) return
      if (e.target.closest('.ai-chat-btn-icon')) {
        isDragging.value = true
        didMove.value = false
        const def = getDefaultPos()
        dragStart.value = {
          x: e.clientX,
          y: e.clientY,
          elX: x.value ?? def.x,
          elY: y.value ?? def.y
        }
        if (x.value == null) x.value = def.x
        if (y.value == null) y.value = def.y
      }
    }

    const onPointerMove = (e) => {
      if (!isDragging.value) return
      didMove.value = true
      const dx = e.clientX - dragStart.value.x
      const dy = e.clientY - dragStart.value.y
      const maxX = window.innerWidth - 56
      const maxY = window.innerHeight - 56
      const nx = Math.max(0, Math.min(maxX, dragStart.value.elX + dx))
      const ny = Math.max(0, Math.min(maxY, dragStart.value.elY + dy))
      x.value = nx
      y.value = ny
    }

    const onPointerUp = () => {
      if (isDragging.value) {
        isDragging.value = false
        savePosition()
      }
    }

    const onClick = (e) => {
      if (didMove.value) return
      if (e.target.closest('.ai-chat-btn-icon')) {
        emit('click')
      }
    }

    onMounted(() => {
      loadPosition()
      window.addEventListener('pointermove', onPointerMove)
      window.addEventListener('pointerup', onPointerUp)
      window.addEventListener('pointerleave', onPointerUp)
    })

    onUnmounted(() => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointerleave', onPointerUp)
    })

    const style = computed(() => {
      const def = { right: 24, bottom: 24 }
      if (x.value != null && y.value != null) {
        return { left: x.value + 'px', top: y.value + 'px' }
      }
      return { right: '24px', bottom: '24px' }
    })

    return {
      x,
      y,
      style,
      isDragging,
      onPointerDown,
      onClick,
      hasUnread: computed(() => state.aiChatUnread)
    }
  },
  template: `
    <div
      class="ai-chat-fab"
      :style="style"
      @pointerdown="onPointerDown"
      @click="onClick"
    >
      <div class="ai-chat-btn-icon" :class="{ 'has-unread': hasUnread }" :title="hasUnread ? 'AI 助手（有未读消息）' : 'AI 助手'">
        <span class="material-icons">smart_toy</span>
        <span v-if="hasUnread" class="ai-chat-fab-badge" aria-label="未读消息"></span>
      </div>
    </div>
  `
}
