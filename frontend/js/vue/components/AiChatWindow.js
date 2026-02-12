/**
 * AI 聊天窗口 - 支持流式响应、思维链、图片/文件/语音、AI 头像、自由拖动、Markdown 渲染
 */
import { ref, reactive, watch, nextTick, onMounted, onUnmounted, computed } from 'vue'
import { API_BASE } from '../utils/api.js'
import { useStore } from '../store/index.js'

function parseMarkdown(text) {
  try {
    const m = window.__marked__
    if (!m) return text
    const parse = m.parse || m
    const out = typeof parse === 'function' ? parse(text) : text
    return typeof out === 'string' ? out : text
  } catch {
    return text
  }
}

const WINDOW_POS_STORAGE_KEY = 'ai_chat_window_pos'
const DEFAULT_WIDTH = 400

// 默认 AI 头像（简约机器人 SVG）
const DEFAULT_AI_AVATAR = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%237c7363"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7.5 11.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5S9.83 13 9 13s-1.5-.67-1.5-1.5zM16 17H8v-2h8v2zm-.5-4c-.83 0-1.5-.67-1.5-1.5S14.67 10 15.5 10s1.5.67 1.5 1.5S16.33 13 15.5 13z"/></svg>')
const DEFAULT_HEIGHT = 520
const MIN_WIDTH = 280
const MIN_HEIGHT = 300
const MAX_WIDTH_RATIO = 0.9
const MAX_HEIGHT_RATIO = 0.85

