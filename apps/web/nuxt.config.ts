export default defineNuxtConfig({
  ssr: true,
  compatibilityDate: "2025-01-01",
  css: ["~/assets/css/main.css"],
  app: {
    head: {
      title: "AetherWatch",
      htmlAttrs: { lang: "zh-CN" },
      meta: [
        {
          name: "description",
          content: "AetherWatch — weather and intelligence, observed. Multi-model forecast, wind globe, and editorial notes.",
        },
        { name: "theme-color", content: "#c1440e" },
      ],
      link: [
        { rel: "icon", type: "image/svg+xml", href: "/favicon.svg" },
        { rel: "preconnect", href: "https://fonts.googleapis.com" },
        { rel: "preconnect", href: "https://fonts.gstatic.com", crossorigin: "" },
        {
          rel: "stylesheet",
          href: "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,620;9..144,700&family=Figtree:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@500;650&display=swap",
        },
      ],
    },
  },
  runtimeConfig: {
    apiInternal: process.env.NUXT_API_INTERNAL || "http://127.0.0.1:8000",
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || "/api",
    },
  },
  vite: {
    optimizeDeps: {
      include: ["maplibre-gl"],
    },
  },
})
