import { ref, onMounted } from 'vue'
import { useStore } from '../store/index.js'

export default {
  name: 'Toast',
  setup() {
    const message = ref('')
    const type = ref('info')
    const visible = ref(false)
    let timer = null

    onMounted(() => {
      useStore().actions.setToast((msg, t) => {
        message.value = msg
        type.value = t || 'info'
        visible.value = true
        clearTimeout(timer)
        timer = setTimeout(() => { visible.value = false }, 3000)
      })
    })

    return { message, type, visible }
  },
  template: `
    <div :class="['toast', type, { show: visible }]">{{ message }}</div>
  `
}
