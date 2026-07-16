<template>
  <div class="publish-address-cascader">
    <div v-if="loading" class="address-state">正在加载地址数据...</div>
    <div v-else-if="loadError || !addressTree.length" class="address-state error">
      {{ loadError || '地址数据未加载，请检查地址字典是否已初始化' }}
    </div>
    <template v-else>
      <div class="address-selects">
        <select v-model="selectedProv" @change="onProvChange">
          <option value="">请选择省份</option>
          <option v-for="province in addressTree" :key="province.name" :value="province.name">{{ province.name }}</option>
        </select>
        <select v-model="selectedCity" :disabled="!selectedProv" @change="onCityChange">
          <option value="">请选择城市</option>
          <option v-for="city in cityList" :key="city.name" :value="city.name">{{ city.name }}</option>
        </select>
        <select v-model="selectedDistrict" :disabled="!selectedCity" @change="onDistrictChange">
          <option value="">请选择区县</option>
          <option v-for="district in districtList" :key="district.adcode || district.name" :value="district.name">{{ district.name }}</option>
        </select>
      </div>
      <div v-if="selectedDistrictInfo" class="selected-address">
        <div>
          <b>{{ selectedDistrictInfo.poiName || selectedDistrict }}</b>
          <span>{{ selectedProv }} {{ selectedCity }} {{ selectedDistrict }}</span>
        </div>
        <button v-if="clearable" type="button" @click="clearSelection">清除</button>
      </div>
      <div v-else-if="legacyAddress" class="legacy-address">
        <div>
          <b>{{ legacyAddress.poiName || '历史地址' }}</b>
          <span>{{ legacyAddressText || '历史地址无法拆分为省、市、区' }}</span>
        </div>
        <button v-if="clearable" type="button" @click="clearSelection">清除</button>
        <p>这是已保留的历史地址；重新选择省、市、区后会保存为新的结构化地址。</p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { addressDictTree } from '../api/misc.js'
import { formatPublishAddress, normalizePublishAddress } from '../utils/publishAddress.js'

const props = defineProps({
  modelValue: { type: Object, default: null },
  clearable: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const addressTree = ref([])
const loading = ref(false)
const loadError = ref('')
const selectedProv = ref('')
const selectedCity = ref('')
const selectedDistrict = ref('')
const selectedDistrictInfo = ref(null)

const cityList = computed(() => {
  const province = addressTree.value.find((item) => item.name === selectedProv.value)
  return province?.cities || []
})
const districtList = computed(() => {
  const city = cityList.value.find((item) => item.name === selectedCity.value)
  return city?.districts || []
})
const legacyAddress = computed(() => {
  const address = normalizePublishAddress(props.modelValue)
  const isChoosingNewAddress = selectedProv.value || selectedCity.value || selectedDistrict.value
  return address && !selectedDistrictInfo.value && !isChoosingNewAddress ? address : null
})
const legacyAddressText = computed(() => formatPublishAddress(legacyAddress.value))

function resetSelection() {
  selectedProv.value = ''
  selectedCity.value = ''
  selectedDistrict.value = ''
  selectedDistrictInfo.value = null
}

function syncSelection(address) {
  resetSelection()
  const normalized = normalizePublishAddress(address)
  if (!normalized || !addressTree.value.length) return
  const province = addressTree.value.find((item) => item.name === normalized.prov)
  const city = province?.cities?.find((item) => item.name === normalized.city)
  const district = city?.districts?.find((item) =>
    item.name === normalized.area && (!normalized.divisionId || String(item.divisionId || '') === normalized.divisionId),
  )
  if (!district) return
  selectedProv.value = province.name
  selectedCity.value = city.name
  selectedDistrict.value = district.name
  selectedDistrictInfo.value = district
}

function onProvChange() {
  selectedCity.value = ''
  selectedDistrict.value = ''
  selectedDistrictInfo.value = null
  emit('update:modelValue', null)
}

function onCityChange() {
  selectedDistrict.value = ''
  selectedDistrictInfo.value = null
  emit('update:modelValue', null)
}

function onDistrictChange() {
  const district = districtList.value.find((item) => item.name === selectedDistrict.value)
  selectedDistrictInfo.value = district || null
  if (!district) return
  emit('update:modelValue', {
    prov: selectedProv.value,
    city: selectedCity.value,
    area: selectedDistrict.value,
    divisionId: district.divisionId || district.adcode || '',
    gps: district.gps || '',
    poiId: district.poiId || '',
    poiName: district.poiName || selectedDistrict.value,
    detail: district.detail || '',
    source: 'address-dict',
  })
}

function clearSelection() {
  resetSelection()
  emit('update:modelValue', null)
}

async function loadAddressTree() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await addressDictTree()
    const provinces = response?.data?.provinces
    if (!Array.isArray(provinces)) throw new Error('地址字典响应格式异常')
    addressTree.value = provinces
    if (!addressTree.value.length) loadError.value = '地址字典当前为空，请联系管理员初始化后重试'
    syncSelection(props.modelValue)
  } catch (error) {
    console.warn('[publish-address-cascader] 加载地址字典失败', error)
    addressTree.value = []
    loadError.value = '地址数据加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (address) => {
  // While the user is cascading through a new choice, keep the visible
  // province/city values even though the parent value is intentionally reset.
  if (!address && (selectedProv.value || selectedCity.value || selectedDistrict.value)) return
  syncSelection(address)
}, { deep: true })
onMounted(loadAddressTree)
</script>

<style scoped>
.address-state { padding: 14px; color: #667085; font-size: 13px; text-align: center; }
.address-state.error { color: #dc2626; }
.address-selects { display: flex; gap: 10px; flex-wrap: wrap; }
.address-selects select { flex: 1; min-width: 120px; padding: 10px 14px; border: 2px solid #e4e7ec; border-radius: 10px; color: #344054; background: #fff; font-size: 14px; }
.address-selects select:focus { outline: none; border-color: var(--primary, #1677ff); }
.address-selects select:disabled { background: #f2f4f7; color: #98a2b3; cursor: not-allowed; }
.selected-address, .legacy-address { display: flex; align-items: start; justify-content: space-between; gap: 10px; margin-top: 10px; padding: 9px 11px; border-radius: 9px; }
.selected-address { border: 1px solid #b3d4ff; background: #eaf3ff; }
.legacy-address { display: grid; grid-template-columns: minmax(0, 1fr) auto; border: 1px solid #fed7aa; background: #fff7ed; }
.selected-address > div, .legacy-address > div { min-width: 0; }
.selected-address b, .legacy-address b, .selected-address span, .legacy-address span { display: block; }
.selected-address b, .legacy-address b { color: #1d4ed8; font-size: 13px; }
.legacy-address b { color: #9a3412; }
.selected-address span, .legacy-address span { margin-top: 2px; color: #667085; font-size: 12px; }
.selected-address button, .legacy-address button { border: 0; background: transparent; color: #0d6bff; cursor: pointer; padding: 0; font-size: 13px; }
.legacy-address button { color: #c2410c; }
.legacy-address p { grid-column: 1 / -1; margin: 0; color: #9a3412; font-size: 12px; line-height: 1.5; }
</style>
