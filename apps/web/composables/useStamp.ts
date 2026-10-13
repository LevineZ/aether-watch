export function beijingStamp(iso?: string) {
  const d = iso ? new Date(iso) : new Date()
  const fmt = new Intl.DateTimeFormat("zh-CN", {
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
  return {
    dateLine: `${parts.year}年${parts.month}月${parts.day}日 · ${parts.weekday}`,
    clock: `${parts.hour}:${parts.minute} 北京时`,
    iso: d.toISOString(),
  }
}
