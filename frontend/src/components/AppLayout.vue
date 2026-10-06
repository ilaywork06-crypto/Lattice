<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { useRouter } from 'vue-router'
import { router } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useLocaleStore } from '@/stores/locale'
import { useNotificationsStore } from '@/stores/notifications'
import BrandLogo from '@/components/BrandLogo.vue'
import GlobalSearch from '@/components/GlobalSearch.vue'
import { ROLE_COLORS, ROLE_LABELS } from '@/constants'
import type { UserRole } from '@/api/types'
import type { LocaleCode } from '@/i18n'

const auth = useAuthStore()
const themeStore = useThemeStore()
const localeStore = useLocaleStore()
const notifications = useNotificationsStore()
const { mdAndUp } = useDisplay()
const routerInstance = useRouter()

const drawer = ref(true)
const rail = ref(false)
const searchOpen = ref(false)

function onGlobalKey(e: KeyboardEvent) {
  // ⌘K / Ctrl-K opens global search from anywhere.
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    searchOpen.value = true
  }
}

onMounted(() => {
  drawer.value = mdAndUp.value
  notifications.startPolling(30000)
  window.addEventListener('keydown', onGlobalKey)
})
onBeforeUnmount(() => {
  notifications.stopPolling()
  window.removeEventListener('keydown', onGlobalKey)
})

interface NavItem {
  title: string
  icon: string
  to: string
  group: string
}

const navGroups = computed(() => {
  const role = auth.role
  const order = ['Overview', 'Assets', 'Operations', 'Admin']
  const groups: Record<string, NavItem[]> = {}
  for (const r of router.getRoutes()) {
    const meta = r.meta
    if (!meta || meta.hideInNav || meta.public) continue
    if (meta.roles && role && !meta.roles.includes(role)) continue
    if (!meta.title || !meta.icon) continue
    const group = meta.group || 'Overview'
    if (!groups[group]) groups[group] = []
    if (groups[group].some((i) => i.to === r.path)) continue
    groups[group].push({ title: meta.title, icon: meta.icon, to: r.path, group })
  }
  return order
    .filter((g) => groups[g]?.length)
    .map((g) => ({ name: g, items: groups[g] }))
})

const roleColor = computed(() => (auth.role ? ROLE_COLORS[auth.role as UserRole] : 'grey'))
const roleLabel = computed(() => (auth.role ? ROLE_LABELS[auth.role as UserRole] : ''))

function setLocale(code: LocaleCode) {
  localeStore.set(code)
}
function goNotifications() {
  routerInstance.push({ name: 'notifications' })
}
function logout() {
  auth.logout(true)
}
function toggleDrawer() {
  if (mdAndUp.value) rail.value = !rail.value
  else drawer.value = !drawer.value
}
</script>

