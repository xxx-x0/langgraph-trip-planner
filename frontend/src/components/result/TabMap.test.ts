import {mount,flushPromises} from '@vue/test-utils'
import {it,expect,vi,afterEach} from 'vitest'
import TabMap from './TabMap.vue'
const io=vi.hoisted(()=>({load:vi.fn()}))
vi.mock('@amap/amap-jsapi-loader',()=>({default:{load:io.load}}))
const props={tripPlan:{days:[]} as any,attractionPhotos:{},visible:true}
afterEach(()=>{vi.useRealTimers();vi.resetAllMocks()})
it('shows failed map availability honestly and retries on reopening',async()=>{
 io.load.mockRejectedValueOnce(new Error('offline'))
 const w=mount(TabMap,{props});await flushPromises()
 expect(w.get('[role=status]').text()).toContain('地图未加载')
 const resize=vi.fn(),destroy=vi.fn();const Map=vi.fn(function(this:any){this.add=vi.fn();this.resize=resize;this.destroy=destroy})
 io.load.mockResolvedValue({Map})
 await w.setProps({visible:false});await w.setProps({visible:true});await flushPromises()
 expect(io.load).toHaveBeenCalledTimes(2);expect(w.find('[role=status]').exists()).toBe(false)
 await (w.vm as any).prepareForExport();expect(resize).toHaveBeenCalled();w.unmount();expect(destroy).toHaveBeenCalledTimes(1)
})
it('bounds export waiting and rejects a late map constructor after unmount',async()=>{
 vi.useFakeTimers();let complete:any;io.load.mockReturnValue(new Promise(r=>complete=r))
 const w=mount(TabMap,{props});await flushPromises()
 const ready=(w.vm as any).prepareForExport();await vi.advanceTimersByTimeAsync(8000);await ready
 expect(w.get('[role=status]').text()).toContain('本次导出不包含完整地图')
 expect(io.load).toHaveBeenCalledTimes(1)
 w.unmount();const Map=vi.fn();complete({Map});await flushPromises();expect(Map).not.toHaveBeenCalled()
})
