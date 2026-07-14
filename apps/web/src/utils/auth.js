export const TOKEN_KEY = 'xianyu_auth_token'
export const USERNAME_KEY = 'xianyu_username'

function read(storage, key) {
  try {
    return storage?.getItem(key) || ''
  } catch {
    return ''
  }
}

function write(storage, key, value) {
  try {
    if (value) storage?.setItem(key, value)
    else storage?.removeItem(key)
  } catch {
    // Storage can be unavailable in privacy modes. Authentication still works
    // for the current page lifecycle even when persistence is unavailable.
  }
}

export function getToken() {
  return read(globalThis.sessionStorage, TOKEN_KEY) || read(globalThis.localStorage, TOKEN_KEY)
}

export function setAuth(token, username = '', { remember = false } = {}) {
  const activeStorage = remember ? globalThis.localStorage : globalThis.sessionStorage
  const inactiveStorage = remember ? globalThis.sessionStorage : globalThis.localStorage
  write(inactiveStorage, TOKEN_KEY, '')
  write(inactiveStorage, USERNAME_KEY, '')
  write(activeStorage, TOKEN_KEY, token)
  write(activeStorage, USERNAME_KEY, username)
}

export function clearAuth() {
  for (const storage of [globalThis.sessionStorage, globalThis.localStorage]) {
    write(storage, TOKEN_KEY, '')
    write(storage, USERNAME_KEY, '')
  }
}

export function getCachedUsername() {
  return read(globalThis.sessionStorage, USERNAME_KEY) || read(globalThis.localStorage, USERNAME_KEY)
}

export function isAuthed() {
  return !!getToken()
}
