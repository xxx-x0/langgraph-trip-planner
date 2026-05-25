<template>
  <div id="app" :data-theme="resolvedTheme">
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
              <router-link to="/" class="nav-item" active-class="nav-active">
                <span class="nav-icon">✨</span>
                <span class="nav-label">规划行程</span>
              </router-link>
              <router-link to="/my-trips" class="nav-item" active-class="nav-active">
                <span class="nav-icon">🗺️</span>
                <span class="nav-label">我的行程</span>
              </router-link>
            </div>
            <button class="theme-toggle" @click="toggleTheme" :title="resolvedTheme === 'dark' ? '切换到亮色模式' : '切换到暗色模式'">
              <span v-if="resolvedTheme === 'dark'" class="theme-icon">☀️</span>
              <span v-else class="theme-icon">🌙</span>
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
        <span>Let's Go! 智能旅行助手 ©2025</span>
      </a-layout-footer>
    </a-layout>
  </div>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'

const { resolvedTheme, toggleTheme } = useTheme()
</script>

<style>
/* 全局包豪斯样式 */
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
.app-header {
  background: var(--white) !important;
  border-bottom: var(--border-main) solid var(--border);
  padding: 0 var(--space-6) !important;
  height: 64px;
  line-height: 64px;
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  box-shadow: var(--shadow-md);
}

.header-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
  max-width: 1400px;
  margin: 0 auto;
}

.header-left {
  display: flex;
  align-items: center;
}

.logo-link {
  display: flex;
  align-items: center;
  color: var(--foreground) !important;
  text-decoration: none;
  transition: opacity var(--transition-fast);
}

.logo-link:hover {
  opacity: 0.8;
}

.logo-text {
  font-size: var(--text-2xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--primary-red);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.header-nav {
  display: flex;
  gap: var(--space-2);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--foreground) !important;
  text-decoration: none;
  padding: 8px 20px;
  border: var(--border-2) solid var(--border);
  background: var(--white);
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  transition: all var(--transition-fast);
  box-shadow: 2px 2px 0px 0px var(--border);
}

.nav-item:hover {
  background: var(--primary-yellow);
  transform: translate(-1px, -1px);
  box-shadow: 3px 3px 0px 0px var(--border);
}

.nav-item:active {
  transform: translate(2px, 2px);
  box-shadow: none;
}

.nav-active {
  background: var(--primary-blue) !important;
  color: var(--white) !important;
}

.nav-icon {
  font-size: var(--text-base);
}

.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: var(--border-2) solid var(--border);
  background: var(--white);
  cursor: pointer;
  transition: all var(--transition-fast);
  box-shadow: 2px 2px 0px 0px var(--border);
}

.theme-toggle:hover {
  background: var(--primary-yellow);
  transform: translate(-1px, -1px);
  box-shadow: 3px 3px 0px 0px var(--border);
}

.theme-toggle:active {
  transform: translate(2px, 2px);
  box-shadow: none;
}

.theme-icon {
  font-size: var(--text-lg);
}

.app-footer {
  text-align: center;
  background: var(--foreground) !important;
  border-top: var(--border-main) solid var(--border);
  color: var(--white);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  padding: var(--space-6) var(--space-4) !important;
}

@media (max-width: 640px) {
  .app-header {
    padding: 0 var(--space-4) !important;
  }

  .header-right {
    gap: var(--space-2);
  }

  .nav-label {
    display: none;
  }

  .nav-item {
    padding: 8px 12px;
  }

  .logo-text {
    font-size: var(--text-lg);
  }

  .theme-toggle {
    width: 36px;
    height: 36px;
  }
}
</style>
