import { defineStore } from 'pinia'
import { extractError } from '@/api/client'

type SnackColor = 'success' | 'error' | 'info' | 'warning'

interface SnackState {
  show: boolean
  message: string
  color: SnackColor
  timeout: number
}

export const useUiStore = defineStore('ui', {
  state: (): { snack: SnackState } => ({
    snack: { show: false, message: '', color: 'info', timeout: 4000 },
  }),
  actions: {
    notify(message: string, color: SnackColor = 'info', timeout = 4000) {
      this.snack = { show: true, message, color, timeout }
    },
    success(message: string) {
      this.notify(message, 'success')
    },
    error(err: unknown) {
      this.notify(extractError(err), 'error', 6000)
    },
    info(message: string) {
      this.notify(message, 'info')
    },
    warning(message: string) {
      this.notify(message, 'warning')
    },
  },
})
