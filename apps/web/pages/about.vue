<template>
  <AppShell title="关于">
    <div class="about-grid">
      <section class="prose">
        <h1>天气与智能，被认真地看一眼</h1>
        <p>
          AetherWatch 是一座本地可运行的观测台：一边用公开数值预报对照 GFS、IFS、AIFS 等模式，
          一边让管理员把客户的 NetCDF 场文件送进同一套目录与地图。地球页用 WebGL / MapLibre 球体
          加上粒子风场；预报页用暖纸页来对照空间场和时间序列；资讯页用 Markdown 写科学笔记。
        </p>
        <h2>数据平面</h2>
        <p>
          <strong>预览（无需上传）</strong>走 Open-Meteo 免费预报 API（非商业、无需密钥）：点上序列是真实网络请求；
          中国范围的空间场是对 Open-Meteo 的粗网格采样并在浏览器里上采样着色。10 米风场同样来自 Open-Meteo，
          编码成 u/v 网格驱动地球页粒子。
        </p>
        <p>
          <strong>客户 NetCDF</strong>由管理页上传 <code>.nc</code> / <code>.nc4</code>，写入 MinIO，
          再经 Taskiq 演员链处理：<code>NcIngestActor</code> 解析变量与维，<code>NcTileActor</code>
          抽出一张二维切片给地图。预报页会把就绪的数据集和预览模式放在同一组芯片里。
        </p>
        <h2>v1 明确不做的事</h2>
        <p>
          完整 NOAA GFS GRIB 全球摄取（cfgrib + 数 GB 的 NOMADS 卷）没有进这条 MVP。
          需要业务级全球 GRIB 时，把文件丢进 MinIO 的 <code>raw/</code> 前缀并扩展
          <code>ForecastIngestActor</code> 即可，接口形状已经按目录/场/比较留好。
        </p>
        <h2>品牌</h2>
        <p>产品名只有 AetherWatch。不要把它叫成任何其他观测站的名字。</p>
      </section>
      <aside class="side-meta">
        <div style="font-family: Fraunces, serif; color: var(--accent)">栈</div>
        <dl>
          <dt>Web</dt>
          <dd>Nuxt 3 · TypeScript · MapLibre GL</dd>
          <dt>API</dt>
          <dd>FastAPI · Python 3.12 · xarray</dd>
          <dt>Actors</dt>
          <dd>Taskiq · Redis</dd>
          <dt>Store</dt>
          <dd>Postgres 16 · MinIO · Redis 7</dd>
          <dt>Edge</dt>
          <dd>Caddy · Docker Compose</dd>
        </dl>
      </aside>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
useHead({ title: "关于 · AetherWatch" })
</script>
