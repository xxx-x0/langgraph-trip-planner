"""A dedicated local browser profile for Ctrip, never the user's Chrome profile."""
import asyncio
from pathlib import Path
from urllib.parse import urlencode

from ..config import get_settings
from .ticket_search import FLIGHT_CITIES, REPO, sample
from .ticket_assistant import ObservedTicket


class TicketBrowser:
    def __init__(self):
        self.driver = self.context = self.page = None
        self.job_id = None
        self.visible = False
        self.lock = asyncio.Lock()

    async def search(self, job, headed=False):
        async with self.lock:
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                return dict(status='failed', code='browser_not_installed', candidates=[],
                    message='机票后台浏览器尚未安装。请按项目“免扩展查票”说明安装浏览器运行组件；也可继续使用网站查询。')
            query = job.query
            if self.job_id != job.id or (headed and not self.visible) or not self.page or self.page.is_closed():
                await self._close_context()
                settings = get_settings()
                profile = Path(settings.ticket_browser_profile_dir).expanduser().resolve()
                profile.mkdir(parents=True, exist_ok=True, mode=0o700)
                profile.chmod(0o700)
                try:
                    if self.driver is None:
                        self.driver = await async_playwright().start()
                    self.context = await self.driver.chromium.launch_persistent_context(
                        str(profile), headless=not headed, channel=settings.ticket_browser_channel,
                        locale='zh-CN', timezone_id='Asia/Shanghai', viewport={'width': 1440, 'height': 1000},
                        timeout=15000)
                    self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                    self.job_id, self.visible = job.id, headed
                    job.browser_visible = headed
                    await self.context.add_init_script(path=str(REPO / 'browser-extension' / 'reader.js'))
                    frm, to = (FLIGHT_CITIES[p.removesuffix('市')] for p in (query.from_place, query.to_place))
                    url = f'https://flights.ctrip.com/online/list/oneway-{frm}-{to}?' + urlencode({
                        'depdate': str(query.date), 'cabin': 'y_s_c_f',
                        'adult': query.adult_passengers or 1, 'child': 0, 'infant': 0})
                    await self.page.goto(url, wait_until='domcontentloaded', timeout=20000)
                    self.url = url
                except asyncio.CancelledError:
                    await self._close_context()
                    raise
                except Exception:
                    await self._close_context()
                    return dict(status='failed', code='browser_unavailable', candidates=[],
                        message='本机查询浏览器未能启动或加载，请检查浏览器组件及网络。登录目录被其他进程占用时请先关闭对应查询窗口。')
            # Reuse only this job's dedicated page. Changed website conditions are
            # rejected by the shared DOM reader's date and city checks.
            q = dict(mode='flight', date=str(query.date), passengers=query.passengers)
            try:
                for _ in range(10):
                    observed = await self.page.evaluate('''({q,url}) => ({
                        candidates: globalThis.LtpTicketReader?.flights(document,q,url) || [],
                        empty: globalThis.LtpTicketReader?.empty(document,q,url) || false
                    })''', {'q': q, 'url': self.url})
                    if observed['empty']:
                        return dict(candidates=[], total_count=0, message='携程当前页面显示未找到符合条件的航班；可核对日期、城市或登录后重新查询。')
                    if observed['candidates']:
                        values = await self.page.evaluate('''async ({q,url}) =>
                            LtpTicketReader.collectFlights(document,q,url,window,
                                ms=>new Promise(resolve=>setTimeout(resolve,ms)))''', {'q': q, 'url': self.url})
                        candidates = [ObservedTicket.model_validate(c).model_dump() for c in values]
                        if candidates:
                            return dict(candidates=sample(candidates), total_count=len(candidates), sampled=len(candidates) >= 80,
                                message='已读取携程可识别的直达列表。列表参考起价、票种、税费及余票仍待出票前核对；最多带回80条，不能视为全站完整结果。')
                    await asyncio.sleep(1)
                if not self.visible:
                    await self._close_context()
                return dict(status='needs_action', code='website_action', candidates=[],
                    message='暂未读到与本次条件匹配的航班列表。请打开本机查询窗口，完成登录或验证、核对查询条件后点击“继续读取”；不能据此判断无票。')
            except asyncio.CancelledError:
                await self._close_context()
                raise
            except Exception:
                await self._close_context()
                return dict(status='failed', code='browser_read_failed', candidates=[],
                    message='本次航班读取中断或页面格式无法识别，请重新查询或使用网站导入；已保存行程未改变。')

    async def _close_context(self):
        context, self.context = self.context, None
        self.page, self.job_id, self.visible = None, None, False
        if context:
            try:
                await asyncio.wait_for(context.close(), 5)
            except Exception:
                pass

    async def close_job(self, key):
        async with self.lock:
            if self.job_id == key:
                await self._close_context()

    async def close(self):
        async with self.lock:
            await self._close_context()
            if self.driver:
                driver, self.driver = self.driver, None
                await driver.stop()
