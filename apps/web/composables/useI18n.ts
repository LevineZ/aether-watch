import { messages, type Locale, type MessageKey } from "~/utils/messages"

const STORAGE_KEY = "aetherwatch.locale"

export function useI18n() {
  const locale = useState<Locale>("aw-locale", () => "zh")

  function t(key: MessageKey, vars?: Record<string, string | number>) {
    const dict = messages[locale.value] || messages.zh
    let s: string = dict[key] || messages.zh[key] || key
    if (vars) {
      for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v))
    }
    return s
  }

  function setLocale(next: Locale) {
    locale.value = next
    if (!import.meta.client) return
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* private mode */
    }
    document.documentElement.lang = next === "zh" ? "zh-CN" : "en"
  }

  function toggleLocale() {
    setLocale(locale.value === "zh" ? "en" : "zh")
  }

  /** Call from onMounted only — avoids SSR/localStorage hydration mismatch. */
  function hydrateLocale() {
    if (!import.meta.client) return
    try {
      const v = localStorage.getItem(STORAGE_KEY)
      if (v === "en" || v === "zh") setLocale(v)
      else document.documentElement.lang = "zh-CN"
    } catch {
      document.documentElement.lang = "zh-CN"
    }
  }

  return { locale, t, setLocale, toggleLocale, hydrateLocale }
}
