import fs from 'node:fs'
import { TextDecoder } from 'node:util'

export const MAX_SECRET_FILE_BYTES = 64 * 1024

const utf8Decoder = new TextDecoder('utf-8', { fatal: true })

export class FileSecretConfigurationError extends Error {
  override readonly name = 'FileSecretConfigurationError'
}

function configurationError(fieldName: string, detail: string): FileSecretConfigurationError {
  return new FileSecretConfigurationError(`${fieldName}_FILE ${detail}`)
}

function readSecretFile(filePath: string, fieldName: string): string {
  let descriptor: number | undefined
  try {
    descriptor = fs.openSync(filePath, 'r')
    if (!fs.fstatSync(descriptor).isFile()) {
      throw configurationError(fieldName, 'must reference a regular file')
    }

    const buffer = Buffer.allocUnsafe(MAX_SECRET_FILE_BYTES + 1)
    let length = 0
    while (length < buffer.length) {
      const bytesRead = fs.readSync(
        descriptor,
        buffer,
        length,
        buffer.length - length,
        null,
      )
      if (bytesRead === 0) break
      length += bytesRead
    }
    if (length > MAX_SECRET_FILE_BYTES) {
      throw configurationError(fieldName, 'exceeds the maximum allowed size')
    }

    let value: string
    try {
      value = utf8Decoder.decode(buffer.subarray(0, length))
    } catch {
      throw configurationError(fieldName, 'must contain valid UTF-8')
    }
    if (value.endsWith('\r\n')) value = value.slice(0, -2)
    else if (value.endsWith('\n')) value = value.slice(0, -1)
    if (value.includes('\r') || value.includes('\n')) {
      throw configurationError(fieldName, 'must contain exactly one logical line')
    }
    if (value.includes('\0')) {
      throw configurationError(fieldName, 'contains an invalid control character')
    }
    if (!value.trim()) throw configurationError(fieldName, 'must not be empty')
    return value
  } catch (error) {
    if (error instanceof FileSecretConfigurationError) throw error
    throw configurationError(fieldName, 'could not be read securely')
  } finally {
    if (descriptor !== undefined) {
      try {
        fs.closeSync(descriptor)
      } catch {
        // Startup will already fail for the primary read error. Never expose a path
        // or platform-specific close error while reporting secret configuration.
      }
    }
  }
}

export function readSecretEnvironmentValue(
  fieldName: string,
  environment: NodeJS.ProcessEnv = process.env,
): string {
  const directValue = String(environment[fieldName] || '').trim()
  const filePath = String(environment[`${fieldName}_FILE`] || '').trim()
  if (directValue && filePath) {
    throw new FileSecretConfigurationError(
      `${fieldName} and ${fieldName}_FILE cannot both be configured`,
    )
  }
  if (!filePath) return directValue
  return readSecretFile(filePath, fieldName)
}
