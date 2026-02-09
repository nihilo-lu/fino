import { ref, watch } from 'vue'

export default {
  name: 'Modal',
  props: {
    title: String,
    body: String,
    show: Boolean
  },
  emits: ['close'],
  setup(props) {
    const isActive = ref(false)
    watch(() => props.show, (v) => { isActive.value = v })
    return { isActive }
  },
  template: `
    <div :class="['modal', { active: show }]">
      <div class="modal-content">
        <div class="modal-header">
          <h3>{{ title }}</h3>
          <button class="modal-close" @click="$emit('close')">
            <span class="material-icons">close</span>
          </button>
        </div>
        <div class="modal-body" v-html="body"></div>
      </div>
    </div>
  `
}
