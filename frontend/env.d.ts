/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CORE_API_URL: string
  readonly VITE_NOTIFICATION_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}
