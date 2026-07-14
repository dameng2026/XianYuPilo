<template>
  <section class="card-panel">
    <div v-if="title || $slots.action" class="panel-head">
      <div>
        <h3><slot name="title">{{ title }}</slot></h3>
        <p v-if="$slots.desc || desc"><slot name="desc">{{ desc }}</slot></p>
      </div>
      <slot name="action" />
    </div>
    <div class="card-panel-body"><slot /></div>
  </section>
</template>
<script setup>
defineProps({ title: String, desc: String })
</script>
<style scoped>
.card-panel {
  min-width: 0;
}
.card-panel-body {
  min-width: 0;
  /* overflow-x: clip (not auto/hidden) so overflow-y stays visible.
     auto/hidden would compute overflow-y to auto, clipping absolutely
     positioned dropdowns (e.g. POI search in ProductPublishPage). */
  overflow-x: clip;
}
@media (max-width: 900px) {
  .card-panel-body {
    overflow-x: clip;
  }
}
</style>
