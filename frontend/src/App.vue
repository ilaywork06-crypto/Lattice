<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/AppLayout.vue'
import GlobalSnackbar from '@/components/GlobalSnackbar.vue'

const route = useRoute()
const themeStore = useThemeStore()
const auth = useAuthStore()

// Login (and any public route) renders bare, without the app shell. The shell
// also waits for a session: before the router has resolved the first route,
// `meta.public` is still unknown, and mounting the shell then fired the
// notification poll without a token (a 401 on every fresh load of /login).
const isBare = computed(() => route.meta.public === true || !auth.isAuthenticated)
</script>

<template>
  <v-app :theme="themeStore.current">
    <AppLayout v-if="!isBare" />
    <router-view v-else v-slot="{ Component }">
      <transition name="page-fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
    <GlobalSnackbar />
  </v-app>
</template>
