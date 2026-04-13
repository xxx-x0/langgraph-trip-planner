<template>
  <div id="app">
    <a-layout style="min-height: 100vh">
      <a-layout-header class="app-header">
        <div class="header-left">
          <router-link to="/" class="logo-link">
            🌍 HelloAgents智能旅行助手
          </router-link>
        </div>
        <div class="header-nav">
          <router-link to="/" class="nav-item" active-class="nav-active">
            ✨ 规划行程
          </router-link>
          <router-link to="/my-trips" class="nav-item" active-class="nav-active">
            🗺️ 我的行程
          </router-link>
        </div>
      </a-layout-header>
      <a-layout-content style="padding: 24px">
        <router-view />
      </a-layout-content>
      <a-layout-footer style="text-align: center">
        HelloAgents智能旅行助手 ©2025 基于HelloAgents框架
      </a-layout-footer>
    </a-layout>
  </div>
</template>

<script setup lang="ts">
</script>

<style>
#app {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
    'Noto Sans', sans-serif;
}

.app-header {
  background: #001529 !important;
  padding: 0 24px !important;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
}

.logo-link {
  color: #fff !important;
  font-size: 20px;
  font-weight: bold;
  text-decoration: none;
}

.header-nav {
  display: flex;
  gap: 8px;
}

.nav-item {
  color: rgba(255, 255, 255, 0.75) !important;
  text-decoration: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.3s ease;
}

.nav-item:hover {
  color: #fff !important;
  background: rgba(255, 255, 255, 0.1);
}

.nav-active {
  color: #fff !important;
  background: rgba(255, 255, 255, 0.15);
}
</style>

