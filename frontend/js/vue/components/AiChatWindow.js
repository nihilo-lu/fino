/**
 * AI 聊天窗口 - 支持流式响应与思维链显示
 */
import { ref, watch, nextTick } from 'vue'
import { API_BASE } from '../utils/api.js'

const SYSTEM_PROMPT = `你是一个投资理财助手，帮助用户分析投资组合、理解收益数据、给出合理建议。回答要简洁专业，适当使用数据支撑。`

export default {
  name: 'AiChatWindow',
  props: {
    show: Boolean
  },
  emits: ['close'],
  setup(props, { emit }) {
    const messages = ref([])
    const inputText = ref('')
    const loading = ref(false)
    const chatListRef = ref(null)
    const maximized = ref(false)

    const scrollToBottom = () => {
      nextTick(() => {
        if (chatListRef.value) {
          chatListRef.value.scrollTop = chatListRef.value.scrollHeight
        }
      })
    }

    watch(() => props.show, (v) => {
      if (v && messages.value.length === 0) {
        messages.value = [
          { role: 'assistant', content: '你好！我是投资理财助手，可以帮你分析投资组合、理解收益数据。有什么想聊的吗？' }
        ]
        scrollToBottom()
      }
    })

    const handleSend = async () => {
      const text = inputText.value.trim()
      if (!text || loading.value) return

      if (text.toLowerCase() === '/clear') {
        clearChat()
        inputText.value = ''
        return
      }

      const userMsg = { role: 'user', content: text }
      messages.value.push(userMsg)
      inputText.value = ''
      loading.value = true

      const assistantMsg = {
        role: 'assistant',
        content: '',
        thinking: '',
        streaming: true
      }
      messages.value.push(assistantMsg)
      scrollToBottom()

      const chatMessages = messages.value.slice(0, -1).map(m => ({
        role: m.role,
        content: m.content
      }))
      chatMessages.unshift({ role: 'system', content: SYSTEM_PROMPT })
      chatMessages.push({ role: 'user', content: text })

      try {
        const response = await fetch(`${API_BASE}/ai/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ messages: chatMessages, stream: true })
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
      scrollToBottom()
    }

    return {
      messages,
      inputText,
      loading,
      chatListRef,
      maximized,
      handleSend,
      handleKeydown,
      clearChat,
      toggleMaximize,
      scrollToBottom
    }
  },
  template: `
    <div v-if="show" :class="['ai-chat-window', { maximized }]">
      <div class="ai-chat-header">
        <h3>🤖 AI 助手</h3>
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
          <div v-if="msg.role === 'user'" class="ai-chat-msg-content">
            {{ msg.content }}
          </div>
          <div v-else class="ai-chat-msg-content">
            <div v-if="msg.thinking" class="ai-chat-thinking">
              <div class="ai-chat-thinking-label">💭 思考过程</div>
              <div class="ai-chat-thinking-text">{{ msg.thinking }}</div>
            </div>
            <div class="ai-chat-response">{{ msg.content }}{{ msg.streaming ? '▌' : '' }}</div>
          </div>
        </div>
      </div>
      <div class="ai-chat-input-area">
        <textarea
          v-model="inputText"
          placeholder="输入消息，Enter 发送；/clear 清除记录"
          rows="2"
          :disabled="loading"
          @keydown="handleKeydown"
        />
        <button
          type="button"
          class="btn btn-primary ai-chat-send"
          :disabled="!inputText.trim() || loading"
          @click="handleSend"
        >
          {{ loading ? '发送中...' : '发送' }}
        </button>
      </div>
    </div>
  `
}
