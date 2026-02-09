import { ref, onMounted, watch, computed } from 'vue'
import { useStore } from '../store/index.js'

export default {
  name: 'CloudStorageView',
  setup() {
    const { state, actions } = useStore()
    const files = ref([])
    const parent = ref(null)
    const currentUri = ref('cloudreve://my/')
    const breadcrumbs = ref([])
    const loading = ref(false)
    const uploading = ref(false)
    const showNewFolder = ref(false)
    const newFolderName = ref('')
    const fileInput = ref(null)

    const canShow = computed(() => {
      return state.cloudreveEnabled && state.cloudreveBound
    })

    const loadFiles = async () => {
      if (!canShow.value) return
      loading.value = true
      const data = await actions.fetchCloudreveFiles(currentUri.value)
      loading.value = false
      if (data) {
        files.value = data.files || []
        parent.value = data.parent || null
      } else {
        files.value = []
      }
    }

    const navigateTo = (item) => {
      if (item.type === 1) {
        currentUri.value = item.path || (currentUri.value + item.name + '/')
        loadFiles()
      }
    }

    const navigateUp = () => {
      if (parent.value?.path) {
        currentUri.value = parent.value.path
        if (!currentUri.value.endsWith('/')) currentUri.value += '/'
        loadFiles()
      }
    }

    const updateBreadcrumbs = () => {
      const uri = currentUri.value
      if (!uri || uri === 'cloudreve://my/') {
        breadcrumbs.value = [{ name: '我的文件', path: 'cloudreve://my/' }]
      } else {
        const parts = uri.replace('cloudreve://my/', '').split('/').filter(Boolean)
        breadcrumbs.value = [{ name: '我的文件', path: 'cloudreve://my/' }]
        let p = 'cloudreve://my/'
        parts.forEach((name, i) => {
          p += (i > 0 ? '/' : '') + name + '/'
          breadcrumbs.value.push({ name: decodeURIComponent(name), path: p })
        })
      }
    }

    watch(currentUri, updateBreadcrumbs, { immediate: true })

    const formatSize = (bytes) => {
      if (!bytes) return '-'
      if (bytes < 1024) return bytes + ' B'
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
      return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
    }

    const handleDownload = async (item) => {
      if (item.type === 1) return
      const data = await actions.createCloudreveDownloadUrl(item.path)
      if (data?.urls?.[0]?.url) {
        window.open(data.urls[0].url, '_blank')
      } else {
        actions.showToast('获取下载链接失败', 'error')
      }
    }

    const handleDelete = async (item) => {
      if (!confirm(`确定要删除「${item.name}」吗？`)) return
      const ok = await actions.deleteCloudreveFile(item.path)
      if (ok) loadFiles()
    }

    const handleCreateFolder = async (e) => {
      e.preventDefault()
      if (!newFolderName.value.trim()) return
      const ok = await actions.createCloudreveFolder(currentUri.value, newFolderName.value.trim())
      if (ok) {
        newFolderName.value = ''
        showNewFolder.value = false
        loadFiles()
      }
    }

    const handleFileSelect = (e) => {
      const filesToUpload = e.target.files
      if (!filesToUpload?.length) return
      ;(async () => {
        uploading.value = true
        for (let i = 0; i < filesToUpload.length; i++) {
          await actions.uploadCloudreveFile(filesToUpload[i], currentUri.value)
        }
        uploading.value = false
        fileInput.value.value = ''
        loadFiles()
      })()
    }

    const goToBreadcrumb = (path) => {
      currentUri.value = path
      if (!currentUri.value.endsWith('/')) currentUri.value += '/'
      loadFiles()
    }

    onMounted(() => {
      if (canShow.value) loadFiles()
    })

    watch(() => [state.cloudreveEnabled, state.cloudreveBound], () => {
      if (canShow.value) loadFiles()
    })

    return {
      state,
      files,
      parent,
      currentUri,
      breadcrumbs,
      loading,
      uploading,
      showNewFolder,
      newFolderName,
      fileInput,
      canShow,
      loadFiles,
      navigateTo,
      navigateUp,
      formatSize,
      handleDownload,
      handleDelete,
      handleCreateFolder,
      handleFileSelect,
      goToBreadcrumb
    }
  },
  template: `
    <div class="view cloud-storage-view">
      <div v-if="!canShow" class="empty-state">
        <p>网盘功能未开启或未绑定，请先在<button type="button" class="btn-link" @click="$emit('navigate', 'settings')">设置</button>中绑定 Cloudreve。</p>
      </div>
      <template v-else>
        <div class="storage-toolbar">
          <div class="breadcrumbs">
            <span
              v-for="(crumb, i) in breadcrumbs"
              :key="crumb.path"
              class="breadcrumb"
            >
              <button v-if="i > 0" type="button" class="btn-link">/</button>
              <button type="button" class="btn-link" @click="goToBreadcrumb(crumb.path)">
                {{ crumb.name }}
              </button>
            </span>
          </div>
          <div class="storage-actions">
            <button type="button" class="btn btn-outline btn-sm" @click="navigateUp" :disabled="!parent">
              <span class="material-icons">arrow_back</span>
              返回
            </button>
            <button type="button" class="btn btn-outline btn-sm" @click="showNewFolder = true">
              <span class="material-icons">create_new_folder</span>
              新建文件夹
            </button>
            <label class="btn btn-primary btn-sm" :class="{ disabled: uploading }">
              <span class="material-icons">upload_file</span>
              {{ uploading ? '上传中...' : '上传' }}
              <input ref="fileInput" type="file" multiple style="display: none" @change="handleFileSelect">
            </label>
          </div>
        </div>
        <form v-if="showNewFolder" @submit="handleCreateFolder" class="new-folder-form">
          <input v-model="newFolderName" type="text" placeholder="文件夹名称" required>
          <button type="submit" class="btn btn-primary btn-sm">创建</button>
          <button type="button" class="btn btn-outline btn-sm" @click="showNewFolder = false; newFolderName = ''">取消</button>
        </form>
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else class="files-list">
          <div
            v-for="item in files"
            :key="item.id"
            class="file-item"
            @dblclick="navigateTo(item)"
          >
            <span class="file-icon material-icons">{{ item.type === 1 ? 'folder' : 'insert_drive_file' }}</span>
            <span class="file-name">{{ item.name }}</span>
            <span class="file-size">{{ formatSize(item.size) }}</span>
            <div class="file-actions">
              <button v-if="item.type === 0" type="button" class="btn-icon" title="下载" @click.stop="handleDownload(item)">
                <span class="material-icons">download</span>
              </button>
              <button type="button" class="btn-icon" title="删除" @click.stop="handleDelete(item)">
                <span class="material-icons">delete</span>
              </button>
            </div>
          </div>
          <p v-if="files.length === 0 && !loading" class="empty-message">此文件夹为空</p>
        </div>
      </template>
    </div>
  `
}