// 仅作未拉取到配置时的兜底，正常从插件配置（api/ai/config）的 system_prompt 读取
const DEFAULT_SYSTEM_PROMPT = `你是一个投资理财助手，帮助用户分析投资组合、理解收益数据、给出合理建议。回答要简洁专业，适当使用数据支撑。
当用户询问账本、账户、交易、持仓、收益等数据且已开启「调用数据」时，你可使用 execute_python 工具在沙箱中执行 Python 调用本应用 API。代码中可用 requests、json、API_BASE、CURRENT_USERNAME（当前登录用户名，调用需 username 的接口时必传，如 /api/ledgers?username= 等）。请将需要返回的结果赋给变量 result。`

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
    show: Boolean,
    standalone: { type: Boolean, default: false },
    /** 独立页多会话时传入当前会话 id，使用 sessions API 读写；不传则用旧版 history API */
    sessionId: { type: Number, default: null }
  },
  emits: ['close', 'session-saved'],
  setup(props, { emit }) {
    const { state, actions } = useStore()
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
    const aiConfig = ref({ avatar_url: '', show_thinking: true, system_prompt: '' })
    const useToolsEnabled = ref(false)
    const isRecording = ref(false)
    const voiceSupport = ref(false)
    const thinkingElapsed = ref(0) // 思考中读秒
    const ttsEnabled = ref(false) // 语音播放 AI 回复
    const showSettingsModal = ref(false)
    const settingsForm = ref({ avatar_url: '', show_thinking: true, system_prompt: '' })
    const settingsSaving = ref(false)
    /** 小窗模式下的当前会话 id，与 /chat 页共用同一套会话列表 */
    const floatingSessionId = ref(null)
    let thinkingTimerId = null
    let recognition = null
    let abortController = null
    let ttsUtterance = null

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
        if (res.ok) {
          const payload = data?.data ?? data
          if (payload && typeof payload === 'object') {
            aiConfig.value = { ...aiConfig.value, ...payload }
          }
        }
      } catch (_) {}
    }

    /** 独立页：按会话 id 加载（多会话页） */
    const loadSession = async (sid) => {
      if (sid == null) return
      messages.value = [] // 先清空，避免切换时短暂显示上一会话
      try {
        const res = await fetch(`${API_BASE}/ai/chat/sessions/${sid}`, { credentials: 'include' })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) return
        const list = data?.data?.messages ?? data?.messages
        if (Array.isArray(list) && list.length > 0) {
          messages.value = list.map((m) => ({
            role: m.role || 'assistant',
            content: m.content || '',
            thinking: m.thinking || ''
          }))
        } else {
          messages.value = [{ role: 'assistant', content: '你好！我是投资理财助手，可以帮你分析投资组合、理解收益数据。有什么想聊的吗？' }]
        }
      } catch (_) {
        messages.value = [{ role: 'assistant', content: '加载失败，请重试。' }]
      }
    }

    /** 当前生效的会话 id：独立页用 props.sessionId，小窗用 floatingSessionId */
    const getEffectiveSessionId = () => {
      if (props.standalone && props.sessionId != null) return props.sessionId
      if (!props.standalone && floatingSessionId.value != null) return floatingSessionId.value
      return null
    }

    /** 小窗打开时：拉取会话列表，使用最近一条或新建一条，并加载其消息（与 /chat 页统一） */
    const initFloatingSession = async () => {
      try {
        const res = await fetch(`${API_BASE}/ai/chat/sessions`, { credentials: 'include' })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) return
        const list = data?.data ?? data
        const arr = Array.isArray(list) ? list : []
        if (arr.length > 0) {
          floatingSessionId.value = arr[0].id
          await loadSession(arr[0].id)
        } else {
          const createRes = await fetch(`${API_BASE}/ai/chat/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ title: '新对话' })
          })
          const createData = await createRes.json().catch(() => ({}))
          if (!createRes.ok || !createData?.data?.id) {
            messages.value = [{ role: 'assistant', content: '你好！我是投资理财助手，可以帮你分析投资组合、理解收益数据。有什么想聊的吗？' }]
            return
          }
          floatingSessionId.value = createData.data.id
          messages.value = [{ role: 'assistant', content: '你好！我是投资理财助手，可以帮你分析投资组合、理解收益数据。有什么想聊的吗？' }]
        }
      } catch (_) {
        messages.value = [{ role: 'assistant', content: '你好！我是投资理财助手，可以帮你分析投资组合、理解收益数据。有什么想聊的吗？' }]
      }
    }

    /** 独立页：从数据库恢复历史记录（单会话旧接口，与账本同库） */
    const loadChatHistory = async () => {
      if (!props.standalone) return
      if (props.sessionId != null) {
        await loadSession(props.sessionId)
        return
      }
      try {
        const res = await fetch(`${API_BASE}/ai/chat/history`, { credentials: 'include' })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) return
        const list = data?.data?.messages ?? data?.messages
        if (Array.isArray(list) && list.length > 0) {
          messages.value = list.map((m) => ({
            role: m.role || 'assistant',
            content: m.content || '',
            thinking: m.thinking || ''
          }))
        }
      } catch (_) {}
    }

    /** 独立页：按会话 id 保存（多会话页） */
    const saveSession = async (sid) => {
      if (sid == null) return
      try {
        const list = messages.value
          .filter((m) => !m.streaming)
          .map((m) => ({
            role: m.role,
            content: typeof m.content === 'string' ? m.content : '',
            thinking: m.thinking || ''
          }))
        await fetch(`${API_BASE}/ai/chat/sessions/${sid}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ messages: list })
        })
        emit('session-saved')
      } catch (_) {}
    }

    /** 将当前对话保存到数据库（小窗与独立页统一用 sessions；无 session 时独立页用旧 history 接口） */
    const saveChatHistory = async () => {
      const sid = getEffectiveSessionId()
      if (sid != null) {
        const list = messages.value.filter((m) => !m.streaming)
        if (list.length === 0) return
        await saveSession(sid)
        return
      }
      if (!props.standalone) return
      try {
        const list = messages.value
          .filter((m) => !m.streaming)
          .map((m) => ({
            role: m.role,
            content: typeof m.content === 'string' ? m.content : '',
            thinking: m.thinking || ''
          }))
        if (list.length === 0) return
        await fetch(`${API_BASE}/ai/chat/history`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ messages: list })
        })
      } catch (_) {}
    }

    const openChatSettings = () => {
      settingsForm.value = {
        avatar_url: aiConfig.value.avatar_url || '',
        show_thinking: !!aiConfig.value.show_thinking,
        system_prompt: aiConfig.value.system_prompt || ''
      }
      showSettingsModal.value = true
    }

    const closeChatSettings = () => {
      showSettingsModal.value = false
    }

    const saveChatSettings = async () => {
      settingsSaving.value = true
      const ok = await actions.saveAiConfig(settingsForm.value)
      settingsSaving.value = false
      if (ok) {
        aiConfig.value = { ...aiConfig.value, ...settingsForm.value }
        closeChatSettings()
        actions.showToast('设置已保存', 'success')
      } else {
        actions.showToast('保存失败', 'error')
      }
    }

    const toggleThinking = (idx) => {
      thinkingCollapsed.value = { ...thinkingCollapsed.value, [idx]: !thinkingCollapsed.value[idx] }
    }
    const executionsCollapsed = ref({})
    const toggleExecutions = (idx) => {
      executionsCollapsed.value = { ...executionsCollapsed.value, [idx]: !executionsCollapsed.value[idx] }
    }
    const formatResultPreview = (r) => {
      if (r === null || r === undefined) return '—'
      if (typeof r === 'string') return r.length > 500 ? r.slice(0, 500) + '…' : r
      try {
        const s = JSON.stringify(r)
        return s.length > 500 ? s.slice(0, 500) + '…' : s
      } catch {
        return String(r)
      }
    }

    /** 将回复内容渲染为 Markdown HTML（marked 默认转义 HTML，安全） */
    const renderReplyHtml = (msg) => {
      const raw = msg.content || ''
      const cursor = msg.streaming ? '▌' : ''
      const html = parseMarkdown(raw)
      return html + cursor
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
      if (props.standalone || maximized.value) return {}
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
        if (props.standalone) {
          loadChatHistory().then(() => {
            if (messages.value.length === 0 && props.sessionId == null) {
              messages.value = [
                { role: 'assistant', content: '你好！我是投资理财助手，可以帮你分析投资组合、理解收益数据。有什么想聊的吗？' }
              ]
            }
            fetchAiConfig()
            scrollToBottom()
          })
          return
        }
        // 小窗：与 /chat 页共用会话，拉取最近一条或新建并加载
        initFloatingSession().then(() => {
          fetchAiConfig()
          scrollToBottom()
        })
      }
    })

    watch(() => props.sessionId, (sid) => {
      if (props.standalone && props.show && sid != null) {
        loadSession(sid).then(() => {
          fetchAiConfig()
          scrollToBottom()
        })
      }
    }, { immediate: true })

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
      if (typeof window.marked !== 'undefined') {
        window.__marked__ = window.marked
        if (typeof window.marked.setOptions === 'function') {
          window.marked.setOptions({ gfm: true, breaks: true })
        }
      }
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
      thinkingElapsed.value = 0
      if (thinkingTimerId) clearInterval(thinkingTimerId)
      const thinkingStart = Date.now()
      thinkingTimerId = setInterval(() => {
        thinkingElapsed.value = Math.floor((Date.now() - thinkingStart) / 1000)
      }, 1000)

      const chatMessages = messages.value.slice(0, -1).map(m => ({
        role: m.role,
        content: typeof m.content === 'string' ? m.content : (m.content && m.content.text) || ''
      }))
      const systemPrompt = (aiConfig.value.system_prompt || '').trim() || DEFAULT_SYSTEM_PROMPT
      chatMessages.unshift({ role: 'system', content: systemPrompt })
      chatMessages.push({ role: 'user', content: userContent })

      const useTools = useToolsEnabled.value
      abortController = new AbortController()
      try {
        const response = await fetch(`${API_BASE}/ai/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          signal: abortController.signal,
          body: JSON.stringify({
            messages: chatMessages,
            stream: !useTools,
            use_tools: useTools,
            attachments: currentAttachments
          })
        })

        if (!response.ok) {
          const err = await response.json().catch(() => ({}))
          throw new Error(err.error || '请求失败')
        }

        if (useTools) {
          const data = await response.json().catch(() => ({}))
          // 后端 api_success(data=dict) 会合并到顶层
          assistantMsg.content = data.content ?? data.data?.content ?? ''
          assistantMsg.thinking = data.thinking ?? data.data?.thinking ?? ''
          assistantMsg.executions = data.executions ?? data.data?.executions ?? []
        } else {
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
        }
      } catch (e) {
        if (e?.name === 'AbortError') {
          assistantMsg.content = '已停止生成'
        } else {
          assistantMsg.content = '抱歉，发生错误：' + (e.message || '请求失败')
        }
      } finally {
        if (thinkingTimerId) {
          clearInterval(thinkingTimerId)
          thinkingTimerId = null
        }
        thinkingElapsed.value = 0
        assistantMsg.streaming = false
        loading.value = false
        scrollToBottom()
        if (props.standalone || getEffectiveSessionId() != null) saveChatHistory()
        if (ttsEnabled.value && assistantMsg.content) {
          speakText(assistantMsg.content)
        }
      }
    }

    const getChatUrl = () => new URL('/chat', window.location.href).href

    const openInNewWindow = () => {
      window.open(getChatUrl(), '_blank')
    }

    const toggleTts = () => {
      ttsEnabled.value = !ttsEnabled.value
      if (ttsEnabled.value && typeof window.speechSynthesis !== 'undefined') {
        try {
          window.speechSynthesis.cancel()
        } catch (_) {}
      }
    }

    const speakText = (text) => {
      if (!text || typeof window.speechSynthesis === 'undefined') return
      try {
        window.speechSynthesis.cancel()
        const u = new SpeechSynthesisUtterance((text || '').trim().slice(0, 4000))
        u.lang = 'zh-CN'
        u.rate = 1
        window.speechSynthesis.speak(u)
      } catch (_) {}
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
      if (props.standalone || getEffectiveSessionId() != null) saveChatHistory()
      scrollToBottom()
    }

    const copyMessage = async (idx) => {
      const msg = messages.value[idx]
      if (!msg) return
      const text = typeof msg.content === 'string' ? msg.content : (msg.content && msg.content.text) || ''
      if (!text) return
      try {
        await navigator.clipboard.writeText(text)
        actions.showToast('已复制', 'success')
      } catch {
        actions.showToast('复制失败', 'error')
      }
    }

    const toggleTools = () => {
      useToolsEnabled.value = !useToolsEnabled.value
    }

    const stopRequest = () => {
      if (abortController) {
        abortController.abort()
        abortController = null
      }
    }

    const ensureWelcome = () => {
      if (messages.value.length === 0) {
        messages.value = [{ role: 'assistant', content: '对话已清空，有什么想聊的吗？' }]
      }
    }

    /** 撤回：仅对最后一条用户消息有效，移除该条及其后一条助手回复 */
    const recallMessage = (idx) => {
      const list = messages.value
      if (idx < 0 || idx >= list.length || list[idx].role !== 'user') return
      const lastUserIdx = [...list].map((m, i) => (m.role === 'user' ? i : -1)).filter(i => i >= 0).pop()
      if (lastUserIdx !== idx) return
      const next = list[idx + 1]
      if (next && next.role === 'assistant') {
        messages.value = list.slice(0, idx).concat(list.slice(idx + 2))
      } else {
        messages.value = list.slice(0, idx).concat(list.slice(idx + 1))
      }
      ensureWelcome()
      if (props.standalone || getEffectiveSessionId() != null) saveChatHistory()
      scrollToBottom()
      actions.showToast('已撤回', 'success')
    }

    /** 删除单条消息 */
    const deleteMessage = (idx) => {
      const list = messages.value
      if (idx < 0 || idx >= list.length) return
      messages.value = list.slice(0, idx).concat(list.slice(idx + 1))
      ensureWelcome()
      if (props.standalone || getEffectiveSessionId() != null) saveChatHistory()
      scrollToBottom()
      actions.showToast('已删除', 'success')
    }

    const isLastUserMessage = (idx) => {
      const list = messages.value
      if (list[idx]?.role !== 'user') return false
      const lastUserIdx = [...list].map((m, i) => (m.role === 'user' ? i : -1)).filter(i => i >= 0).pop()
      return lastUserIdx === idx
    }

    const toggleMaximize = () => {
      maximized.value = !maximized.value
      if (!maximized.value && winX.value == null) loadWindowPosition()
      scrollToBottom()
    }

    const defaultAvatarUrl = DEFAULT_AI_AVATAR
    const userAvatar = computed(() => state.user?.avatar)

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
      toggleExecutions,
      formatResultPreview,
      executionsCollapsed,
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
      userAvatar,
      useToolsEnabled,
      windowStyle,
      isDragging,
      onHeaderPointerDown,
      onResizePointerDown,
      resizeDir,
      thinkingElapsed,
      renderReplyHtml,
      copyMessage,
      toggleTools,
      stopRequest,
      recallMessage,
      deleteMessage,
      isLastUserMessage,
      getChatUrl,
      openInNewWindow,
      toggleTts,
      ttsEnabled,
      showSettingsModal,
      settingsForm,
      settingsSaving,
      openChatSettings,
      closeChatSettings,
      saveChatSettings
    }
  },
  template: `
    <div v-if="show" :class="['ai-chat-window', { maximized, dragging: isDragging, resizing: resizeDir, standalone }]" :style="windowStyle">
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
          <button type="button" class="btn-icon" :title="ttsEnabled ? '关闭语音播放' : '开启语音播放'" :class="{ active: ttsEnabled }" @click="toggleTts">
            <span class="material-icons">{{ ttsEnabled ? 'volume_up' : 'volume_off' }}</span>
          </button>
          <button v-if="standalone" type="button" class="btn-icon" title="设置" @click="openChatSettings">
            <span class="material-icons">settings</span>
          </button>
          <button v-if="!standalone" type="button" class="btn-icon" title="在新窗口打开" @click="openInNewWindow">
            <span class="material-icons">open_in_new</span>
          </button>
          <button v-if="!standalone" type="button" class="btn-icon" :title="maximized ? '还原' : '最大化'" @click="toggleMaximize">
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
            <div class="ai-chat-msg-wrap">
              <div class="ai-chat-msg-body">
                <div class="ai-chat-msg-bubble">
                  <div class="ai-chat-msg-content">
                    <div v-if="msg.attachments && msg.attachments.length" class="ai-chat-attachments">
                      <template v-for="(att, ai) in msg.attachments" :key="ai">
                        <img v-if="att.type === 'image' && (att.preview || att.data)" :src="att.preview || (att.data ? 'data:' + (att.mime || 'image/png') + ';base64,' + att.data : '')" class="ai-chat-attach-preview" alt="附件" />
                        <span v-else-if="att.type === 'file'" class="ai-chat-attach-file">📎 {{ att.name }}</span>
                      </template>
                    </div>
                    <span>{{ msg.content }}</span>
                  </div>
                </div>
                <div class="ai-chat-msg-actions">
                  <button type="button" class="ai-chat-msg-copy" title="复制" @click="copyMessage(idx)">
                    <span class="material-icons">content_copy</span>
                  </button>
                  <button v-if="isLastUserMessage(idx)" type="button" class="ai-chat-msg-action" title="撤回" @click="recallMessage(idx)">
                    <span class="material-icons">undo</span>
                  </button>
                  <button type="button" class="ai-chat-msg-action" title="删除" @click="deleteMessage(idx)">
                    <span class="material-icons">delete_outline</span>
                  </button>
                </div>
              </div>
              <img v-if="userAvatar" :src="userAvatar" alt="我" class="ai-chat-msg-avatar" />
              <span v-else class="ai-chat-msg-avatar-placeholder material-icons">person</span>
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
            <div class="ai-chat-msg-body">
              <div class="ai-chat-msg-bubble assistant-content">
                <div v-if="msg.streaming && !msg.content && !msg.thinking" class="ai-chat-typing">
                  <div class="ai-chat-typing-top">
                    <span class="ai-chat-typing-label">Thinking</span>
                    <span class="ai-chat-typing-timer">{{ thinkingElapsed }}s</span>
                  </div>
                  <div class="ai-chat-typing-bottom">
                    <div class="ai-chat-typing-dots">
                      <span class="ai-chat-typing-dot"></span>
                      <span class="ai-chat-typing-dot"></span>
                      <span class="ai-chat-typing-dot"></span>
                    </div>
                  </div>
                </div>
                <template v-else>
                  <div v-if="msg.thinking && aiConfig.show_thinking" class="ai-chat-thinking">
                    <button type="button" class="ai-chat-thinking-toggle" @click="toggleThinking(idx)">
                      <span class="material-icons">{{ thinkingCollapsed[idx] ? 'expand_more' : 'expand_less' }}</span>
                      <span>思考过程</span>
                    </button>
                    <div v-if="!thinkingCollapsed[idx]" class="ai-chat-thinking-text">{{ msg.thinking }}</div>
                  </div>
                  <div v-if="msg.executions && msg.executions.length" class="ai-chat-executions">
                    <button type="button" class="ai-chat-executions-toggle" @click="toggleExecutions(idx)">
                      <span class="material-icons">{{ executionsCollapsed[idx] ? 'expand_more' : 'expand_less' }}</span>
                      <span>已执行代码（{{ msg.executions.length }} 次）</span>
                    </button>
                    <div v-if="!executionsCollapsed[idx]" class="ai-chat-exec-list">
                      <div v-for="(ex, ei) in msg.executions" :key="ei" class="ai-chat-exec-item">
                        <div class="ai-chat-exec-label">Python #{{ ei + 1 }}</div>
                        <pre class="ai-chat-exec-code">{{ ex.code || '(无代码)' }}</pre>
                        <div v-if="ex.ok" class="ai-chat-exec-result">
                          <span class="ai-chat-exec-result-label">结果</span>
                          <pre class="ai-chat-exec-result-body">{{ formatResultPreview(ex.result) }}</pre>
                          <pre v-if="ex.stdout" class="ai-chat-exec-stdout">{{ ex.stdout }}</pre>
                        </div>
                        <div v-else class="ai-chat-exec-error">
                          <span class="material-icons">error_outline</span>
                          {{ ex.error || '执行失败' }}
                          <pre v-if="ex.stdout" class="ai-chat-exec-stdout">{{ ex.stdout }}</pre>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="ai-chat-msg-content-inner">
                    <div class="ai-chat-response markdown-body" v-html="renderReplyHtml(msg)"></div>
                  </div>
                </template>
              </div>
              <div class="ai-chat-msg-actions">
                <button type="button" class="ai-chat-msg-copy" title="复制" @click="copyMessage(idx)">
                  <span class="material-icons">content_copy</span>
                </button>
                <button type="button" class="ai-chat-msg-action" title="删除" @click="deleteMessage(idx)">
                  <span class="material-icons">delete_outline</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="ai-chat-input-area">
        <div class="ai-chat-input-wrap">
          <textarea
            v-model="inputText"
            placeholder="输入消息，Enter 发送"
            rows="2"
            :disabled="loading"
            @keydown="handleKeydown"
            class="ai-chat-input"
          />
          <button v-if="voiceSupport" type="button" class="ai-chat-input-mic" :class="{ recording: isRecording }" :title="isRecording ? '停止' : '语音输入'" @mousedown="startVoiceInput" @mouseup="stopVoiceInput" @mouseleave="stopVoiceInput">
            <span class="material-icons">{{ isRecording ? 'stop' : 'mic' }}</span>
          </button>
        </div>
        <div v-if="attachments.length" class="ai-chat-attach-list">
          <template v-for="(att, idx) in attachments" :key="idx">
            <span v-if="att.type === 'image' && att.preview" class="ai-chat-attach-thumb">
              <img :src="att.preview" alt="预览" />
              <button type="button" class="ai-chat-attach-remove" @click="removeAttachment(idx)">×</button>
            </span>
            <span v-else class="ai-chat-attach-name">📎 {{ att.name || '文件' }} <button type="button" class="ai-chat-attach-remove" @click="removeAttachment(idx)">×</button></span>
          </template>
        </div>
        <div class="ai-chat-input-actions">
          <button type="button" class="ai-chat-action-btn" title="清除聊天记录" @click="clearChat">
            <span class="material-icons">delete_sweep</span>
          </button>
          <button type="button" class="ai-chat-action-btn" :class="{ active: useToolsEnabled }" title="允许助手调用数据（沙箱执行 Python）" @click="toggleTools">
            <span class="material-icons">code</span>
          </button>
          <button type="button" class="ai-chat-action-btn" title="上传图片" @click="triggerFileInput('image/*')">
            <span class="material-icons">image</span>
          </button>
          <button type="button" class="ai-chat-action-btn" title="上传文件" @click="triggerFileInput()">
            <span class="material-icons">attach_file</span>
          </button>
          <button
            v-if="loading"
            type="button"
            class="ai-chat-action-btn ai-chat-stop-btn"
            title="停止生成"
            @click="stopRequest"
          >
            <span class="material-icons">stop_circle</span>
          </button>
          <button
            type="button"
            class="ai-chat-action-btn ai-chat-send-btn"
            :disabled="(!inputText.trim() && !attachments.length) || loading"
            :title="loading ? '发送中' : '发送'"
            @click="handleSend"
          >
            <span class="material-icons">send</span>
          </button>
        </div>
      </div>
      <template v-if="!maximized">
        <div class="ai-chat-resize-handle ai-chat-resize-e" title="拖动调整宽度" @pointerdown="onResizePointerDown($event, 'e')"></div>
        <div class="ai-chat-resize-handle ai-chat-resize-s" title="拖动调整高度" @pointerdown="onResizePointerDown($event, 's')"></div>
        <div class="ai-chat-resize-handle ai-chat-resize-se" title="拖动调整大小" @pointerdown="onResizePointerDown($event, 'se')"></div>
      </template>

      <div v-if="showSettingsModal" class="modal active" @click.self="closeChatSettings">
        <div class="modal-content ai-chat-settings-modal">
          <div class="modal-header">
            <h3>聊天设置</h3>
            <button type="button" class="modal-close" @click="closeChatSettings">
              <span class="material-icons">close</span>
            </button>
          </div>
          <div class="modal-body">
            <form @submit.prevent="saveChatSettings">
              <div class="form-group">
                <label>AI 头像 URL</label>
                <input v-model="settingsForm.avatar_url" type="url" placeholder="https://...（留空使用默认图标）">
              </div>
              <div class="form-group checkbox-group">
                <label class="checkbox-label">
                  <input v-model="settingsForm.show_thinking" type="checkbox">
                  <span>显示思考过程</span>
                </label>
              </div>
              <div class="form-group">
                <label>系统提示词</label>
                <textarea v-model="settingsForm.system_prompt" rows="5" placeholder="设定 AI 助手的角色与行为，留空使用默认提示词。"></textarea>
              </div>
              <div class="form-actions">
                <button type="button" class="btn btn-outline" @click="closeChatSettings">取消</button>
                <button type="submit" class="btn btn-primary" :disabled="settingsSaving">
                  {{ settingsSaving ? '保存中...' : '保存' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  `
}
