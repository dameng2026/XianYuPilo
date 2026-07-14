<template>
  <label :class="['admin-config-field', { 'is-wide': wide }]">
    <div class="admin-config-field-head">
      <div class="admin-config-field-copy">
        <div class="admin-config-field-title-row">
          <span class="admin-config-field-label">{{ label }}</span>
          <span v-if="required" class="admin-config-field-required">必填</span>
        </div>
        <p v-if="hint" class="admin-config-field-hint">{{ hint }}</p>
      </div>
      <span v-if="badge" class="admin-config-field-badge">{{ badge }}</span>
    </div>

    <div class="admin-config-field-control">
      <slot />
    </div>

    <p v-if="meta" class="admin-config-field-meta">{{ meta }}</p>
  </label>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  hint: { type: String, default: '' },
  meta: { type: String, default: '' },
  badge: { type: String, default: '' },
  required: Boolean,
  wide: Boolean,
})
</script>

<style scoped>
.admin-config-field {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px;
  border-radius: 20px;
  border: 1px solid rgba(223, 232, 247, 0.98);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 251, 255, 0.94));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.82);
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}

.admin-config-field:hover {
  transform: translateY(-1px);
  border-color: rgba(189, 210, 243, 0.98);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 14px 28px rgba(31, 53, 94, 0.06);
}

.admin-config-field.is-wide {
  grid-column: 1 / -1;
}

.admin-config-field-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.admin-config-field-copy {
  min-width: 0;
}

.admin-config-field-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.admin-config-field-label {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  font-size: 14px;
  font-weight: 800;
  color: #15213d;
  letter-spacing: 0.2px;
}

.admin-config-field-required {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(239, 68, 68, 0.08);
  color: #e14d4d;
  font-size: 11px;
  font-weight: 700;
}

.admin-config-field-hint {
  margin: 5px 0 0;
  color: #7786a0;
  font-size: 12px;
  line-height: 1.6;
}

.admin-config-field-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(13, 107, 255, 0.08);
  color: #2c63d4;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.admin-config-field-control {
  display: flex;
  width: 100%;
}

.admin-config-field-control :deep(.config-input),
.admin-config-field-control :deep(.config-textarea) {
  width: 100%;
  border: 1px solid rgba(214, 225, 242, 0.95);
  border-radius: 14px;
  background: #fff;
  color: #33435f;
  text-align: left;
  transition: border-color .18s ease, box-shadow .18s ease, background .18s ease;
}

.admin-config-field-control :deep(.config-input) {
  height: 46px;
  padding: 0 14px;
}

.admin-config-field-control :deep(.config-textarea) {
  min-height: 112px;
  padding: 12px 14px;
  line-height: 1.72;
  resize: vertical;
}

.admin-config-field-control :deep(.config-input::placeholder),
.admin-config-field-control :deep(.config-textarea::placeholder) {
  color: #a0adc2;
  text-align: left;
}

.admin-config-field-control :deep(.config-input:hover),
.admin-config-field-control :deep(.config-textarea:hover) {
  border-color: #c7d7ef;
}

.admin-config-field-control :deep(.config-input:focus),
.admin-config-field-control :deep(.config-input:focus-visible),
.admin-config-field-control :deep(.config-textarea:focus),
.admin-config-field-control :deep(.config-textarea:focus-visible) {
  outline: none;
  border-color: #0d6bff;
  box-shadow: 0 0 0 4px rgba(13, 107, 255, 0.11);
  background: #fff;
}

.admin-config-field-control :deep(.secret-input) {
  width: 100%;
  height: 46px;
  border-radius: 14px;
}

.admin-config-field-meta {
  margin: 0;
  color: #5f728f;
  font-size: 12px;
  line-height: 1.6;
}
</style>
