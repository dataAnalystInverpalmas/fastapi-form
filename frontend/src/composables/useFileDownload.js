/**
 * useFileDownload — descarga un archivo binario via fetch y lo ofrece al usuario.
 * Reemplaza el comportamiento de <form method="post"> con FileResponse.
 */
import { ref } from 'vue'
import axios from 'axios'

export function useFileDownload() {
  const downloading = ref(false)
  const error = ref(null)

  async function download(url, body, filename) {
    downloading.value = true
    error.value = null
    try {
      const res = await axios.post(url, body, { responseType: 'blob' })
      const blob = new Blob([res.data], { type: res.headers['content-type'] })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      // Intenta obtener el nombre del header Content-Disposition
      const disposition = res.headers['content-disposition'] || ''
      const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      link.download = match ? match[1].replace(/['"]/g, '') : filename || 'descarga.xlsx'
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(link.href)
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Error al descargar el archivo.'
      error.value = msg
      if (window.$toast) window.$toast(msg, 'danger')
    } finally {
      downloading.value = false
    }
  }

  return { downloading, error, download }
}
