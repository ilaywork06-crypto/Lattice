<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import AppLayout from '@/components/AppLayout.vue'
import GlobalSnackbar from '@/components/GlobalSnackbar.vue'

const route = useRoute()
const themeStore = useThemeStore()

// Login (and any public route) renders bare, without the app shell.
const isBare = computed(() => route.meta.public === true)
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
