<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<template>
  <v-container class="fill-height">
    <v-row justify="center">
      <v-col cols="12" md="6" class="text-center">
        <v-icon icon="mdi-compass-off-outline" size="96" color="primary" class="mb-4" />
        <h1 class="text-h3 font-weight-bold mb-2">404</h1>
        <p class="text-body-1 text-medium-emphasis mb-6">
          {{ $t('notFound.text') }}
        </p>
        <v-btn color="primary" prepend-icon="mdi-home" @click="router.push('/')">
          {{ $t('notFound.back') }}
        </v-btn>
      </v-col>
    </v-row>
  </v-container>
</template>
