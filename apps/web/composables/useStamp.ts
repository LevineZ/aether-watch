export function beijingStamp(iso?: string, locale: "zh" | "en" = "zh") {
  const d = iso ? new Date(iso) : new Date()
  const tag = locale === "en" ? "en-GB" : "zh-CN"
  const fmt = new Intl.DateTimeFormat(tag, {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "long",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
  const parts = Object.fromEntries(fmt.formatToParts(d).map((p) => [p.type, p.value]))
  if (locale === "en") {
    return {
      dateLine: `${parts.weekday} ${parts.day}/${parts.month}/${parts.year}`,
      clock: `${parts.hour}:${parts.minute}`,
      iso: d.toISOString(),
    }
  }
  return {
    dateLine: `${parts.year}年${parts.month}月${parts.day}日 · ${parts.weekday}`,
    clock: `${parts.hour}:${parts.minute}`,
    iso: d.toISOString(),
  }
}
