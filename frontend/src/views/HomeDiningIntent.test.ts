import { mount, flushPromises } from '@vue/test-utils'
import { expect,it,vi } from 'vitest'
import Antd,{DatePicker,Form} from 'ant-design-vue'
import dayjs from 'dayjs'
import Home from './Home.vue'
vi.mock('vue-router',()=>({useRouter:()=>({push:vi.fn()})}))
it('carries the explicit meal budget and dietary request through the discovery request',async()=>{
 sessionStorage.clear()
 const w=mount(Home,{global:{plugins:[Antd]}})
 const dates=w.findAllComponents(DatePicker)
 dates[0].vm.$emit('update:value',dayjs('2026-10-30'));dates[1].vm.$emit('update:value',dayjs('2026-11-01'));await flushPromises()
 await w.find('input[aria-label="每人每餐预算"]').setValue('50')
 await w.find('input[aria-label="饮食要求"]').setValue('花生过敏')
 w.findComponent(Form).vm.$emit('finish');await flushPromises()
 expect(JSON.parse(sessionStorage.getItem('tripFormData')!)).toMatchObject({meal_budget_per_person:50,dietary_requirements:'花生过敏',dining_style:'on_route'})
 w.unmount()
})
