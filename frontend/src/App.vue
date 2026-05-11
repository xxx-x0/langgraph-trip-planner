<template>
  <div id="app" :data-theme="resolvedTheme">
    <a-layout style="min-height: 100vh; background: var(--color-bg-primary)">
      <a-layout-header class="app-header">
        <div class="header-inner">
          <div class="header-left">
            <router-link to="/" class="logo-link">
              <svg class="logo-icon" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="2"/>
                <path d="M8 18C8 18 10 14 16 14C22 14 24 18 24 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                <path d="M10 20C10 20 12 17 16 17C20 17 22 20 22 20" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <circle cx="16" cy="11" r="2" fill="currentColor"/>
              </svg>
              <span class="logo-text">HelloAgents</span>
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
        <span>HelloAgents智能旅行助手 ©2025 基于HelloAgents框架</span>
      </a-layout-footer>
    </a-layout>
  </div>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'

const { resolvedTheme, toggleTheme } = useTheme()
</script>

<style>
#app {
  font-family: var(--font-family);
  color: var(--color-text-primary);
  background: var(--color-bg-primary);
  transition: background var(--transition-normal), color var(--transition-normal);
}
</style>

<style scoped>
.app-header {
  background: rgba(255, 255, 255, 0.8) !important;
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--color-border);
  padding: 0 var(--space-6) !important;
  height: var(--header-height);
  line-height: var(--header-height);
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  transition: background var(--transition-normal), border-color var(--transition-normal);
}

[data-theme="dark"] .app-header {
  background: rgba(18, 18, 24, 0.85) !important;
}

.header-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
  max-width: var(--content-max-width);
  margin: 0 auto;
}

.header-left {
  display: flex;
  align-items: center;
}

.logo-link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-primary) !important;
  text-decoration: none;
  transition: opacity var(--transition-fast);
}

.logo-link:hover {
  opacity: 0.85;
}

.logo-icon {
  width: 28px;
  height: 28px;
  color: var(--color-primary);
}

.logo-text {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  letter-spacing: -0.02em;
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.header-nav {
  display: flex;
  gap: var(--space-1);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-text-secondary) !important;
  text-decoration: none;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  transition: all var(--transition-fast);
}

.nav-item:hover {
  color: var(--color-text-primary) !important;
  background: var(--color-primary-bg);
}

.nav-active {
  color: var(--color-primary) !important;
  background: var(--color-primary-bg);
  font-weight: var(--font-weight-semibold);
}

.nav-icon {
  font-size: var(--font-size-base);
}

.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-elevated);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.theme-toggle:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
  transform: scale(1.05);
}

.theme-toggle:active {
  transform: scale(0.95);
}

.theme-icon {
  font-size: var(--font-size-lg);
}

.app-footer {
  text-align: center;
  background: var(--color-bg-secondary) !important;
  border-top: 1px solid var(--color-border);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
  padding: var(--space-6) var(--space-4) !important;
  transition: background var(--transition-normal), border-color var(--transition-normal);
}

@media (max-width: 768px) {
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
    padding: var(--space-2);
  }

  .logo-text {
    font-size: var(--font-size-lg);
  }
}
</style>
