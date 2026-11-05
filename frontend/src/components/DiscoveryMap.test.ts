import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,expect,it,vi} from 'vitest'
import DiscoveryMap from './DiscoveryMap.vue'

const sdk=vi.hoisted(()=>({load:vi.fn()}))
vi.mock('@amap/amap-jsapi-loader',()=>({default:sdk}))
beforeEach(()=>vi.clearAllMocks())

it('does not create a map after leaving discovery while the SDK is loading',async()=>{
 let resolve!:(value:any)=>void
 sdk.load.mockReturnValue(new Promise(r=>resolve=r))
 const map=vi.fn()
 const w=mount(DiscoveryMap,{props:{attractions:[]}})
 await flushPromises();w.unmount();resolve({Map:map});await flushPromises()
 expect(map).not.toHaveBeenCalled()
})

it('mounts only the current container after a quick return to discovery',async()=>{
 let resolve!:(value:any)=>void
 sdk.load.mockReturnValue(new Promise(r=>resolve=r))
 const old=mount(DiscoveryMap,{props:{attractions:[]}});await flushPromises();old.unmount()
 const current=mount(DiscoveryMap,{props:{attractions:[]}});await flushPromises()
 const destroy=vi.fn(),map=vi.fn(function(_container:HTMLElement,_options:unknown){return {destroy}})
 resolve({Map:map,InfoWindow:vi.fn(function(){}),Pixel:vi.fn(function(){})});await flushPromises()
 expect(map).toHaveBeenCalledOnce()
 expect(map.mock.calls[0][0]).toBe(current.get('#discovery-map').element)
 current.unmount();expect(destroy).toHaveBeenCalledOnce()
})
