import js from "@eslint/js";
import pluginVue from "eslint-plugin-vue";
import globals from "globals";

// 前端 ESLint flat config（ESLint 9+）
// - 纯 JS 走 @eslint/js 推荐规则（抓真实错误：no-undef / no-unused-vars 等）
// - .vue 走 eslint-plugin-vue 的 flat/essential（只抓真实错误，不启用模板格式规则）
//   说明：之前用 flat/recommended 会拉进 html-indent / max-attributes-per-line /
//   attributes-order / html-self-closing 等纯格式规则，与 IDE 格式化重复、噪音极大；
//   学习项目不上 Prettier，故降为 essential，让 lint 只管「会不会出 bug」。
// - globals.browser：声明 fetch / URLSearchParams / window 等浏览器全局，
//   否则 @eslint/js recommended 会把这些判成 no-undef error
export default [
  js.configs.recommended,
  ...pluginVue.configs["flat/essential"],
  {
    files: ["**/*.vue", "**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
      },
    },
  },
  {
    rules: {
      // 学习项目：未用变量仅 warn 不拦（Vue 的 v-for 未用索引已由 vue/no-unused-vars 抓）
      "no-unused-vars": "warn",
      "no-console": "off",
    },
  },
  {
    ignores: ["dist/**", "node_modules/**"],
  },
];
