/**
 * AI 聊天窗口 - 支持流式响应、思维链、图片/文件/语音、AI 头像、自由拖动
 */
import { ref, reactive, watch, nextTick, onMounted, onUnmounted, computed } from 'vue'
import { API_BASE } from '../utils/api.js'
import { useStore } from '../store/index.js'

const WINDOW_POS_STORAGE_KEY = 'ai_chat_window_pos'
const DEFAULT_WIDTH = 400
const DEFAULT_HEIGHT = 520
const MIN_WIDTH = 280
const MIN_HEIGHT = 300
const MAX_WIDTH_RATIO = 0.9
const MAX_HEIGHT_RATIO = 0.85

const SYSTEM_PROMPT = `你是一个投资理财助手，帮助用户分析投资组合、理解收益数据、给出合理建议。回答要简洁专业，适当使用数据支撑。`

const IMAGE_MIME = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
const MAX_IMAGE_SIZE = 4 * 1024 * 1024 // 4MB
const MAX_FILE_SIZE = 512 * 1024 // 512KB for text files

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => {
      const data = (fr.result || '').split(',')[1]
      resolve(data ? { data, mime: file.type } : null)
    }
    fr.onerror = () => reject(new Error('读取失败'))
    fr.readAsDataURL(file)
  })
}

function readAsText(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(fr.result || '')
    fr.onerror = () => reject(new Error('读取失败'))
    fr.readAsText(file, 'utf-8')
  })
}

