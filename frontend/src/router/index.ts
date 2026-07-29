import {
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
} from 'vue-router'
import type { UserRole } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { i18n } from '@/i18n'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    icon?: string
    public?: boolean
    roles?: UserRole[] // if set, restrict to these roles
    hideInNav?: boolean
    group?: string
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/LoginPage.vue'),
    meta: { title: 'nav.signIn', public: true, hideInNav: true },
  },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/pages/DashboardPage.vue'),
    meta: { title: 'nav.dashboard', icon: 'mdi-view-dashboard-outline', group: 'Overview' },
  },
  // Sidebar order (§3): Cards → Assemblies → Setups.
  {
    path: '/cards',
    name: 'cards',
    component: () => import('@/pages/CardsPage.vue'),
    meta: { title: 'nav.cards', icon: 'mdi-memory', group: 'Assets' },
  },
  {
    path: '/assemblies',
    name: 'assemblies',
    component: () => import('@/pages/AssembliesPage.vue'),
    meta: { title: 'nav.assemblies', icon: 'mdi-cpu-64-bit', group: 'Assets' },
  },
  {
    path: '/setups',
    name: 'setups',
    component: () => import('@/pages/SetupsPage.vue'),
    meta: { title: 'nav.setups', icon: 'mdi-server', group: 'Assets' },
  },
  {
    path: '/items/:id',
    name: 'item-detail',
    component: () => import('@/pages/ItemDetailPage.vue'),
    meta: { title: 'nav.item', hideInNav: true },
    props: true,
  },
  {
    path: '/inventory',
    name: 'inventory',
    component: () => import('@/pages/InventoryPage.vue'),
    meta: { title: 'nav.inventory', icon: 'mdi-warehouse', group: 'Assets' },
  },
  {
    path: '/graph',
    name: 'graph',
    component: () => import('@/pages/GraphPage.vue'),
    meta: { title: 'nav.graph', icon: 'mdi-graph-outline', group: 'Assets' },
  },
  {
    path: '/locations',
    name: 'locations',
    component: () => import('@/pages/LocationsPage.vue'),
    meta: { title: 'nav.locations', icon: 'mdi-map-marker-radius', group: 'Assets' },
  },
  {
    path: '/templates',
    name: 'templates',
    component: () => import('@/pages/TemplatesPage.vue'),
    meta: {
      title: 'nav.templates',
      icon: 'mdi-content-duplicate',
      group: 'Assets',
      roles: ['editor', 'manager'],
    },
  },
  {
    path: '/change-requests',
    name: 'change-requests',
    component: () => import('@/pages/ChangeRequestsPage.vue'),
    meta: { title: 'nav.changeRequests', icon: 'mdi-file-swap-outline', group: 'Operations' },
  },
  {
    // Every change-request notification — in-app *and* the email — links to
    // `/change-requests/{id}` (see services/change_requests.py). Without this
    // route those links fell through to the catch-all and showed a 404.
    path: '/change-requests/:id',
    name: 'change-request-detail',
    component: () => import('@/pages/ChangeRequestsPage.vue'),
    meta: { title: 'nav.changeRequests', hideInNav: true },
  },
  {
    path: '/notifications',
    name: 'notifications',
    component: () => import('@/pages/NotificationsPage.vue'),
    meta: { title: 'nav.notifications', icon: 'mdi-bell-outline', group: 'Operations' },
  },
  {
    path: '/audit',
    name: 'audit',
    component: () => import('@/pages/AuditPage.vue'),
    meta: { title: 'nav.audit', icon: 'mdi-history', group: 'Operations' },
  },
  {
    path: '/import-export',
    name: 'import-export',
    component: () => import('@/pages/ImportExportPage.vue'),
    meta: {
      title: 'nav.importExport',
      icon: 'mdi-swap-vertical-bold',
      group: 'Operations',
      roles: ['editor', 'manager'],
    },
  },
  {
    path: '/catalog',
    name: 'catalog',
    component: () => import('@/pages/CatalogPage.vue'),
    meta: {
      title: 'nav.catalog',
      icon: 'mdi-tag-multiple-outline',
      group: 'Admin',
      roles: ['manager'],
    },
  },
  {
    path: '/users',
    name: 'users',
    component: () => import('@/pages/UsersPage.vue'),
    meta: {
      title: 'nav.users',
      icon: 'mdi-account-group-outline',
      group: 'Admin',
      roles: ['manager'],
    },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/pages/NotFoundPage.vue'),
    meta: { title: 'nav.notFound', hideInNav: true },
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    if (to.name === 'login' && auth.isAuthenticated) {
      return { name: 'dashboard' }
    }
    return true
  }

  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.roles && auth.role && !to.meta.roles.includes(auth.role)) {
    return { name: 'dashboard' }
  }

  return true
})

router.afterEach((to) => {
  const base = 'Lattice'
  const title = to.meta.title ? i18n.global.t(to.meta.title) : ''
  document.title = title ? `${title} · ${base}` : base
})
