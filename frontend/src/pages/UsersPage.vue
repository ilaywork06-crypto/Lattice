<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { usersApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import { ROLE_COLORS, ROLE_LABELS } from '@/constants'
import type { UserBrief, UserRole } from '@/api/types'

const auth = useAuthStore()
const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

const users = ref<UserBrief[]>([])
const loading = ref(false)
const search = ref('')

const roles: UserRole[] = ['viewer', 'editor', 'manager']

const headers = computed(() => [
  { title: t('fields.name'), key: 'full_name' },
  { title: t('users.email'), key: 'email' },
  { title: t('users.role'), key: 'role', width: 160 },
  { title: '', key: 'actions', sortable: false, align: 'end', width: 120 },
])

async function load() {
  loading.value = true
  try {
    users.value = await usersApi.list()
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

// ---- Create / edit dialog -------------------------------------------------
const dialog = ref(false)
const editing = ref<UserBrief | null>(null)
const saving = ref(false)
const form = reactive<{
  email: string
  full_name: string
  password: string
  role: UserRole
  is_active: boolean
}>({ email: '', full_name: '', password: '', role: 'viewer', is_active: true })

function openCreate() {
  editing.value = null
  form.email = ''
  form.full_name = ''
  form.password = ''
  form.role = 'viewer'
  form.is_active = true
  dialog.value = true
}

function openEdit(u: UserBrief) {
  editing.value = u
  form.email = u.email
  form.full_name = u.full_name
  form.password = ''
  form.role = u.role
  form.is_active = true
  dialog.value = true
}

async function save() {
  saving.value = true
  try {
    if (editing.value) {
      await usersApi.update(editing.value.id, {
        full_name: form.full_name.trim(),
        role: form.role,
        is_active: form.is_active,
        password: form.password.trim() || undefined,
      })
      ui.success(t('users.updated'))
    } else {
      if (!form.email.trim() || !form.full_name.trim() || !form.password.trim()) {
        ui.warning(t('users.requiredFields'))
        saving.value = false
        return
      }
      await usersApi.create({
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
        role: form.role,
      })
      ui.success(t('users.created'))
    }
    dialog.value = false
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    saving.value = false
  }
}

// ---- Delete ---------------------------------------------------------------
const removeUser = ref<UserBrief | null>(null)
async function confirmRemove() {
  if (!removeUser.value) return
  try {
    await usersApi.remove(removeUser.value.id)
    ui.success(t('users.deleted'))
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    removeUser.value = null
  }
}

onMounted(load)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader
      :title="$t('nav.users')"
      :subtitle="$t('users.subtitle')"
      icon="mdi-account-group-outline"
    >
      <template #actions>
        <v-btn color="primary" prepend-icon="mdi-account-plus" @click="openCreate">{{ $t('users.addUser') }}</v-btn>
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <v-card-text>
        <v-text-field
          v-model="search"
          :label="$t('users.searchUsers')"
          prepend-inner-icon="mdi-magnify"
          clearable
          hide-details
          density="comfortable"
          style="max-width: 360px"
        />
      </v-card-text>
      <v-divider />
      <v-data-table
        :headers="headers as any"
        :items="users"
        :loading="loading"
        :search="search"
        item-value="id"
        density="comfortable"
      >
        <template #item.full_name="{ item }">
          <div class="d-flex align-center gap-3">
            <v-avatar :color="ROLE_COLORS[item.role]" size="34">
              <span class="text-caption font-weight-bold text-white">
                {{ item.full_name.split(' ').map((p: string) => p[0]).slice(0, 2).join('') }}
              </span>
            </v-avatar>
            <span class="font-weight-medium">{{ item.full_name }}</span>
            <v-chip v-if="item.id === auth.userId" size="x-small" variant="tonal">{{ $t('users.you') }}</v-chip>
          </div>
        </template>
        <template #item.role="{ item }">
          <v-chip :color="ROLE_COLORS[item.role]" size="small" variant="tonal">
            {{ ROLE_LABELS[item.role] }}
          </v-chip>
        </template>
        <template #item.actions="{ item }">
          <v-btn icon="mdi-pencil" size="small" variant="text" @click="openEdit(item)" />
          <v-btn
            icon="mdi-delete-outline"
            size="small"
            variant="text"
            color="error"
            :disabled="item.id === auth.userId"
            @click="removeUser = item"
          />
        </template>
        <template #no-data>
          <EmptyState icon="mdi-account-group-outline" :title="$t('users.noUsers')" />
        </template>
      </v-data-table>
    </v-card>

    <!-- Create / edit dialog -->
    <v-dialog v-model="dialog" max-width="520">
      <v-card rounded="lg">
        <v-card-title class="pa-4">{{ editing ? $t('users.editUser') : $t('users.addUser') }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-text-field
            v-model="form.email"
            :label="$t('users.emailReq')"
            type="email"
            :disabled="!!editing"
            class="mb-1"
          />
          <v-text-field v-model="form.full_name" :label="$t('users.fullNameReq')" class="mb-1" />
          <v-text-field
            v-model="form.password"
            :label="editing ? $t('users.newPassword') : $t('users.passwordReq')"
            type="password"
            class="mb-1"
          />
          <v-select
            v-model="form.role"
            :label="$t('users.role')"
            class="mb-1"
            :items="roles.map((r) => ({ title: ROLE_LABELS[r], value: r }))"
          />
          <v-switch
            v-if="editing"
            v-model="form.is_active"
            :label="$t('users.active')"
            color="success"
            hide-details
            density="comfortable"
          />
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="saving" @click="save">
            {{ editing ? $t('common.save') : $t('common.create') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ConfirmDialog
      :model-value="removeUser !== null"
      :title="$t('users.deleteTitle')"
      :message="removeUser ? $t('users.deleteMsg', { name: removeUser.full_name }) : ''"
      :confirm-text="$t('common.delete')"
      @update:model-value="(v) => !v && (removeUser = null)"
      @confirm="confirmRemove"
    />
  </v-container>
</template>
