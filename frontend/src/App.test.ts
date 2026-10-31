import {mount} from '@vue/test-utils'
import {reactive,nextTick} from 'vue'
import {it,expect,vi} from 'vitest'
import App from './App.vue'
const state=vi.hoisted(()=>({route:null as any}))
vi.mock('@/services/quality',()=>({qualityGet:vi.fn().mockResolvedValue({data:{enabled:false}})}))
vi.mock('vue-router',()=>({useRoute:()=>state.route}))
it('keeps the active workspace tied to saved and multicity editor routes and switches component themes',async()=>{
 state.route=reactive({path:'/draft/one',query:{multi:'mc_a'}})
 const w=mount(App,{global:{stubs:{BauhausLoader:true,AConfigProvider:{name:'AConfigProvider',props:['theme','locale'],template:'<div><slot /></div>'},ALayout:{template:'<div><slot /></div>'},ALayoutHeader:{template:'<header><slot /></header>'},ALayoutContent:{template:'<main><slot /></main>'},ALayoutFooter:{template:'<footer><slot /></footer>'},RouterLink:{props:['to'],template:'<a><slot /></a>'},RouterView:{template:'<div />'}}}})
 expect(w.get('[aria-current="page"]').text()).toContain('多日旅行')
 state.route.query={};state.route.path='/trip/12';await nextTick()
 expect(w.get('[aria-current="page"]').text()).toContain('我的行程')
 const before=w.findComponent({name:'AConfigProvider'}).props('theme').token.colorPrimary
 await w.get('.theme-toggle').trigger('click')
 expect(w.findComponent({name:'AConfigProvider'}).props('theme').token.colorPrimary).not.toBe(before)
 expect(w.get('.theme-toggle').attributes('aria-label')).toContain('切换到');w.unmount()
})
