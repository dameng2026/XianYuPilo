import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { pruneUnreferencedSourcePublicAssets } from './public-assets.mjs'

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const result = pruneUnreferencedSourcePublicAssets(webRoot)

console.log(
  `pruned ${result.removedFiles} unreferenced public source assets `
  + `(${(result.removedBytes / 1024 / 1024).toFixed(2)} MiB)`,
)