export default {
  name: 'AiChatWindow',
  props: {
    show: Boolean
  },
  emits: ['close'],
  setup(props, { emit }) {
    const { actions } = useStore()
    const messages = ref([])
    const inputText = ref('')
    const loading = ref(false)
    const chatListRef = ref(null)
    const maximized = ref(false)
    const winX = ref(null)
    const winY = ref(null)
    const winW = ref(null)
    const winH = ref(null)
    const isDragging = ref(false)
    const dragStart = ref({ x: 0, y: 0, elX: 0, elY: 0 })
    const resizeDir = ref(null) // 'e' | 's' | 'se'
    const resizeStart = ref({ x: 0, y: 0, w: 0, h: 0 })
    const attachments = ref([]) // { type: 'image'|'file', data?, mime?, name?, text?, preview? }
    const thinkingCollapsed = ref({}) // idx -> true 表示折叠
    const aiConfig = ref({ avatar_url: '', show_thinking: true })
    const isRecording = ref(false)
    const voiceSupport = ref(false)
    let recognition = null

    const scrollToBottom = () => {
      nextTick(() => {
        if (chatListRef.value) {
          chatListRef.value.scrollTop = chatListRef.value.scrollHeight
        }
      })
    }

    const fetchAiConfig = async () => {
      try {
        const res = await fetch(`${API_BASE}/ai/config`, { credentials: 'include' })
        const data = await res.json().catch(() => ({}))
        if (res.ok && data?.data) {
          aiConfig.value = { ...aiConfig.value, ...data.data }
        }
      } catch (_) {}
    }

    const toggleThinking = (idx) => {
      thinkingCollapsed.value = { ...thinkingCollapsed.value, [idx]: !thinkingCollapsed.value[idx] }
    }

    const loadWindowPosition = () => {
      try {
        const saved = localStorage.getItem(WINDOW_POS_STORAGE_KEY)
        if (saved) {
          const data = JSON.parse(saved)
          winX.value = typeof data.x === 'number' ? data.x : null
          winY.value = typeof data.y === 'number' ? data.y : null
          winW.value = typeof data.w === 'number' ? data.w : null
          winH.value = typeof data.h === 'number' ? data.h : null
        } else {
          winX.value = null
          winY.value = null
          winW.value = null
          winH.value = null
        }
      } catch {
        winX.value = null
        winY.value = null
        winW.value = null
        winH.value = null
      }
    }

    const saveWindowState = () => {
      try {
        const obj = {}
        if (winX.value != null) obj.x = winX.value
        if (winY.value != null) obj.y = winY.value
        if (winW.value != null) obj.w = winW.value
        if (winH.value != null) obj.h = winH.value
        if (Object.keys(obj).length) {
          localStorage.setItem(WINDOW_POS_STORAGE_KEY, JSON.stringify(obj))
        }
      } catch {}
    }

    const getCurrentSize = () => ({
      w: winW.value ?? DEFAULT_WIDTH,
      h: winH.value ?? DEFAULT_HEIGHT
    })

    const getDefaultWindowPos = () => {
      const { w, h } = getCurrentSize()
      return {
        x: window.innerWidth - w - 24,
        y: Math.max(0, window.innerHeight - h - 90)
      }
    }

    const onHeaderPointerDown = (e) => {
      if (e.button !== 0 || maximized.value) return
      if (e.target.closest('.ai-chat-header-actions')) return
      isDragging.value = true
      const def = getDefaultWindowPos()
      const elX = winX.value ?? def.x
      const elY = winY.value ?? def.y
      dragStart.value = { x: e.clientX, y: e.clientY, elX, elY }
      if (winX.value == null) winX.value = def.x
      if (winY.value == null) winY.value = def.y
    }

    const onResizePointerDown = (e, dir) => {
      if (e.button !== 0 || maximized.value) return
      e.stopPropagation()
      resizeDir.value = dir
      const { w, h } = getCurrentSize()
      resizeStart.value = { x: e.clientX, y: e.clientY, w, h }
    }

    const clampSize = (w, h) => {
      const maxW = Math.floor(window.innerWidth * MAX_WIDTH_RATIO)
      const maxH = Math.floor(window.innerHeight * MAX_HEIGHT_RATIO)
      return {
        w: Math.max(MIN_WIDTH, Math.min(maxW, w)),
        h: Math.max(MIN_HEIGHT, Math.min(maxH, h))
      }
    }

    const onPointerMove = (e) => {
      if (resizeDir.value) {
        const dx = e.clientX - resizeStart.value.x
        const dy = e.clientY - resizeStart.value.y
        let w = resizeStart.value.w
        let h = resizeStart.value.h
        if (resizeDir.value === 'e' || resizeDir.value === 'se') w += dx
        if (resizeDir.value === 's' || resizeDir.value === 'se') h += dy
        const clamped = clampSize(w, h)
        winW.value = clamped.w
        winH.value = clamped.h
        return
      }
      if (!isDragging.value) return
      const dx = e.clientX - dragStart.value.x
      const dy = e.clientY - dragStart.value.y
      const { w } = getCurrentSize()
      const maxX = window.innerWidth - w
      const maxY = window.innerHeight - 100
      winX.value = Math.max(0, Math.min(maxX, dragStart.value.elX + dx))
      winY.value = Math.max(0, Math.min(maxY, dragStart.value.elY + dy))
    }

    const onPointerUp = () => {
      if (resizeDir.value) {
        resizeDir.value = null
        saveWindowState()
      }
      if (isDragging.value) {
        isDragging.value = false
        saveWindowState()
      }
    }

    const windowStyle = computed(() => {
      if (maximized.value) return {}
      const style = {}
      if (winX.value != null && winY.value != null) {
        style.left = winX.value + 'px'
        style.top = winY.value + 'px'
        style.right = 'auto'
        style.bottom = 'auto'
      }
      if (winW.value != null) style.width = winW.value + 'px'
      if (winH.value != null) style.height = winH.value + 'px'
      return style
    })

    watch(() => props.show, (v) => {
      if (v) {
        loadWindowPosition()
        if (messages.value.length === 0) {
          messages.value = [
            { role: 'assistant', content: '你好！我是投资理财助手，可以帮你分析投资组合、理解收益数据。有什么想聊的吗？' }
          ]
        }
        fetchAiConfig()
        scrollToBottom()
      }
    })

    onMounted(() => {
      window.addEventListener('pointermove', onPointerMove)
      window.addEventListener('pointerup', onPointerUp)
      window.addEventListener('pointerleave', onPointerUp)
    })
    onUnmounted(() => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointerleave', onPointerUp)
    })

    const addImage = (file) => {
      if (!IMAGE_MIME.includes(file.type) || file.size > MAX_IMAGE_SIZE) {
        actions.showToast('请选择 JPG/PNG/GIF/WebP 图片，且不超过 4MB', 'warning')
        return
      }
      readAsBase64(file).then((res) => {
        if (res) {
          attachments.value = [
            ...attachments.value,
            { type: 'image', data: res.data, mime: res.mime, preview: URL.createObjectURL(file) }
          ]
        }
      }).catch(() => actions.showToast('图片读取失败', 'error'))
    }

    const addFile = (file) => {
      if (file.size > MAX_FILE_SIZE) {
        actions.showToast('文件不超过 512KB', 'warning')
        return
      }
      const name = file.name
      const isText = file.type.startsWith('text/') || /\.(txt|md|json|csv)$/i.test(name)
      if (isText) {
        readAsText(file).then((text) => {
          attachments.value = [...attachments.value, { type: 'file', name, text }]
        }).catch(() => actions.showToast('文件读取失败', 'error'))
      } else {
        attachments.value = [...attachments.value, { type: 'file', name }]
      }
    }

    const removeAttachment = (idx) => {
      const a = attachments.value[idx]
      if (a?.preview) URL.revokeObjectURL(a.preview)
      attachments.value = attachments.value.filter((_, i) => i !== idx)
    }

    const triggerFileInput = (accept) => {
      const input = document.createElement('input')
      input.type = 'file'
      input.multiple = true
      if (accept && accept.startsWith('image')) {
        input.accept = 'image/*'
        input.onchange = () => {
          for (const file of Array.from(input.files || [])) addImage(file)
        }
      } else {
        input.accept = ''
        input.onchange = () => {
          for (const file of Array.from(input.files || [])) addFile(file)
        }
      }
      input.click()
    }

    const startVoiceInput = () => {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
      if (!SpeechRecognition) {
        actions.showToast('当前浏览器不支持语音输入', 'warning')
        return
      }
      if (!recognition) recognition = new SpeechRecognition()
      recognition.lang = 'zh-CN'
      recognition.continuous = true
      recognition.interimResults = true
      recognition.onresult = (e) => {
        const last = e.results.length - 1
        const text = e.results[last][0].transcript
        if (e.results[last].isFinal && text) {
          inputText.value = (inputText.value + text).trim()
        }
      }
      recognition.onerror = () => {
        isRecording.value = false
      }
      recognition.start()
      isRecording.value = true
    }

    const stopVoiceInput = () => {
      if (recognition) recognition.stop()
      isRecording.value = false
    }

    onMounted(() => {
      voiceSupport.value = !!(window.SpeechRecognition || window.webkitSpeechRecognition)
    })

    const handleSend = async () => {
      const text = inputText.value.trim()
      const hasAttachments = attachments.value.length > 0
      if ((!text && !hasAttachments) || loading.value) return

      if (text.toLowerCase() === '/clear') {
        clearChat()
        inputText.value = ''
        attachments.value = []
        return
      }

      let userContent = text
      const fileTexts = attachments.value.filter(a => a.type === 'file' && a.text).map(a => `[文件 ${a.name}]\n${a.text}`)
      if (fileTexts.length) userContent = [userContent, ...fileTexts].filter(Boolean).join('\n\n')

      const userMsg = { role: 'user', content: userContent, attachments: [...attachments.value] }
      messages.value.push(userMsg)
      inputText.value = ''
      const currentAttachments = attachments.value.map(a => {
        if (a.type === 'image' && a.data) return { type: 'image', data: a.data, mime: a.mime }
        return null
      }).filter(Boolean)
      attachments.value = []
      loading.value = true

      const assistantMsg = reactive({
        role: 'assistant',
        content: '',
        thinking: '',
        streaming: true
      })
      messages.value.push(assistantMsg)
      scrollToBottom()

      const chatMessages = messages.value.slice(0, -1).map(m => ({
        role: m.role,
        content: typeof m.content === 'string' ? m.content : (m.content && m.content.text) || ''
      }))
      chatMessages.unshift({ role: 'system', content: SYSTEM_PROMPT })
      chatMessages.push({ role: 'user', content: userContent })

      try {
        const response = await fetch(`${API_BASE}/ai/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            messages: chatMessages,
            stream: true,
            attachments: currentAttachments
          })
        })

        if (!response.ok) {
          const err = await response.json().catch(() => ({}))
          throw new Error(err.error || '请求失败')
        }

        const reader = response.body?.getReader()
        const decoder = new TextDecoder()
        if (!reader) throw new Error('无法读取响应')

        let buffer = ''
        assistantMsg.streaming = true

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                if (data.type === 'thinking' && data.content) {
                  assistantMsg.thinking = (assistantMsg.thinking || '') + data.content
                } else if (data.type === 'content' && data.content) {
                  assistantMsg.content = (assistantMsg.content || '') + data.content
                }
              } catch {}
            }
          }
          await nextTick()
          await new Promise(r => setTimeout(r, 0))
          scrollToBottom()
        }
      } catch (e) {
        assistantMsg.content = '抱歉，发生错误：' + (e.message || '请求失败')
      } finally {
        assistantMsg.streaming = false
        loading.value = false
        scrollToBottom()
      }
    }

    const handleKeydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    }

    const clearChat = () => {
      messages.value = [
        { role: 'assistant', content: '对话已清空，有什么想聊的吗？' }
      ]
      scrollToBottom()
    }

    const toggleMaximize = () => {
      maximized.value = !maximized.value
      if (!maximized.value && winX.value == null) loadWindowPosition()
      scrollToBottom()
    }

    const defaultAvatarUrl = '' // 可改为默认头像 URL

    return {
      messages,
      inputText,
      loading,
      chatListRef,
      maximized,
      attachments,
      thinkingCollapsed,
      aiConfig,
      isRecording,
      voiceSupport,
      toggleThinking,
      removeAttachment,
      triggerFileInput,
      startVoiceInput,
      stopVoiceInput,
      handleSend,
      handleKeydown,
      clearChat,
      toggleMaximize,
      scrollToBottom,
      defaultAvatarUrl,
      windowStyle,
      isDragging,
      onHeaderPointerDown,
      onResizePointerDown,
      resizeDir
    }
  },
  template: `
    <div v-if="show" :class="['ai-chat-window', { maximized, dragging: isDragging, resizing: resizeDir }]" :style="windowStyle">
      <div class="ai-chat-header ai-chat-header-draggable" @pointerdown="onHeaderPointerDown">
        <div class="ai-chat-header-title">
          <img
            v-if="aiConfig.avatar_url || defaultAvatarUrl"
            :src="aiConfig.avatar_url || defaultAvatarUrl"
            alt="AI"
            class="ai-chat-header-avatar"
          />
          <span v-else class="ai-chat-header-avatar-placeholder material-icons">smart_toy</span>
          <h3>AI 助手</h3>
        </div>
        <div class="ai-chat-header-actions">
          <button type="button" class="btn-icon" :title="maximized ? '还原' : '最大化'" @click="toggleMaximize">
            <span class="material-icons">{{ maximized ? 'fullscreen_exit' : 'fullscreen' }}</span>
          </button>
          <button type="button" class="btn-icon" title="关闭" @click="$emit('close')">
            <span class="material-icons">close</span>
          </button>
        </div>
      </div>
      <div ref="chatListRef" class="ai-chat-messages">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          :class="['ai-chat-msg', msg.role]"
        >
          <template v-if="msg.role === 'user'">
            <div class="ai-chat-msg-content">
              <div v-if="msg.attachments && msg.attachments.length" class="ai-chat-attachments">
                <template v-for="(att, ai) in msg.attachments" :key="ai">
                  <img v-if="att.type === 'image' && (att.preview || att.data)" :src="att.preview || (att.data ? 'data:' + (att.mime || 'image/png') + ';base64,' + att.data : '')" class="ai-chat-attach-preview" alt="附件" />
                  <span v-else-if="att.type === 'file'" class="ai-chat-attach-file">📎 {{ att.name }}</span>
                </template>
              </div>
              <span>{{ msg.content }}</span>
            </div>
          </template>
          <div v-else class="ai-chat-msg-wrap">
            <img
              v-if="aiConfig.avatar_url || defaultAvatarUrl"
              :src="aiConfig.avatar_url || defaultAvatarUrl"
              alt="AI"
              class="ai-chat-msg-avatar"
            />
            <span v-else class="ai-chat-msg-avatar-placeholder material-icons">smart_toy</span>
            <div class="ai-chat-msg-content assistant-content">
              <div v-if="msg.streaming && !msg.content && !msg.thinking" class="ai-chat-typing">
                <span class="ai-chat-typing-dot"></span>
                <span class="ai-chat-typing-dot"></span>
                <span class="ai-chat-typing-dot"></span>
              </div>
              <template v-else>
                <div v-if="msg.thinking && aiConfig.show_thinking" class="ai-chat-thinking">
                  <button type="button" class="ai-chat-thinking-toggle" @click="toggleThinking(idx)">
                    <span class="material-icons">{{ thinkingCollapsed[idx] ? 'expand_more' : 'expand_less' }}</span>
                    <span>思考过程</span>
                  </button>
                  <div v-if="!thinkingCollapsed[idx]" class="ai-chat-thinking-text">{{ msg.thinking }}</div>
                </div>
                <div class="ai-chat-response">{{ msg.content }}{{ msg.streaming ? '▌' : '' }}</div>
              </template>
            </div>
          </div>
        </div>
      </div>
      <div class="ai-chat-input-area">
        <div v-if="attachments.length" class="ai-chat-attach-list">
          <template v-for="(att, idx) in attachments" :key="idx">
            <span v-if="att.type === 'image' && att.preview" class="ai-chat-attach-thumb">
              <img :src="att.preview" alt="预览" />
              <button type="button" class="ai-chat-attach-remove" @click="removeAttachment(idx)">×</button>
            </span>
            <span v-else class="ai-chat-attach-name">📎 {{ att.name || '文件' }} <button type="button" class="ai-chat-attach-remove" @click="removeAttachment(idx)">×</button></span>
          </template>
        </div>
        <div class="ai-chat-input-row">
          <div class="ai-chat-input-actions">
            <button type="button" class="btn-icon" title="上传图片" @click="triggerFileInput('image/*')">
              <span class="material-icons">image</span>
            </button>
            <button type="button" class="btn-icon" title="上传文件" @click="triggerFileInput()">
              <span class="material-icons">attach_file</span>
            </button>
            <button v-if="voiceSupport" type="button" class="btn-icon" :title="isRecording ? '停止' : '语音输入'" :class="{ recording: isRecording }" @mousedown="startVoiceInput" @mouseup="stopVoiceInput" @mouseleave="stopVoiceInput">
              <span class="material-icons">{{ isRecording ? 'stop' : 'mic' }}</span>
            </button>
          </div>
          <textarea
            v-model="inputText"
            placeholder="输入消息，Enter 发送；/clear 清除记录"
            rows="2"
            :disabled="loading"
            @keydown="handleKeydown"
          />
        </div>
        <button
          type="button"
          class="btn btn-primary ai-chat-send"
          :disabled="(!inputText.trim() && !attachments.length) || loading"
          @click="handleSend"
        >
          {{ loading ? '发送中...' : '发送' }}
        </button>
      </div>
      <template v-if="!maximized">
        <div class="ai-chat-resize-handle ai-chat-resize-e" title="拖动调整宽度" @pointerdown="onResizePointerDown($event, 'e')"></div>
        <div class="ai-chat-resize-handle ai-chat-resize-s" title="拖动调整高度" @pointerdown="onResizePointerDown($event, 's')"></div>
        <div class="ai-chat-resize-handle ai-chat-resize-se" title="拖动调整大小" @pointerdown="onResizePointerDown($event, 'se')"></div>
      </template>
    </div>
  `
}
