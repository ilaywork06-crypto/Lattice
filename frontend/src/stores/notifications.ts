import { defineStore } from 'pinia'
import { notificationsApi } from '@/api/services'
import type { NotificationCounts, NotificationItem, NotificationStatus } from '@/api/types'

let pollTimer: ReturnType<typeof setInterval> | null = null
const PAGE = 50

export const useNotificationsStore = defineStore('notifications', {
  state: (): {
    items: NotificationItem[]
    unread: number
    counts: NotificationCounts
    status: NotificationStatus
    hasMore: boolean
    loading: boolean
  } => ({
    items: [],
    unread: 0,
    counts: { total: 0, unread: 0, read: 0 },
    status: 'all',
    hasMore: false,
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
    async fetchCounts() {
      try {
        this.counts = await notificationsApi.counts()
        this.unread = this.counts.unread
      } catch {
        // keep last known
      }
    },
    /** Every notification addressed to me — all, unread or read — newest first. */
    async fetchList(next?: NotificationStatus) {
      const status = next ?? this.status
      this.loading = true
      this.status = status
      try {
        const page = await notificationsApi.list({ status, limit: PAGE, offset: 0 })
        this.items = page
        this.hasMore = page.length === PAGE
      } finally {
        this.loading = false
      }
    },
    async fetchMore() {
      if (!this.hasMore || this.loading) return
      this.loading = true
      try {
        const page = await notificationsApi.list({
          status: this.status,
          limit: PAGE,
          offset: this.items.length,
        })
        this.items.push(...page)
        this.hasMore = page.length === PAGE
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
        this.counts.unread = Math.max(0, this.counts.unread - 1)
        this.counts.read += 1
        if (this.status === 'unread') this.items = this.items.filter((i) => i.id !== id)
      }
    },
    async markAllRead() {
      await notificationsApi.markAllRead()
      this.items.forEach((i) => {
        i.read = true
      })
      if (this.status === 'unread') this.items = []
      this.counts = { total: this.counts.total, unread: 0, read: this.counts.total }
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
