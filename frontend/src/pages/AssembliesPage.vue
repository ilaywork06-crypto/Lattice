<script setup lang="ts">
import ItemsListView from '@/components/ItemsListView.vue'
</script>

<template>
  <ItemsListView type="assembly" icon="mdi-cpu-64-bit" :subtitle="$t('subtitles.assemblies')" />
</template>
