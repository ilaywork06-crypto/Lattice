<script setup lang="ts">
import ItemsListView from '@/components/ItemsListView.vue'
</script>

<template>
  <ItemsListView type="card" icon="mdi-memory" :subtitle="$t('subtitles.cards')" />
</template>
