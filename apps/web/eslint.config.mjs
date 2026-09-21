// ESLint flat config. `next lint` is deprecated (interactive prompt, removed in Next 16), so the
// harness runs the ESLint CLI directly with the Next.js rule sets (core-web-vitals + TypeScript).
import { FlatCompat } from "@eslint/eslintrc";
import { dirname } from "path";
import { fileURLToPath } from "url";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
];

export default config;
