<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { extractError } from '@/api/client'
import { ROLE_COLORS, ROLE_LABELS } from '@/constants'
import type { UserRole } from '@/api/types'

const auth = useAuthStore()
const themeStore = useThemeStore()
const router = useRouter()
const route = useRoute()
const { t } = useI18n({ useScope: 'global' })

const email = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const error = ref('')

interface Demo {
  email: string
  password: string
  role: UserRole
  name: string
}
const demos: Demo[] = [
  { email: 'admin@lattice.io', password: 'admin1234', role: 'manager', name: 'Admin' },
  { email: 'noa@lattice.io', password: 'password', role: 'manager', name: 'Noa' },
  { email: 'dana@lattice.io', password: 'password', role: 'editor', name: 'Dana' },
  { email: 'amir@lattice.io', password: 'password', role: 'viewer', name: 'Amir' },
]

function fill(demo: Demo) {
  email.value = demo.email
  password.value = demo.password
  error.value = ''
}

async function submit() {
  error.value = ''
  if (!email.value || !password.value) {
    error.value = t('auth.fillEmailPassword')
    return
  }
  loading.value = true
  try {
    await auth.login(email.value.trim(), password.value)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e) {
    error.value = extractError(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <v-main class="login-bg">
    <v-btn
      class="theme-toggle"
      :icon="themeStore.isDark ? 'mdi-weather-sunny' : 'mdi-weather-night'"
      variant="tonal"
      @click="themeStore.toggle()"
    />
    <v-container class="fill-height">
      <v-row justify="center" align="center">
        <v-col cols="12" sm="9" md="6" lg="4">
          <div class="text-center mb-6">
            <v-avatar color="primary" size="64" rounded="lg" class="mb-3">
              <span class="text-h4 font-weight-bold text-white">R</span>
            </v-avatar>
            <h1 class="text-h4 font-weight-bold">Lattice</h1>
            <p class="text-body-2 text-medium-emphasis">{{ $t('login.brandSubtitle') }}</p>
          </div>

          <v-card rounded="xl" elevation="8" class="pa-2">
            <v-card-text>
              <v-form @submit.prevent="submit">
                <v-text-field
                  v-model="email"
                  :label="$t('auth.email')"
                  type="email"
                  prepend-inner-icon="mdi-email-outline"
                  autocomplete="username"
                  autofocus
                  class="mb-2"
                />
                <v-text-field
                  v-model="password"
                  :label="$t('auth.password')"
                  :type="showPassword ? 'text' : 'password'"
                  prepend-inner-icon="mdi-lock-outline"
                  :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
                  autocomplete="current-password"
                  @click:append-inner="showPassword = !showPassword"
                  @keyup.enter="submit"
                />

                <v-alert
                  v-if="error"
                  type="error"
                  variant="tonal"
                  density="compact"
                  class="mb-4"
                  :text="error"
                />

                <v-btn
                  type="submit"
                  color="primary"
                  size="large"
                  block
                  :loading="loading"
                  prepend-icon="mdi-login"
                >
                  {{ $t('auth.signIn') }}
                </v-btn>
              </v-form>

              <v-divider class="my-5">
                <span class="text-caption text-medium-emphasis px-2">{{ $t('login.demoAccounts') }}</span>
              </v-divider>

              <div class="d-flex flex-wrap justify-center gap-2">
                <v-chip
                  v-for="demo in demos"
                  :key="demo.email"
                  :color="ROLE_COLORS[demo.role]"
                  variant="tonal"
                  size="small"
                  class="font-weight-medium"
                  @click="fill(demo)"
                >
                  <v-icon start icon="mdi-account" size="14" />
                  {{ demo.name }} · {{ ROLE_LABELS[demo.role] }}
                </v-chip>
              </div>
              <p class="text-center text-caption text-medium-emphasis mt-3">
                {{ $t('login.demoHint') }}
              </p>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </v-container>
  </v-main>
</template>

<style scoped>
.login-bg {
  background:
    radial-gradient(1200px 600px at 10% -10%, rgba(91, 110, 245, 0.22), transparent 60%),
    radial-gradient(900px 500px at 110% 10%, rgba(0, 188, 212, 0.18), transparent 55%);
}
.theme-toggle {
  position: absolute;
  top: 16px;
  inset-inline-end: 16px;
  z-index: 5;
}
</style>
