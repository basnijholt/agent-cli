import js from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import prettier from "eslint-plugin-prettier";
import prettierConfig from "eslint-config-prettier";

export default [
  js.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: {
          jsx: true,
        },
      },
      globals: {
        // Browser globals
        window: "readonly",
        document: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        fetch: "readonly",
        localStorage: "readonly",
        Response: "readonly",
        navigator: "readonly",
        // DOM types
        HTMLDivElement: "readonly",
        HTMLElement: "readonly",
        HTMLInputElement: "readonly",
        HTMLTextAreaElement: "readonly",
        HTMLButtonElement: "readonly",
        Element: "readonly",
        Node: "readonly",
        Event: "readonly",
        KeyboardEvent: "readonly",
        MouseEvent: "readonly",
        FocusEvent: "readonly",
        // Web APIs
        AbortController: "readonly",
        AbortSignal: "readonly",
        TextDecoder: "readonly",
        ReadableStreamDefaultReader: "readonly",
        DOMParser: "readonly",
        // Node.js globals
        process: "readonly",
        global: "readonly",
        __dirname: "readonly",
        __filename: "readonly",
        NodeJS: "readonly",
        // React
        React: "readonly",
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
      react: react,
      "react-hooks": reactHooks,
      prettier: prettier,
    },
    rules: {
      ...tseslint.configs.recommended.rules,
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      ...prettierConfig.rules,
      "prettier/prettier": "error",
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/explicit-function-return-type": "off",
      "no-console": ["warn", { allow: ["warn", "error"] }],
      // Allow setState in effects - common pattern for syncing state
      "react-hooks/set-state-in-effect": "off",
    },
    settings: {
      react: {
        version: "detect",
      },
    },
  },
  // Relaxed rules for test files
  {
    files: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}", "**/test/**/*.{ts,tsx}", "e2e/**/*.{ts,tsx}"],
    rules: {
      "no-console": "off",
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  {
    ignores: [
      "dist/**",
      "dist-main/**",
      "node_modules/**",
      "*.config.js",
      "*.config.ts",
      "playwright-report/**",
      "test-results/**",
    ],
  },
];
