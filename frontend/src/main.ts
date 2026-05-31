import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import './styles/design-tokens.css'
import './styles/dark-tokens.css'
import './styles/animations.css'
// 包豪斯设计系统样式
import './styles/bauhaus-tokens.css'
import './styles/bauhaus-components.css'
import './styles/bauhaus-antd-override.css'
import './styles/bauhaus-utilities.css'
import App from './App.vue'
import Home from './views/Home.vue'
import Result from './views/Result.vue'
import MyTrips from './views/MyTrips.vue'
import DiscoverView from './views/DiscoverView.vue'
import { gsap } from 'gsap'
import { Flip } from 'gsap/Flip'
import { SplitText } from 'gsap/SplitText'

// GSAP 插件应在 app 级注册一次
gsap.registerPlugin(Flip, SplitText)

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Home',
      component: Home
    },
    {
      path: '/result',
      name: 'Result',
      component: Result
    },
    {
      path: '/discover',
      name: 'Discover',
      component: DiscoverView
    },
    {
      path: '/my-trips',
      name: 'MyTrips',
      component: MyTrips
    },
    {
      path: '/trip/:id',
      name: 'trip-detail',
      component: Result,
      props: true
    },
    {
      path: '/draft/:id',
      name: 'Draft',
      component: () => import('@/views/DraftView.vue'),
      props: true,
    },
  ]
})

const app = createApp(App)

app.use(router)
app.use(Antd)

app.mount('#app')
