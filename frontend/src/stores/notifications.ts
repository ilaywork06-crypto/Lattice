import { defineStore } from 'pinia'
import { notificationsApi } from '@/api/services'
import type { NotificationItem } from '@/api/types'

let pollTimer: ReturnType<typeof setInterval> | null = null

export const useNotificationsStore = defineStore('notifications', {
  state: (): { items: NotificationItem[]; unread: number; loading: boolean } => ({
    items: [],
    unread: 0,
    loading: false,
  }),
  actions: {
    async fetchUnreadCount() {
      try {
        this.unread = await notificationsApi.unreadCount()
      } catch {
        // Notification service may be offline; keep last known count silently.
      }
    },
    async fetchList(unreadOnly = false) {
      this.loading = true
      try {
        this.items = await notificationsApi.list({ unread_only: unreadOnly, limit: 50 })
      } finally {
        this.loading = false
      }
    },
    async markRead(id: number) {
      await notificationsApi.markRead(id)
      const n = this.items.find((i) => i.id === id)
      if (n && !n.read) {
        n.read = true
        this.unread = Math.max(0, this.unread - 1)
      }
    },
    async markAllRead() {
      await notificationsApi.markAllRead()
      this.items.forEach((i) => {
        i.read = true
      })
      this.unread = 0
    },
    startPolling(intervalMs = 30000) {
      this.stopPolling()
      void this.fetchUnreadCount()
      pollTimer = setInterval(() => {
        void this.fetchUnreadCount()
      }, intervalMs)
    },
    stopPolling() {
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    },
  },
})
