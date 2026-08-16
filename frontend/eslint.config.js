import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import tsParser from '@typescript-eslint/parser'
import globals from 'globals'

export default [
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    ignores: ['dist/**', 'node_modules/**', 'src/**/*.d.ts'],
  },
  {
    files: ['src/**/*.{vue,js}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: {
        parser: tsParser,
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    rules: {
      // 存量代码已存在大量风格问题，此处只保留关键错误规则
      'no-unused-vars': 'off',
      'no-undef': 'off',  // TS 类型检查由 vue-tsc 负责
      'no-dupe-keys': 'error',
      'no-constant-condition': 'error',
      'vue/multi-word-component-names': 'off',
      'vue/no-v-html': 'off',
      'vue/no-mutating-props': 'warn',
      'vue/require-v-for-key': 'error',
      'vue/no-unused-components': 'warn',
      'no-console': 'off',
    },
  },
]
