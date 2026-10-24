<template>
  <a-config-provider :theme="componentTheme" :locale="zhCN">
    <div id="app" :data-theme="resolvedTheme" class="travel-shell">
      <a-layout style="min-height: 100vh; background: var(--color-bg-primary)">
        <a-layout-header class="app-header">
          <div class="header-inner">
            <div class="header-left">
              <router-link to="/" class="logo-link">
                <span class="logo-text">Let's Go!</span>
              </router-link>
            </div>
            <div class="header-right">
              <div class="header-nav">
                <router-link to="/" aria-label="规划行程" class="nav-item" :class="{ 'nav-active': activeWorkspace === 'plan' }" :aria-current="activeWorkspace === 'plan' ? 'page' : undefined">
                  <span class="nav-icon">＋</span>
                  <span class="nav-label">规划行程</span>
                </router-link>
                <router-link to="/multi-trip" aria-label="多日旅行" class="nav-item" :class="{ 'nav-active': activeWorkspace === 'multi' }" :aria-current="activeWorkspace === 'multi' ? 'page' : undefined"><span class="nav-icon" aria-hidden="true">⌁</span><span class="nav-label">多日旅行</span></router-link>
                <router-link to="/my-trips" aria-label="我的行程" class="nav-item" :class="{ 'nav-active': activeWorkspace === 'saved' }" :aria-current="activeWorkspace === 'saved' ? 'page' : undefined">
                  <span class="nav-icon">▤</span>
                  <span class="nav-label">我的行程</span>
                </router-link>
              </div>
              <button :aria-label="resolvedTheme === 'dark' ? '切换到亮色模式' : '切换到暗色模式'" class="theme-toggle" @click="toggleTheme" :title="resolvedTheme === 'dark' ? '切换到亮色模式' : '切换到暗色模式'">
                <span v-if="resolvedTheme === 'dark'" class="theme-icon">☼</span>
                <span v-else class="theme-icon">◐</span>
              </button>
            </div>
          </div>
        </a-layout-header>
        <a-layout-content style="padding: 0">
          <router-view v-slot="{ Component }">
            <transition name="page" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </a-layout-content>
        <a-layout-footer class="app-footer">
          <span>Let’s Go! · 好的旅行，从容发生。</span>
        </a-layout-footer>
      </a-layout>
      <BauhausLoader />
    </div>
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { theme as antdTheme } from 'ant-design-vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import { useTheme } from '@/composables/useTheme'
import BauhausLoader from '@/components/loader/BauhausLoader.vue'

const { resolvedTheme, toggleTheme } = useTheme()
const route = useRoute()
const activeWorkspace = computed(() => {
  if (route.path.startsWith('/multi-trip') || route.query.multi) return 'multi'
  if (route.path === '/my-trips' || route.path.startsWith('/trip/') || route.path === '/result') return 'saved'
  return 'plan'
})
const componentTheme = computed(() => ({
  algorithm: resolvedTheme.value === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
  token: {
    colorPrimary: resolvedTheme.value === 'dark' ? '#e8ba88' : '#8c552e',
    colorBgBase: resolvedTheme.value === 'dark' ? '#191c1f' : '#faf9f6',
    colorTextBase: resolvedTheme.value === 'dark' ? '#f0efeb' : '#292b2d',
    borderRadius: 10, fontSize: 14,
  },
}))
</script>

<style>
/* Shared application base */
body {
  font-family: var(--font-family);
  color: var(--foreground);
  background: var(--background);
  margin: 0;
  padding: 0;
}

* {
  box-sizing: border-box;
}

#app {
  min-height: 100vh;
}
</style>

<style scoped>
.app-header{position:sticky;top:0;z-index:200;height:64px;line-height:1.5;padding:0 24px!important;background:var(--desk-glass)!important;backdrop-filter:blur(20px);border-bottom:1px solid var(--color-border)}
.header-inner{max-width:1240px;height:100%;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:20px}
.header-right,.header-nav{display:flex;align-items:center;gap:8px}.header-right{gap:18px}
.logo-link{text-decoration:none}.logo-text{font-size:22px;font-weight:600;letter-spacing:-.04em;color:var(--color-text-primary)}
.nav-item{display:flex;align-items:center;gap:8px;padding:10px 16px;color:var(--color-text-secondary);border-radius:10px;font-size:12px;transition:background .2s,color .2s;text-decoration:none}.nav-icon{display:none}
.nav-item:hover{background:var(--color-bg-tertiary);color:var(--color-text-primary)}.nav-active{background:var(--color-primary-bg);color:var(--color-primary);font-weight:600}
.theme-toggle{display:grid;place-items:center;width:34px;height:34px;flex-shrink:0;border:1px solid var(--color-border);border-radius:50%;background:transparent;color:var(--color-text-secondary);cursor:pointer;transition:background .2s}.theme-toggle:hover{background:var(--color-bg-tertiary)}.theme-icon{font-size:18px}
.app-footer{text-align:center;background:var(--desk-bg)!important;border-top:1px solid var(--color-border);color:var(--color-text-secondary);font-size:11px;padding:28px 16px!important;letter-spacing:.08em}
@media(max-width:640px){.app-header{padding:0 14px!important}.header-inner{gap:10px}.header-right{gap:6px}.header-nav{gap:2px}.nav-item{padding:9px 7px;font-size:11px}.logo-text{font-size:19px}.theme-toggle{width:30px;height:30px}}
@media(max-width:360px){.app-header{padding:0 10px!important}.header-inner{gap:6px}.header-right{gap:4px}.logo-text{font-size:16px;white-space:nowrap}.nav-item{padding:9px 5px;white-space:nowrap}}
</style>
