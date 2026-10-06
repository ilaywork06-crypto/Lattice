<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { authApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { extractError } from '@/api/client'
import BrandLogo from '@/components/BrandLogo.vue'
import { ROLE_COLORS, ROLE_LABELS } from '@/constants'
import type { LoginHint } from '@/api/types'

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

// Which accounts are offered here is a manager's decision (Users & Permissions),
// not a hard-coded list — so a deployment that shouldn't advertise any simply
// has none, and the whole section disappears.
const hints = ref<LoginHint[]>([])

async function loadHints() {
  try {
    hints.value = await authApi.loginHints()
  } catch {
    // The shortcuts are a convenience; never block sign-in over them.
    hints.value = []
  }
}

function fill(hint: LoginHint) {
  email.value = hint.email
  // Only pre-filled where a manager published the password; otherwise the field
  // is cleared and focus is left to the user to type it.
  password.value = hint.password ?? ''
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

onMounted(loadHints)
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
            <BrandLogo :size="72" class="mx-auto mb-3" />
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

              <template v-if="hints.length">
                <v-divider class="my-5">
                  <span class="text-caption text-medium-emphasis px-2">{{ $t('login.demoAccounts') }}</span>
                </v-divider>

                <div class="d-flex flex-wrap justify-center gap-2">
                  <v-chip
                    v-for="hint in hints"
                    :key="hint.email"
                    :color="ROLE_COLORS[hint.role]"
                    variant="tonal"
                    size="small"
                    class="font-weight-medium"
                    @click="fill(hint)"
                  >
                    <v-icon start :icon="hint.password ? 'mdi-account-key' : 'mdi-account'" size="14" />
                    <bdi>{{ hint.full_name }}</bdi> · {{ ROLE_LABELS[hint.role] }}
                  </v-chip>
                </div>
                <p class="text-center text-caption text-medium-emphasis mt-3">
                  {{ hints.some((h) => h.password) ? $t('login.demoHint') : $t('login.demoHintEmailOnly') }}
                </p>
              </template>
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
