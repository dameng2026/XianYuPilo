export const IMAGE_UPLOAD_MAX_BYTES = 5 * 1024 * 1024

const ALLOWED_MEDIA_TYPES = new Set([
  'image/jpeg',
  'image/png',
  'image/gif',
  'image/webp',
])

const ALLOWED_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp'])

export function imageUploadValidationMessage(file) {
  if (!file || typeof file !== 'object') return '文件无效，请重新选择图片'
  if (!Number.isFinite(file.size) || file.size <= 0) return '文件为空，请重新选择图片'
  if (file.size > IMAGE_UPLOAD_MAX_BYTES) return '大小超过 5MB，请压缩后重试'

  const mediaType = String(file.type || '').trim().toLowerCase()
  const extension = String(file.name || '').split('.').pop()?.toLowerCase() || ''
  if (
    (mediaType && !ALLOWED_MEDIA_TYPES.has(mediaType))
    || (!mediaType && !ALLOWED_EXTENSIONS.has(extension))
  ) {
    return '格式不受支持，仅支持 JPEG、PNG、GIF 和 WebP'
  }
  return ''
}
