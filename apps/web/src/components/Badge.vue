<template><span :class="['badge', type || 'green']"><slot /></span></template>
<script setup>defineProps({ type: String })</script>
