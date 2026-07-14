import pluginJs from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

const relaxedLegacyRules = {
  'no-console': ['warn', { allow: ['warn', 'error', 'log'] }],
  'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
  'no-empty': 'warn',
  'no-irregular-whitespace': 'warn',
  'no-useless-assignment': 'warn'
}

export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'output/**', '.pytest_cache/**', 'tmp-*.js']
  },
  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.es2024
      }
    }
  },
  pluginJs.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.{js,mjs,vue}'],
    rules: {
      ...relaxedLegacyRules,
      'vue/multi-word-component-names': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/html-self-closing': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-indent': 'off',
      'vue/require-default-prop': 'off'
    }
  }
]