<template>
  <v-navigation-drawer
    v-model="drawer"
    :rail="rail && mdAndUp"
    :permanent="mdAndUp"
    :temporary="!mdAndUp"
    color="nav"
    width="264"
    expand-on-hover
  >
    <div class="d-flex align-center pa-4" style="min-height: 64px">
      <BrandLogo :size="38" />
      <div v-if="!rail" class="ms-3 overflow-hidden">
        <div class="text-h6 font-weight-bold" style="line-height: 1.1">Lattice</div>
        <div class="text-caption text-medium-emphasis">{{ $t('common.tagline') }}</div>
      </div>
    </div>
    <v-divider />

    <template v-for="group in navGroups" :key="group.name">
      <v-list-subheader v-if="!rail" class="text-uppercase text-caption font-weight-bold">
        {{ $t('navGroups.' + group.name) }}
      </v-list-subheader>
      <v-list nav density="comfortable" class="py-0">
        <v-list-item
          v-for="item in group.items"
          :key="item.to"
          :to="item.to"
          :prepend-icon="item.icon"
          :title="$t(item.title)"
          color="primary"
          rounded="lg"
          class="mx-2"
        />
      </v-list>
    </template>
  </v-navigation-drawer>

  <v-app-bar flat color="app-bar" border="b">
    <v-app-bar-nav-icon @click="toggleDrawer" />
    <BrandLogo :size="26" class="ms-1" />
    <v-toolbar-title class="font-weight-bold flex-grow-0 ms-2 me-4">Lattice</v-toolbar-title>

    <!-- Global search activator -->
    <v-btn
      class="search-activator d-none d-sm-flex text-none"
      variant="tonal"
      height="40"
      @click="searchOpen = true"
    >
      <v-icon icon="mdi-magnify" start />
      <span class="text-medium-emphasis">{{ $t('search.open') }}</span>
      <v-chip size="x-small" variant="outlined" class="ms-3">⌘K</v-chip>
    </v-btn>
    <v-btn class="d-sm-none" variant="text" icon="mdi-magnify" @click="searchOpen = true" />

    <v-spacer />

    <!-- Language picker -->
    <v-menu location="bottom end">
      <template #activator="{ props }">
        <v-tooltip :text="$t('appbar.language')" location="bottom">
          <template #activator="{ props: tip }">
            <v-btn v-bind="{ ...props, ...tip }" variant="text" icon="mdi-translate" />
          </template>
        </v-tooltip>
      </template>
      <v-list density="compact" nav min-width="160">
        <v-list-item
          v-for="loc in localeStore.available"
          :key="loc.code"
          :active="localeStore.current === loc.code"
          color="primary"
          @click="setLocale(loc.code)"
        >
          <template #prepend>
            <span class="me-3 text-h6">{{ loc.flag }}</span>
          </template>
          <v-list-item-title>{{ loc.native }}</v-list-item-title>
          <template #append>
            <v-icon v-if="localeStore.current === loc.code" icon="mdi-check" size="18" />
          </template>
        </v-list-item>
      </v-list>
    </v-menu>

    <!-- Theme picker: the default light/dark pair plus pastel palettes -->
    <v-menu location="bottom end" :close-on-content-click="false">
      <template #activator="{ props }">
        <v-tooltip :text="$t('appbar.theme')" location="bottom">
          <template #activator="{ props: tip }">
            <v-btn v-bind="{ ...props, ...tip }" variant="text" icon="mdi-palette-outline" />
          </template>
        </v-tooltip>
      </template>
      <v-card min-width="280" rounded="lg">
        <v-card-title class="text-subtitle-2 pb-0">{{ $t('appbar.theme') }}</v-card-title>
        <v-card-text class="pt-2">
          <div class="theme-grid">
            <button
              v-for="th in themeStore.available"
              :key="th.name"
              type="button"
              class="theme-option"
              :class="{ active: themeStore.current === th.name }"
              :aria-label="$t('themes.' + th.name)"
              @click="themeStore.set(th.name)"
            >
              <span class="theme-swatch" :style="{ background: th.swatch[0] }">
                <span :style="{ background: th.swatch[1] }" />
                <span :style="{ background: th.swatch[2] }" />
              </span>
              <span class="text-caption">{{ $t('themes.' + th.name) }}</span>
              <v-icon
                v-if="themeStore.current === th.name"
                icon="mdi-check-circle"
                size="16"
                color="primary"
                class="theme-check"
              />
            </button>
          </div>
        </v-card-text>
      </v-card>
    </v-menu>

    <!-- Notification bell -->
    <v-tooltip :text="$t('appbar.notifications')" location="bottom">
      <template #activator="{ props }">
        <v-btn v-bind="props" variant="text" icon @click="goNotifications">
          <v-badge
            :content="notifications.unread"
            :model-value="notifications.unread > 0"
            color="error"
            max="99"
          >
            <v-icon icon="mdi-bell-outline" />
          </v-badge>
        </v-btn>
      </template>
    </v-tooltip>

    <!-- User menu -->
    <v-menu location="bottom end" :close-on-content-click="false">
      <template #activator="{ props }">
        <v-btn v-bind="props" variant="text" class="ms-1 px-2">
          <v-avatar color="primary" size="34" class="me-2">
            <span class="text-body-2 font-weight-bold">{{ auth.initials }}</span>
          </v-avatar>
          <div class="d-none d-sm-flex flex-column align-start" style="line-height: 1.1">
            <span class="text-body-2 font-weight-medium">{{ auth.fullName }}</span>
            <span class="text-caption text-medium-emphasis">{{ roleLabel }}</span>
          </div>
          <v-icon icon="mdi-chevron-down" size="18" class="ms-1 d-none d-sm-flex" />
        </v-btn>
      </template>
      <v-card min-width="240" rounded="lg">
        <v-card-text class="d-flex align-center gap-3">
          <v-avatar color="primary" size="42">
            <span class="text-body-1 font-weight-bold">{{ auth.initials }}</span>
          </v-avatar>
          <div>
            <div class="text-subtitle-2">{{ auth.fullName }}</div>
            <v-chip :color="roleColor" size="x-small" variant="flat" class="mt-1">
              {{ roleLabel }}
            </v-chip>
          </div>
        </v-card-text>
        <v-divider />
        <v-list density="compact" nav>
          <v-list-item
            prepend-icon="mdi-bell-outline"
            :title="$t('appbar.notifications')"
            @click="goNotifications"
          />
          <v-list-item
            :prepend-icon="themeStore.isDark ? 'mdi-weather-sunny' : 'mdi-weather-night'"
            :title="themeStore.isDark ? $t('appbar.lightMode') : $t('appbar.darkMode')"
            @click="themeStore.toggle()"
          />
          <v-divider class="my-1" />
          <v-list-item
            prepend-icon="mdi-logout"
            :title="$t('appbar.signOut')"
            base-color="error"
            @click="logout"
          />
        </v-list>
      </v-card>
    </v-menu>
  </v-app-bar>

  <v-main>
    <router-view v-slot="{ Component }">
      <transition name="page-fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </v-main>

  <GlobalSearch v-model="searchOpen" />
</template>

<style scoped>
.theme-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.theme-option {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 10px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: start;
}
.theme-option.active {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 1px rgb(var(--v-theme-primary)) inset;
}
.theme-swatch {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  width: 30px;
  height: 22px;
  padding: 3px;
  border-radius: 6px;
  box-shadow: 0 0 0 1px rgba(128, 128, 128, 0.35) inset;
  flex: none;
}
.theme-swatch span {
  flex: 1;
  height: 10px;
  border-radius: 3px;
}
.theme-check {
  position: absolute;
  top: 4px;
  inset-inline-end: 4px;
}
.search-activator {
  min-width: 220px;
  justify-content: flex-start;
}
</style>
