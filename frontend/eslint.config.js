import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import sonarjs from "eslint-plugin-sonarjs";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "playwright-report", "test-results"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  sonarjs.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "sonarjs/cognitive-complexity": ["warn", 15],
      "sonarjs/no-duplicate-string": "off",
    },
  },
  {
    files: ["e2e/**/*.ts", "playwright.config.ts", "vite.config.ts"],
    rules: {
      "sonarjs/no-duplicate-string": "off",
      // The local accounts are documented in the README; nothing secret here.
      "sonarjs/no-hardcoded-passwords": "off",
    },
  }
);
