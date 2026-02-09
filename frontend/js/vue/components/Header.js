export default {
  name: 'Header',
  props: {
    pageTitle: String
  },
  emits: ['toggle-sidebar'],
  template: `
    <header class="top-bar">
      <button class="btn-icon" @click="$emit('toggle-sidebar')">
        <span class="material-icons">menu</span>
      </button>
      <div class="page-title">
        <h2>{{ pageTitle }}</h2>
      </div>
    </header>
  `
}
