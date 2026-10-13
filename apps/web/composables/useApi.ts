export function resolveApi(path: string) {
  const config = useRuntimeConfig()
  const p = path.startsWith("/") ? path : `/${path}`
  const full = p.startsWith("/api") ? p : `/api${p}`
  if (import.meta.server) {
    return `${config.apiInternal}${full}`
  }
  return full
}

export function useApi() {
  const get = <T>(path: string, query?: Record<string, string | number | undefined>) =>
    $fetch<T>(resolveApi(path), { query })

  const postForm = <T>(path: string, body: FormData, token: string) =>
    $fetch<T>(resolveApi(path), {
      method: "POST",
      body,
      headers: { "X-Admin-Token": token },
    })

  const post = <T>(path: string, token: string) =>
    $fetch<T>(resolveApi(path), {
      method: "POST",
      headers: { "X-Admin-Token": token },
    })

  return { get, post, postForm }
}
