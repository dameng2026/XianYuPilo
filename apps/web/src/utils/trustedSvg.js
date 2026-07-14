const FORBIDDEN_SVG_MARKUP = /<(?:script|style|foreignObject|iframe|object|embed|link|meta)\b|\son[a-z]+\s*=|(?:javascript|data\s*:\s*text\/html)\s*:/i

/**
 * Audit boundary for the small, source-controlled SVG icon registries.
 * Runtime/API/user-provided markup must never be passed to this function.
 */
export function trustedSvg(markup) {
  const source = String(markup || '').trim()
  if (!source || !/^<svg\b[\s\S]*<\/svg>$/.test(source)) return ''
  if (FORBIDDEN_SVG_MARKUP.test(source)) return ''
  return source
}
