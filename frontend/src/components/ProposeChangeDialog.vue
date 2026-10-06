<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { changeRequestsApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import { CHANGE_ACTION_ICONS, CHANGE_ACTION_LABELS } from '@/constants'
import type { ProposeContext } from '@/lib/propose'

const props = defineProps<{
  modelValue: boolean
  context: ProposeContext | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submitted: []
}>()

const ui = useUiStore()
const auth = useAuthStore()
const { t } = useI18n({ useScope: 'global' })

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const reason = ref('')
const formRef = ref()
const submitting = ref(false)

const required = [(v: string) => !!v?.trim() || t('common.required')]

watch(
  () => props.modelValue,
  (v) => {
    if (v) reason.value = props.context?.reason?.trim() ?? ''
  },
)

const actionLabel = computed(() =>
  props.context ? CHANGE_ACTION_LABELS[props.context.action] : '',
)
const actionIcon = computed(() =>
  props.context ? CHANGE_ACTION_ICONS[props.context.action] : 'mdi-file',
)

async function submit() {
  if (!props.context) return
  const result = await formRef.value?.validate()
  if (result && !result.valid) return
  submitting.value = true
  try {
    await changeRequestsApi.create({
      action: props.context.action,
      item_id: props.context.itemId ?? null,
      template_id: props.context.templateId ?? null,
      item_type: props.context.itemType ?? null,
      payload: props.context.payload,
      reason: reason.value.trim(),
    })
    ui.success(t('propose.submittedToast'))
    open.value = false
    emit('submitted')
  } catch (e) {
    ui.error(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="600" scrollable>
    <v-card v-if="context" rounded="lg">
      <v-card-title class="d-flex align-center gap-2 pa-4">
        <v-icon icon="mdi-file-swap-outline" color="primary" />
        <span class="text-h6">{{ $t('propose.title') }}</span>
      </v-card-title>
      <v-divider />

      <v-card-text class="pa-4">
        <v-alert type="info" variant="tonal" density="comfortable" class="mb-4">
          <div class="d-flex align-center gap-2">
            <v-icon :icon="actionIcon" size="18" />
            <span>
              <strong>{{ actionLabel }}</strong>
              <template v-if="context.targetName"> · {{ context.targetName }}</template>
            </span>
          </div>
          <div class="text-caption mt-1">
            {{ auth.isViewer ? $t('propose.viewerNote') : $t('propose.editorNote') }}
          </div>
        </v-alert>

        <v-table v-if="context.summaryLines?.length" density="compact" class="mb-4 rounded border">
          <tbody>
            <tr v-for="line in context.summaryLines" :key="line.label">
              <td class="text-medium-emphasis" style="width: 40%"><bdi>{{ line.label }}</bdi></td>
              <td class="font-weight-medium"><bdi>{{ line.value }}</bdi></td>
            </tr>
          </tbody>
        </v-table>

        <v-form ref="formRef" @submit.prevent="submit">
          <v-textarea
            v-model="reason"
            :label="$t('propose.reasonLabel')"
            :placeholder="$t('propose.reasonPlaceholder')"
            rows="3"
            auto-grow
            :rules="required"
            :hint="context.reason ? $t('propose.reasonPrefilled') : undefined"
            persistent-hint
            autofocus
          />
        </v-form>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-3">
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ $t('common.cancel') }}</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          prepend-icon="mdi-send"
          :loading="submitting"
          @click="submit"
        >
          {{ $t('propose.submit') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
