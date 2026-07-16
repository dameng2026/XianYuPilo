export const PUBLISH_ADDRESS_REQUIRED_FIELDS = [
  'poiName',
  'prov',
  'city',
  'area',
  'divisionId',
  'gps',
  'poiId',
]

export function cleanAddressValue(value) {
  const text = value == null ? '' : String(value).trim()
  return text.toLowerCase() === 'null' ? '' : text
}

/**
 * Accepts both the current address-dictionary payload and historical POI/manual
 * payloads. Unknown legacy fields are deliberately preserved for display and
 * only replaced after the user chooses a new province/city/district.
 */
export function normalizePublishAddress(raw) {
  if (!raw || typeof raw !== 'object') return null
  const address = {
    ...raw,
    poiName: cleanAddressValue(raw.poiName || raw.addressPoiName || raw.name || raw.addressText || raw.address),
    prov: cleanAddressValue(raw.prov || raw.addressProv || raw.pname),
    city: cleanAddressValue(raw.city || raw.addressCity || raw.cityname),
    area: cleanAddressValue(raw.area || raw.addressArea || raw.adname || raw.district),
    divisionId: cleanAddressValue(raw.divisionId || raw.addressDivisionId || raw.adcode),
    gps: cleanAddressValue(raw.gps || raw.addressGps || raw.location),
    poiId: cleanAddressValue(raw.poiId || raw.addressPoiId || raw.id),
    detail: cleanAddressValue(raw.detail || raw.addressDetail),
  }
  if (!address.detail && raw.address && raw.address !== address.poiName) address.detail = cleanAddressValue(raw.address)
  if (!address.source) address.source = 'legacy'
  return address
}

export function getPublishAddressMissingFields(address) {
  const normalized = normalizePublishAddress(address)
  if (!normalized) return [...PUBLISH_ADDRESS_REQUIRED_FIELDS]
  return PUBLISH_ADDRESS_REQUIRED_FIELDS.filter((key) => !cleanAddressValue(normalized[key]))
}

export function isPublishAddressComplete(address) {
  return getPublishAddressMissingFields(address).length === 0
}

export function formatPublishAddress(address) {
  const normalized = normalizePublishAddress(address)
  if (!normalized) return ''
  return [normalized.prov, normalized.city, normalized.area, normalized.detail]
    .filter(Boolean)
    .join(' ')
}
