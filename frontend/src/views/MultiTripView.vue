<template>
  <main class="multi-page">
    <header v-if="!id || document" class="trip-hero">
      <div class="hero-copy">
        <nav class="breadcrumbs" aria-label="当前位置"><router-link to="/">规划行程</router-link><span>/</span><router-link to="/multi-trip">多城市旅行</router-link></nav>
        <p class="eyebrow">YOUR NEXT CHAPTER / 旅行工作台</p>
        <h1>{{ document ? document.plan.title : '下一站，由你决定。' }}</h1>
        <p class="hero-description">{{ document ? '城市、日程与每一段路，在这里自然衔接。' : '挑几座喜欢的城市，把沿途的日子慢慢展开。' }}</p>
        <div class="hero-meta"><span><b>{{ tripDays }}</b> 天旅程</span><span><b>{{ plan.stops.length }}</b> 座城市</span><span><b>{{ plan.companions.count }}</b> 人同行</span></div>
        <div class="hero-dates">{{ plan.start_date.replaceAll('-','.') }} <span>—</span> {{ plan.end_date.replaceAll('-','.') }}</div>
      </div>
      <JourneyCover :stops="plan.stops" :origin="plan.origin.name" :destination="plan.destination.name" :days="tripDays" :interactive="!!document" :selected="overviewCity || plan.stops[0]?.id" :photos="cityPhotos" @select="openCityChapter" @transport="openTransport" />
    </header>
    <h1 v-else>{{busy?'正在读取旅行…':'暂时无法显示这趟旅行'}}</h1>
    <p v-if="error" ref="errorPanel" tabindex="-1" role="alert" class="error">{{error}} <button v-if="loadFailed" @click="load">重新读取已保存内容</button><button v-else-if="document" @click="reloadSaved">重新读取已保存内容</button><span v-else>输入已保留，修改后可以重试。</span></p>
    <p v-if="message" role="status" class="success-note">{{message}}</p>
    <p v-if="busy" role="status" class="loading-note">正在处理，请稍候…</p>
    <details v-if="!id && records.length" class="card recent-trips"><summary>继续上次的旅行 <span class="badge">{{records.length}}</span></summary><div class="record-grid"><router-link v-for="r in records" :key="r.id" :to="`/multi-trip/${r.id}`" class="record-card"><span class="badge">{{r.status==='saved'?'已保存':'草稿'}}</span><strong>{{r.title}}</strong><span>{{r.cities.join(' → ')}}</span><small>{{r.start_date}} · 继续查看 →</small></router-link></div></details>
    <template v-if="!id || document">
    <div v-if="document" class="version-line"><span class="status-dot" :class="{unsaved:dirty}"></span><span>{{readonly?'已保存版本 · 只读':dirty?'有未保存的修改':'草稿已保存'}} · 版本 {{document.revision}}</span><router-link v-if="document.source_id" :to="`/multi-trip/${document.source_id}`">查看原版本</router-link><router-link v-if="readonly" :to="{ path: '/travel-records/new', query: { source_kind: 'multi', source_id: document.id } }">记录这次旅行</router-link><button v-if="readonly" :disabled="busy" @click="copyVersion">复制为新版本继续修改</button></div>
    <nav v-if="document" ref="workspaceNav" class="workspace-nav" :style="{'--workspace-index':tabs.findIndex(tab=>tab.id===activeSection)}" aria-label="旅行工作区">
      <button v-for="tab in tabs" :key="tab.id" :aria-current="activeSection===tab.id?'page':undefined" :class="{active:activeSection===tab.id}" @click="activeSection=tab.id"><span class="nav-number">{{tab.number}}</span>{{tab.label}}<span v-if="tab.id==='review' && summary?.missing.length" class="tab-count">{{summary.missing.length}}</span></button>
    </nav>
    <section v-if="preview" class="card preview" ref="previewPanel" tabindex="-1" aria-label="变更预览"><h2>确认后，这些地方会一起更新</h2><p v-if="plan.title!==document.plan.title" class="title-change">旅行名称：{{document.plan.title}} → {{plan.title}}</p><div v-if="pendingTicket" class="ticket-confirmation"><strong>本次选择：{{pendingTicket.service_number || '班次待定'}}</strong><p>{{pendingTicket.departure_station}} {{pendingTicket.departure_time.replace('T',' ')}} → {{pendingTicket.arrival_station}} {{pendingTicket.arrival_time.replace('T',' ')}}</p><p>全体票价 {{pendingTicket.ticket_total??'待确认'}} {{pendingTicket.currency}}。{{pendingTicket.price_note}}</p></div><p v-for="c in preview.changes" :key="c">{{c}}</p><p>已知预算变化：{{preview.budget_delta>=0?'+':''}}{{preview.budget_delta}} 元。费用缺失或旧报价失效时，减少不等于省钱。</p><div class="preview-city-grid"><details v-for="city in preview.summary.cities" :key="city.id" :open="!!pendingTicket && previewDays(city).length>0"><summary>{{city.city}} · {{city.nights}} 晚 <span class="summary-hint">查看每日时段与影响</span></summary><p v-for="w in city.windows" :key="w.date">{{w.date}}：{{windowText(w)}} {{w.provisional?"（交通未齐，暂定）":""}}</p><p v-for="r in city.windows.flatMap((w:any)=>w.rest_periods||[])" :key="r.id">休息：{{r.date}} {{r.start_time}}—{{r.end_time}} {{r.label}}</p><p v-for="impact in (city.impacts || []).filter((impact:any)=>impact.changes?.length)" :key="impact.date">{{impact.date}} {{impact.changes.join('；')}}</p><div v-if="pendingTicket"><div v-for="day in previewDays(city)" :key="day.date"><h4>{{day.date}} 确认后的时间安排</h4><ol><li v-for="(item,i) in day.timeline_schedule" :key="i">{{item.start_time}}—{{item.end_time}} · {{item.ref_name}}</li></ol><p v-if="!day.timeline_schedule?.length">当天留给在途和抵达休整，请核对住宿及用餐。</p></div></div><p v-if="city.stale">旧每日安排保留，但日期或人数已变，需重新规划。</p></details></div><div v-if="preview.summary.conflicts.length" class="preview-conflicts" role="alert"><strong>{{preview.summary.conflicts.length}} 处时间冲突需要处理</strong><p>当前班次无法容纳以下安排。可以先保留为草稿，再调整班次或每日安排；冲突解决前不能保存为旅行版本。</p><ul><li v-for="c in preview.summary.conflicts" :key="c">{{c}}</li></ul></div><section v-if="preview.adjustments?.length" class="adjustment-review"><h3>按交通重新安排当天</h3><ul><li v-for="change in preview.adjustments" :key="change">{{change}}</li></ul><p>减少项目带来的费用下降不等于省钱；未安排的餐次仍需在另一城或途中解决。两侧改动的路线已重新查询，站场接驳仍为预留估计。</p><label><input type="checkbox" v-model="acknowledgeAdjustments" />我已核对上述调整和取消项，同意同步更新两城当天安排</label></section><label v-if="preview.booked.length"><input type="checkbox" v-model="acknowledge" />我已核对 {{preview.booked.join('、')}}；这里只修改本地计划，未进行改签或退订</label><button class="primary" :disabled="busy || (preview.booked.length>0&&!acknowledge) || (!!preview.adjustment_id&&!acknowledgeAdjustments)" @click="saveChanges">{{preview.summary.conflicts.length?'保留为草稿，稍后处理冲突':'确认影响并保存草稿'}}</button> <button :disabled="busy" @click="discardChanges">撤销本次未保存修改</button></section>
    <section v-if="document && summary" v-show="activeSection==='overview'" class="overview-panel">
      <div class="section-heading overview-heading"><div><p class="eyebrow">YOUR DAYS / 日程</p><h2>你的每日旅程</h2></div><button @click="activeSection='cities'">{{readonly?'查看城市设置':'调整城市与日期'}} ↗</button></div>
      <p v-if="dirty" class="notice">这里展示上次保存的安排。请先预览并保存修改，再编辑每日行程。</p>

      <MultiTripItinerary :cities="summary.cities" :transfers="overviewTransfers" :focus-city="overviewCity || String(route.query.city||'')" :focus-date="String(route.query.date||'')" :readonly="readonly" :disabled="busy||dirty||manualLegDirty" @plan="launchCity($event,false)" @edit="launchCity($event,true)" @edit-day="launchCity($event.id,true,$event.date)" @transport="openDayTransport" @city-change="overviewCity=$event" />
      <div class="overview-stats"><button @click="activeSection='transport'"><small>城际交通</small><strong>{{filledTransfers}} / {{itineraryEdges.length}} <span>段已填写</span></strong><span>查看班次与接驳 →</span></button><button @click="activeSection='review'"><small>已知费用</small><strong>¥{{money(summary.budget.total)}}</strong><span>{{summary.budget.complete?'查看费用明细':'仍有费用待确认'}} →</span></button><button @click="activeSection='review'"><small>出发前待办</small><strong>{{summary.missing.length}} <span>项待核对</span></strong><span>{{summary.conflicts.length?summary.conflicts.length+' 项冲突需处理':'查看住宿与费用缺项'}} →</span></button></div>
    </section>
    <div v-show="!document || activeSection==='cities'" class="cities-panel">
    <div class="section-heading"><div><p class="eyebrow">BUILD YOUR JOURNEY</p><h2>{{document?'城市与停留':'从一条喜欢的路线开始'}}</h2></div><span class="section-note">5～10 天 · 2～3 座城市</span></div>
    <div v-if="inputIssues.length" ref="validationPanel" tabindex="-1" class="notice input-issues" role="status"><strong>先核对这 {{inputIssues.length}} 处，再继续</strong><ul><li v-for="issue in inputIssues" :key="issue.field+issue.message">{{issue.message}} <button @click="focusField(issue.field)">定位修改</button></li></ul></div>
    <fieldset class="card trip-settings" :disabled="readonly || busy"><legend>这次旅行的基本信息</legend>
      <div class="trip-composer"><div><small>这次，想怎样出发？</small><h3>{{plan.origin.name}} <span>出发，去</span> {{plan.stops.map((s:any)=>s.city.name).join(' · ')}}</h3><p>{{plan.start_date}} — {{plan.end_date}} · {{tripDays}} 天</p></div><div class="companion-stepper"><span>一起出发</span><button aria-label="减少同行人数" :disabled="plan.companions.count<=1" @click="plan.companions.count--">−</button><output>{{plan.companions.count}} <small>人</small></output><button aria-label="增加同行人数" :disabled="plan.companions.count>=20" @click="plan.companions.count++">＋</button></div></div>
      <div class="pace-choices" aria-label="选择旅行节奏"><button v-for="p in paceChoices" :key="p.value" :aria-pressed="plan.pace===p.value" :class="{selected:plan.pace===p.value}" @click="plan.pace=p.value"><span>{{p.icon}}</span><strong>{{p.name}}</strong><small>{{p.note}}</small></button></div>
      <details class="essential-settings"><summary>修改名称、日期与预算 <span class="summary-hint">{{plan.title}} · {{plan.budget ? '预算 ¥'+plan.budget : '预算待定'}}</span></summary><div class="fields">
        <label>旅行名称<input id="trip-title" v-model="plan.title" maxlength="120" /></label>
        <label>开始日期<input id="trip-start" type="date" v-model="plan.start_date" /></label><label>结束日期<input id="trip-end" type="date" :min="plan.start_date" v-model="plan.end_date" /></label>
        <label>出发城市<input v-model="plan.origin.name" /></label><label>返家城市<input v-model="plan.destination.name" /></label>
        <label>同行人数<input type="number" min="1" max="20" v-model.number="plan.companions.count" /></label>
        <label>总预算（元，未知留空）<input type="number" min="1" :value="plan.budget??''" @input="plan.budget=numberOrNull($event)" /></label>
        <label>旅行节奏<select v-model="plan.pace"><option value="slow">慢慢逛</option><option value="balanced">游玩与休息兼顾</option><option value="active">多些体验</option></select></label>
        <label>每人每餐预算<input type="number" :value="plan.meal_budget_per_person??''" @input="plan.meal_budget_per_person=numberOrNull($event)" /></label>
        <label>饮食要求<input v-model="plan.dietary_requirements" maxlength="300" /></label>
      </div></details>
      <details class="preference-details"><summary>房间与同行儿童 <span class="summary-hint">按需设置</span></summary><p>住宿查询默认按同行人数安排一间成人房；带儿童或多间房请填写准确条件。</p>
      <label><input type="checkbox" :checked="!!plan.hotel_occupancy" @change="toggleOccupancy" />指定房间与儿童年龄</label>
      <div v-if="plan.hotel_occupancy" class="fields"><label>房间数<input type="number" min="1" v-model.number="plan.hotel_occupancy.room_count" /></label><label>每房成人数<input type="number" min="1" v-model.number="plan.hotel_occupancy.adults_per_room" /></label><label>每房儿童年龄（逗号分隔）<input :value="plan.hotel_occupancy.children_ages.join(',')" @change="setAges" /></label></div>
      </details><div class="section-heading city-section-heading"><div><h3>沿途想停留的城市</h3><p>同日换城可共用一天，退房当天不多算一晚。</p></div><button @click="suggestRest">帮我留出休息时段</button></div>

      <p v-if="localNote" role="status" class="notice">{{localNote}}</p>
      <div class="stay-allocation" aria-label="城市停留分配"><div class="stay-track"><button v-for="(s,i) in plan.stops" :key="s.id" :style="{flex:Math.max(1,nights(s.start_date,s.end_date))}" :aria-pressed="editingCity===s.id" @click="editingCity=s.id"><span>0{{i+1}} / {{s.city.name}}</span><strong>{{nights(s.start_date,s.end_date)}} <small>晚</small></strong></button></div><div v-for="(s,i) in plan.stops.slice(0,-1)" :key="s.id" class="boundary-control"><label :for="'boundary-'+s.id">{{s.city.name}} → {{plan.stops[i+1].city.name}}<strong>{{s.end_date}} 换城</strong></label><input :id="'boundary-'+s.id" type="range" :min="1" :max="Math.max(1,nights(s.start_date,plan.stops[i+1].end_date)-1)" :value="nights(s.start_date,s.end_date)" :disabled="nights(s.start_date,plan.stops[i+1].end_date)<2" @input="setBoundary(i,Number(($event.target as HTMLInputElement).value))" /><small>拖动或使用方向键分配停留。改动后会核对现有住宿、车票和日程。</small></div></div>
      <article v-for="(stop,i) in plan.stops" :key="stop.id" class="city-editor">
        <div class="city-card-heading"><span class="stop-number">0{{i+1}}</span><div><h3>{{stop.city.name || '选择一座城市'}}</h3><span>第 {{i+1}} 站 · 计划 {{nights(stop.start_date,stop.end_date)}} 晚</span></div><button :aria-expanded="editingCity===stop.id" @click="editingCity=editingCity===stop.id?'':stop.id">{{editingCity===stop.id?'收起设置':'编辑这一站'}} {{editingCity===stop.id?'−':'＋'}}</button></div><div v-show="editingCity===stop.id || readonly" class="city-edit-body"><div class="fields">
          <label>城市名称<input :id="`city-name-${stop.id}`" v-model="stop.city.name" maxlength="80" /></label><label>抵达日期<input :id="`city-start-${stop.id}`" type="date" :min="plan.start_date" :max="plan.end_date" v-model="stop.start_date" /></label><label>离开日期<input :id="`city-end-${stop.id}`" type="date" :min="stop.start_date" :max="plan.end_date" v-model="stop.end_date" /></label>
          <label><input type="checkbox" v-model="stop.must_visit" />这次一定要去</label>
        </div>
        <button :disabled="i===0" @click="move(i,-1)">向前一站</button> <button :disabled="i===plan.stops.length-1" @click="move(i,1)">向后一站</button> <button :disabled="plan.stops.length<=2 || stop.must_visit" @click="removeCity(i)">减少这一城</button>
        <details class="rest-editor" :id="`rest-${stop.id}`" :open="openRest.includes(stop.id)" @toggle="toggleRest(stop.id, $event)"><summary>留一点时间休息 <span class="summary-hint">{{stop.rest_periods?.length || 0}} 段已安排</span></summary><p>在当时所在区域休息，地点自行确认；如需回酒店，请调整路线。修改后先预览，再保存整趟旅行。</p>
          <div v-for="(r,j) in stop.rest_periods" :key="r.id" class="fields"><label>休息日期<input type="date" v-model="r.date" :min="stop.start_date" :max="stop.end_date" /></label><label>休息开始<input type="time" v-model="r.start_time" /></label><label>休息结束<input type="time" v-model="r.end_time" /></label><label>想怎么休息<input v-model="r.label" maxlength="80" /></label><button @click="stop.rest_periods.splice(j,1)">移除这段休息</button></div>
          <button @click="addRest(stop)">添加休息时段</button>
        </details>
        <details><summary>安排 {{stop.city.name}} 的住宿</summary><p>可先填自己查到的住宿；不填写时，预算使用后续每日安排的酒店报价。有手动住宿区间时，以这些区间为准，不重复加每日酒店。</p>
          <section v-for="(h,j) in stop.lodgings" :key="h.id" class="lodging"><div class="fields">
            <label>酒店名称<input v-model="h.name" /></label><label>入住日期<input type="date" v-model="h.check_in" /></label><label>退房日期<input type="date" v-model="h.check_out" /></label>
            <label>房间数<input type="number" min="1" v-model.number="h.rooms" /></label><label>住宿金额<input type="number" min="0" step="0.01" :value="h.amount??''" @input="h.amount=numberOrNull($event)" /></label>
            <label>金额口径<select v-model="h.basis"><option value="stay_total">整个区间、全部房间总额</option><option value="room_night">每房每晚同价</option></select></label><label>币种<input v-model="h.currency" maxlength="3" /></label>
            <label>价格来源<select v-model="h.source"><option value="unknown">未知</option><option value="user_estimate">自己估算</option><option value="user_quote">记录报价</option><option value="paid">已支付</option></select></label>
            <label>来源说明<input v-model="h.source_note" maxlength="300" /></label><label>记录时间<input type="datetime-local" v-model="h.recorded_at" /></label>
            <label>税费<select v-model="h.taxes_included"><option :value="null">待确认</option><option :value="true">已包含</option><option :value="false">未包含</option></select></label><label><input type="checkbox" v-model="h.booked" />已订住宿，保留约束</label>
          </div><button @click="stop.lodgings.splice(j,1)">移除这段住宿</button></section>
          <button @click="addHotel(stop)">添加住宿区间</button>
        </details>
      </div></article>
      <button class="add-city" :disabled="plan.stops.length>=3" @click="addCity">再去一座城市</button>
      <div class="actions"><button @click="compare">比较城市级方案</button><button class="primary" v-if="!id" @click="create">建立这趟旅行</button><button class="primary" v-else @click="previewChanges">查看整趟变更影响</button></div>
    </fieldset>
    <section v-if="options.length" class="card"><h2>先比较怎么走</h2><p>这些是日期和节奏的备选，不是已核实的低价或最快路线。选择后仍需查票和住宿。</p><div class="options"><article v-for="o in options" :key="o.name"><h3>{{o.name}}</h3><p>{{o.reason}}</p><p>{{o.plan.stops.map((s:any)=>s.city.name+' '+nights(s.start_date,s.end_date)+'晚').join(' → ')}}</p><p>换城 {{o.summary.hotel_changes}} 次 · 门到门 {{duration(o.summary.door_minutes)}} · 已知费用 ¥{{o.summary.budget.total}}</p><p>可安排时间合计：{{duration(o.summary.usable_minutes)}}；每次换城都要重新收拾行李。</p><p>{{o.summary.missing.length}} 项待确认</p><p v-if="o.blocked.length">涉及已订安排：{{o.blocked.join('；')}}，请在原方案逐项修改并确认。</p><button :disabled="readonly || busy || o.blocked.length>0" @click="choose(o)">采用这组城市日期，继续核对</button></article></div></section>
    </div>
    <section v-if="document && !readonly" v-show="activeSection==='transport'" class="card transport-panel"><p class="eyebrow">ON THE ROAD</p><h2>把每一段交通接起来</h2><p>先保存城市和日期，再查各段交通。浏览器候选可直接采用并预览，文字导入也可加入备选；查看整趟影响后确认保存。</p>
      <div class="edge-picker" aria-label="选择交通段"><button v-for="(e,i) in itineraryEdges" :key="e.from+e.to" :class="{active:edgeIndex===i}" :aria-pressed="edgeIndex===i" @click="selectTransport(i)"><small>第 {{i+1}} 段 · {{e.date}}</small><strong>{{e.fromName}} → {{e.toName}}</strong><span>{{edgeLeg(e)?.service_number || '待选班次'}}</span></button></div><p v-if="dirty" class="notice">有未保存修改，请先查看整趟变更影响并确认保存，再查票。</p>
      <label class="sr-only">本次查哪一段<select :value="edgeIndex" @change="selectTransport(Number(($event.target as HTMLSelectElement).value))"><option v-for="(e,i) in itineraryEdges" :key="e.from+'-'+e.to" :value="i">{{e.fromName}} → {{e.toName}}</option></select></label>
      <p v-for="t in orphanTransfers" :key="t.from_stop+'-'+t.to_stop" class="error">原交通 {{t.leg?.service_number||t.from_stop+' → '+t.to_stop}} 已不连接相邻城市。<button @click="plan.transfers=plan.transfers.filter((x:any)=>x!==t)">从待保存方案移除此段，再核对已订影响</button></p>
      <div v-if="transportSaved && !dirty" class="notice transport-saved" role="status"><strong>{{transportSaved}} 已保存到草稿</strong><p>还需在费用与待办中保存旅行版本。</p><button v-if="nextUnfilledEdge>=0" @click="selectTransport(nextUnfilledEdge);transportSaved=''">继续查下一段：{{itineraryEdges[nextUnfilledEdge]?.fromName}} → {{itineraryEdges[nextUnfilledEdge]?.toName}}</button><button @click="activeSection='review'">核对并保存旅行版本 →</button></div>
      <details v-if="edgeDays.length" class="edge-day-context" aria-label="本段衔接的每日安排"><summary>{{selectedEdge.date}} · 两侧安排与休息提醒</summary><div class="edge-day-grid"><article v-for="c in edgeDays" :key="c.id"><strong>{{c.city}} · {{c.period}}</strong><p>{{c.activities}} 项活动与用餐<span v-if="c.rest"> · {{c.rest}}</span></p><button :disabled="busy||dirty||manualLegDirty" @click="launchCity(c.id,true,selectedEdge.date)">调整 {{c.city}} 当天安排 →</button><button v-if="c.rest" :disabled="busy||dirty||manualLegDirty" @click="editRest(c.id)">调整休息时段</button></article></div><p>时间来自已保存日程；车站接驳和办理缓冲仍需单独预留。</p></details>
      <TransportStage v-if="selectedEdge" :edge="selectedEdge" :leg="legEdit?.outbound" :days="edgeDays" :disabled="busy||dirty" :editing-disabled="manualLegDirty" @edit="openStageDay" @buffer="updateBuffer" />
      <div v-if="manualLegDirty" class="buffer-preview-action"><span>预留时间已改变，尚未保存。</span><button class="primary" :disabled="busy" @click="selectLeg(legEdit?.outbound||null)">预览新的衔接安排 →</button></div>
      <template v-if="selectedEdge"><TicketAssistant :key="selectedEdge.from+'-'+selectedEdge.to+'-'+document.revision" :request="ticketRequest" single-segment :disabled="busy||dirty||manualLegDirty" :schedule-context="{kind:'multi',draft_id:id,revision:document.revision,from_stop:selectedEdge.from,to_stop:selectedEdge.to}" @add="importTicket" @adopt="selectLeg($event.leg,$event.ticketBasis)" @adjust="selectLeg($event.leg,$event.ticketBasis,true)"><template #conflict-actions><button v-for="c in edgeDays" :key="c.id" :disabled="busy||dirty||manualLegDirty" @click="launchCity(c.id,true,selectedEdge.date)">调整 {{c.city}} 当天安排 →</button></template></TicketAssistant>
        <details><summary>手动填写或修改这一段</summary><JourneyEditor :key="selectedEdge.from+'-'+selectedEdge.to" v-model="legEdit" single-leg :start-date="selectedEdge.date" :end-date="plan.end_date" :passengers="plan.companions.count" /><button class="primary" :disabled="busy||!legEdit?.outbound" @click="selectLeg(legEdit?.outbound||null)">预览本段修改</button> <button :disabled="busy||!legEdit?.outbound" @click="selectLeg(legEdit?.outbound||null,undefined,true)">按此班次调整两侧当天安排</button> <button :disabled="busy||!legEdit?.outbound" @click="addLeg(legEdit?.outbound,'手动备选')">加入本段比较</button></details>
        <div v-if="legOptions.length" class="options"><article v-for="(o,i) in legOptions" :key="i"><h3>{{o.name}}</h3><p>{{o.leg.service_number}} {{o.leg.departure_station}} → {{o.leg.arrival_station}}</p><p>{{o.leg.departure_time}} — {{o.leg.arrival_time}}</p><p>全体票价 {{o.leg.ticket_total??'未知'}} {{o.leg.currency}}；附加费用 {{o.leg.extras_total??'未知'}} · 含两端接驳和办理 {{legDuration(o.leg)}} 分钟</p><p>席别：{{o.leg.seat_class||'待确认'}}；中转 {{o.leg.connections??'未知'}}；行李 {{o.leg.baggage_policy||'待确认'}}；退改 {{o.leg.refund_policy||'待确认'}}</p><button :disabled="busy" @click="selectLeg(o.leg)">选择这段，预览整趟影响</button></article></div>
        <p v-if="selectedLeg">已填写：{{selectedLeg.service_number||'班次待定'}} {{selectedLeg.departure_time}} → {{selectedLeg.arrival_time}} <button :disabled="busy" @click="selectLeg(null)">移除此段并预览</button></p>
      </template>
    </section>
    <section v-if="summary" v-show="activeSection==='review' || (readonly && activeSection==='transport')" class="card review-panel"><p class="eyebrow">BEFORE YOU GO</p><h2>{{readonly && activeSection==='transport'?'每一段路，都有安排':'整趟旅行，一起核对'}}</h2><template v-if="readonly && activeSection==='transport'"><div class="edge-picker" aria-label="选择已保存交通段"><button v-for="(e,i) in itineraryEdges" :key="e.from+e.to" :class="{active:edgeIndex===i}" :aria-pressed="edgeIndex===i" @click="selectTransport(i)"><small>{{e.date}}</small><strong>{{e.fromName}} → {{e.toName}}</strong><span>{{edgeLeg(e)?.service_number || '待选班次'}}</span></button></div><TransportStage v-if="selectedEdge" :edge="selectedEdge" :leg="selectedLeg" :days="edgeDays" disabled readonly /></template><p>{{summary.description}}</p><div class="budget"><strong>已知预算 ¥{{summary.budget.total}}</strong><span>已计城际交通 {{summary.budget.transport}} · 已计住宿 {{summary.budget.hotels}} · 已计市内活动与用餐 {{summary.budget.local}}</span><span>{{summary.budget.is_within_budget===false?'已知费用已超预算':summary.budget.complete?'费用已填齐，出发前仍请核价':'费用尚未齐全，不能保证在预算内'}}</span></div><p>门到门交通合计：{{duration(summary.door_minutes)}} · 换城 {{summary.hotel_changes}} 次</p>
      <details :open="activeSection==='transport'"><summary>查看已选交通与待补段</summary><article v-for="e in summary.transfers" :key="e.from_stop+'-'+e.to_stop"><h3>{{e.from_city}} → {{e.to_city}}</h3><template v-if="savedLeg(e)"><p>{{savedLeg(e).service_number||'班次待定'}} · {{savedLeg(e).booking_status==='booked'?'已订':'正在考虑'}} · {{savedLeg(e).seat_class||'席别待确认'}}</p><p>{{savedLeg(e).departure_station}} {{savedLeg(e).departure_time.replace('T',' ')}} → {{savedLeg(e).arrival_station}} {{savedLeg(e).arrival_time.replace('T',' ')}}（北京时间）</p><p>全体 {{savedLeg(e).passengers}} 人票价 {{savedLeg(e).ticket_total??'未知'}} {{savedLeg(e).currency}}；附加费用 {{savedLeg(e).extras_total??'待确认'}}。{{savedLeg(e).price_note}}</p><p>门到门合计 {{e.minutes}} 分钟（含在途、接驳及办理预留）；行李 {{savedLeg(e).baggage_policy||'待确认'}}，退改 {{savedLeg(e).refund_policy||'待确认'}}。</p></template><p v-else>班次、时间和费用待填写。</p></article></details>
      <p v-for="c in summary.conflicts" :key="c" class="error">{{c}}</p>
      <details><summary>每晚住在哪里</summary><p v-for="n in summary.nights" :key="n.date">{{n.date}}：{{n.owners.join(' / ')||'尚待安排'}}</p></details>
      <section class="checklist"><h3>出发前，还需要核对 {{summary.missing.length}} 项</h3><p>按类别展开查看，尚未核对的内容会随版本一起保留。</p><details v-for="group in pendingGroups" :key="group.name" class="checklist-group"><summary>{{group.name}} <span class="badge">{{group.items.length}} 项</span></summary><button v-if="!readonly && group.target" @click="activeSection=group.target">{{group.target==='transport'?'去安排交通':'去设置住宿'}} →</button><ul><li v-for="(item,i) in group.items" :key="i">{{item}}</li></ul></details><p v-if="!summary.missing.length">当前没有列出的待确认项，出发前仍请核对实际信息。</p></section>
      <p v-if="dirty||manualLegDirty" class="notice">请先预览并保存修改，再保存旅行版本。</p><p v-else-if="summary.conflicts.length" class="notice">请先处理上方时间冲突，再保存旅行版本。</p><button class="primary" v-if="document && !readonly" :disabled="busy||dirty||manualLegDirty||summary.conflicts.length>0" @click="finalize">保存这个旅行版本</button><p>可以保存仍有待确认项的版本；未确认费用和空白每日安排会原样保留，不代表已经预订或完整可执行。</p>
    </section>
    <div v-if="document && !readonly && (dirty||manualLegDirty) && !preview" class="save-dock"><div><strong>有修改尚未保存</strong><span>确认对交通、住宿与每日安排的影响后再保存。</span></div><button class="primary" :disabled="busy" @click="manualLegDirty?selectLeg(legEdit?.outbound||null):previewChanges()">查看整趟变更影响 →</button></div>
    </template>
  </main>
</template>
<script setup lang="ts">
import {ref,computed,watch,onMounted,onBeforeUnmount,nextTick} from 'vue'
import TransportStage from '@/components/multitrip/TransportStage.vue'
import JourneyCover from '@/components/multitrip/JourneyCover.vue'
import MultiTripItinerary from '@/components/multitrip/MultiTripItinerary.vue'
import {useRoute,useRouter,onBeforeRouteLeave,onBeforeRouteUpdate} from 'vue-router'
import {multiTripInputIssues} from '@/utils/multiTripValidation'
import {multiApi} from '@/services/api'
import TicketAssistant from '@/components/TicketAssistant.vue'
import JourneyEditor from '@/components/JourneyEditor.vue'
import type {Journey,JourneyLeg,TripFormData} from '@/types'
const route=useRoute(),router=useRouter(),id=computed(()=>String(route.params.id||''))
const clone=(v:any)=>JSON.parse(JSON.stringify(v)),uid=()=>crypto.randomUUID(),shift=(d:string,n:number)=>new Date(Date.parse(d+'T00:00:00Z')+n*86400000).toISOString().slice(0,10)
const today=new Date().toISOString().slice(0,10),start=shift(today,7)
const city=(name:string)=>({id:uid(),name,timezone:'Asia/Shanghai'})
const stop=(name:string,a:string,b:string)=>({id:uid(),city:city(name),start_date:a,end_date:b,must_visit:true,lodgings:[] as any[],rest_periods:[] as any[]})
const initial=()=>({title:'我的多城市旅行',start_date:start,end_date:shift(start,6),origin:city('上海'),destination:city('上海'),companions:{type:'solo',count:1},hotel_occupancy:null as any,budget:null as number|null,pace:'balanced',preferences:[],transportation:'公共交通',accommodation:'经济型酒店',meal_budget_per_person:null as number|null,dietary_requirements:'',stops:[stop('苏州',start,shift(start,3)),stop('杭州',shift(start,3),shift(start,6))],transfers:[] as any[]})
const plan=ref<any>(initial()),document=ref<any>(null),records=ref<any[]>([]),options=ref<any[]>([]),preview=ref<any>(null),busy=ref(false),error=ref(''),message=ref(''),localNote=ref(''),acknowledge=ref(false),acknowledgeAdjustments=ref(false)
const newPlanBaseline=ref(JSON.stringify(plan.value))
const hasUnsavedChanges=computed(()=>document.value?(dirty.value||manualLegDirty.value):JSON.stringify(plan.value)!==newPlanBaseline.value)
const inputIssues=computed(()=>multiTripInputIssues(plan.value))
const validationPanel=ref<HTMLElement|null>(null),errorPanel=ref<HTMLElement|null>(null),loadFailed=ref(false),openRest=ref<string[]>([])
function confirmLeave(){return !hasUnsavedChanges.value || window.confirm('这次修改尚未保存。离开会丢失未保存的输入，仍要离开吗？')}
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate((to,from)=>String(to.params.id||'')===String(from.params.id||'')||confirmLeave())
function beforeUnload(event:BeforeUnloadEvent){if(hasUnsavedChanges.value){event.preventDefault();event.returnValue=''}}
onMounted(()=>window.addEventListener('beforeunload',beforeUnload))
onBeforeUnmount(()=>window.removeEventListener('beforeunload',beforeUnload))
async function reloadSaved(){if(confirmLeave())await load()}
async function focusField(field:string){activeSection.value='cities';const stop=plan.value.stops.find((s:any)=>field.endsWith(s.id));if(stop)editingCity.value=stop.id;await nextTick();const element=window.document.getElementById(field);let ancestor=element?.parentElement;while(ancestor){if(ancestor.tagName==='DETAILS')(ancestor as HTMLDetailsElement).open=true;ancestor=ancestor.parentElement}element?.focus();element?.scrollIntoView?.({block:'center'})}
async function validInput(){if(!inputIssues.value.length)return true;activeSection.value='cities';await nextTick();validationPanel.value?.focus();validationPanel.value?.scrollIntoView?.({block:'center'});return false}
watch(error,async value=>{if(value){await nextTick();errorPanel.value?.focus();errorPanel.value?.scrollIntoView?.({block:'center'})}})
function toggleRest(id:string,event:Event){const isOpen=(event.target as HTMLDetailsElement).open;openRest.value=isOpen?[...new Set([...openRest.value,id])]:openRest.value.filter(x=>x!==id)}
const readonly=computed(()=>document.value?.status==='saved'),dirty=computed(()=>!!document.value&&JSON.stringify(plan.value)!==JSON.stringify(document.value.plan)),summary=computed(()=>document.value?.summary)
const cityPhotos=computed(()=>Object.fromEntries((summary.value?.cities||[]).map((c:any)=>{const url=c.days?.flatMap((d:any)=>d?.attractions||[]).find((a:any)=>typeof a.image_url==='string'&&/^https?:\/\//.test(a.image_url))?.image_url;return [c.id,url||'']})))
const pendingGroups=computed(()=>{
 const groups=[{name:'城际交通',target:'transport',items:[] as string[]},{name:'住宿与房间',target:'cities',items:[] as string[]},{name:'用餐安排',target:'',items:[] as string[]},{name:'门票与预约',target:'',items:[] as string[]},{name:'其他费用与提醒',target:'',items:[] as string[]}]
 for(const item of summary.value?.missing||[]){const index=/班次|车票|航班|城际|接驳/.test(item)?0:/住宿|酒店|房型|房间|入住/.test(item)?1:/餐|饮食/.test(item)?2:/门票|预约/.test(item)?3:4;groups[index]!.items.push(item)}
 return groups.filter(group=>group.items.length)
})
const activeSection=ref(route.query.section==='transport'?'transport':'overview')
const overviewCity=ref(''),editingCity=ref('')
const paceChoices=[{value:'slow',icon:'◡',name:'慢慢逛',note:'多一点留白与休息'},{value:'balanced',icon:'◒',name:'刚刚好',note:'游玩和休息都有位置'},{value:'active',icon:'↗',name:'尽兴探索',note:'把时间留给更多体验'}]
function setBoundary(index:number,days:number){const a=plan.value.stops[index],b=plan.value.stops[index+1];const date=shift(a.start_date,days);a.end_date=date;b.start_date=date;localNote.value=document.value && JSON.stringify(plan.value)===JSON.stringify(document.value.plan)?'':'换城日期已调整，尚未保存。已有班次和日程保留，请预览日期变化的影响。'}
function updateBuffer(change:{key:string;value:number}){if(busy.value||dirty.value||!legEdit.value?.outbound)return;legEdit.value={...legEdit.value,outbound:{...legEdit.value.outbound,[change.key]:change.value}}}
function openStageDay(cityId:string){if(!busy.value&&!dirty.value&&!manualLegDirty.value)launchCity(cityId,true,selectedEdge.value.date)}
function openTransport(index:number){selectTransport(index);activeSection.value='transport'}
async function openCityChapter(cityId:string){activeSection.value='overview';overviewCity.value=cityId;await nextTick();window.document.querySelector('.itinerary-layout')?.scrollIntoView?.({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'})}
const transportSaved=ref('')
const pendingTicket=ref<JourneyLeg|null>(null)
function discardChanges(){legEdit.value={...legEdit.value!,outbound:document.value.plan.transfers.find((t:any)=>t.from_stop===selectedEdge.value?.from&&t.to_stop===selectedEdge.value?.to)?.leg||null};plan.value=clone(document.value.plan);preview.value=null;pendingTicket.value=null;message.value='已撤销未保存修改，恢复上次保存的旅行。'}
async function editRest(stopId:string){activeSection.value='cities';editingCity.value=stopId;openRest.value=[...new Set([...openRest.value,stopId])];await nextTick();window.document.getElementById('rest-'+stopId)?.scrollIntoView?.({block:'center'})}
const workspaceNav=ref<HTMLElement|null>(null)
watch(activeSection,async()=>{await nextTick();workspaceNav.value?.scrollIntoView?.({block:'start'})})
const tabs=[{id:'overview',number:'01',label:'行程总览'},{id:'cities',number:'02',label:'城市与住宿'},{id:'transport',number:'03',label:'城际交通'},{id:'review',number:'04',label:'费用与待办'}]
const tripDays=computed(()=>Math.max(0,nights(plan.value.start_date,plan.value.end_date)+1)||'—')
const money=(n:number)=>Number(n||0).toLocaleString('zh-CN',{maximumFractionDigits:2})
const previewDays=(city:any)=>(city.days||[]).filter((d:any)=>d && [pendingTicket.value?.departure_time.slice(0,10),pendingTicket.value?.arrival_time.slice(0,10)].includes(d.date))
const previewPanel=ref<HTMLElement|null>(null)
watch(preview,async value=>{if(value){await nextTick();previewPanel.value?.focus();previewPanel.value?.scrollIntoView?.({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'})}})
const edgeLeg=(e:any)=>plan.value.transfers.find((t:any)=>t.from_stop===e.from&&t.to_stop===e.to)?.leg
const filledTransfers=computed(()=>itineraryEdges.value.filter(e=>edgeLeg(e)).length)
const savedLeg=(e:any)=>document.value?.plan.transfers.find((t:any)=>t.from_stop===e.from_stop&&t.to_stop===e.to_stop)?.leg
const numberOrNull=(e:Event)=>(e.target as HTMLInputElement).value===''?null:Number((e.target as HTMLInputElement).value)
const windowText=(w:any)=>w.available_minutes===0?(w.rest_minutes?'当天可用时间留给休息，暂无游玩时段':'当天主要在途，暂无游玩时段'):clock(Math.max(480,w.start_minutes))+'—'+clock(Math.min(1320,w.end_minutes))+' 内安排活动'+(w.rest_minutes?`，其中留出 ${w.rest_minutes} 分钟休息`:'')
const nights=(a:string,b:string)=>Math.round((Date.parse(b)-Date.parse(a))/86400000),clock=(n:number)=>String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0'),duration=(n:number|null)=>n==null?'待填齐各段':`${Math.floor(n/60)}小时${n%60}分`
watch(plan,()=>{preview.value=null;acknowledge.value=false;acknowledgeAdjustments.value=false;options.value=[]},{deep:true})
function accept(d:any){document.value=d;plan.value=clone(d.plan);preview.value=null;options.value=[]}
async function run(fn:(current:()=>boolean)=>Promise<void>){
  if(busy.value)return
  const generation=loadGeneration,target=id.value,basis=JSON.stringify([plan.value,legEdit.value]),current=()=>generation===loadGeneration&&target===id.value&&basis===JSON.stringify([plan.value,legEdit.value])
  busy.value=true;error.value='';message.value=''
  try{await fn(current)}catch(e:any){if(current()){const detail=e?.response?.data?.detail;error.value=typeof detail==='string'?detail:Array.isArray(detail)?detail.map(x=>x.msg?.replace(/^Value error, /,'')).join('；'):'操作未完成，已保存旅行保持原样，请检查输入或重试。';preview.value=null}}finally{if(generation===loadGeneration&&target===id.value)busy.value=false}
}
let loadGeneration=0
async function load(){const generation=++loadGeneration;const target=id.value;busy.value=true;error.value='';loadFailed.value=false;document.value=null;preview.value=null;message.value='';localNote.value='';activeSection.value=route.query.section==='transport'?'transport':'overview';edgeIndex.value=Number(route.query.edge)||0;transportSaved.value='';pendingTicket.value=null;overviewCity.value='';try{const d=await multiApi(target?'/'+target:'');if(generation!==loadGeneration||target!==id.value)return;if(target)accept(d);else{plan.value=initial();newPlanBaseline.value=JSON.stringify(plan.value);records.value=d}}catch{if(generation===loadGeneration){loadFailed.value=true;error.value='读取失败，请重试；已保存旅行保持原样。'}}finally{if(generation===loadGeneration)busy.value=false}}
watch(id,load);onMounted(load)
const cityNames=(p:any)=>JSON.stringify([p.origin.name,p.destination.name,p.stops.map((s:any)=>s.city.name)])
watch(()=>cityNames(plan.value),names=>{if(document.value && names!==cityNames(document.value.plan) && !busy.value)clearUnbookedTransfers()})
function toggleOccupancy(){plan.value.hotel_occupancy=plan.value.hotel_occupancy?null:{room_count:1,adults_per_room:plan.value.companions.count,children_ages:[]}}
function setAges(e:Event){plan.value.hotel_occupancy.children_ages=(e.target as HTMLInputElement).value.split(/[,，]/).filter(x=>x.trim()).map(Number)}
function addRest(s:any){(s.rest_periods??=[]).push({id:uid(),date:s.start_date,start_time:'14:00',end_time:'15:00',label:'留给自己的休息时间'})}
async function suggestRest(){if(!await validInput())return;await run(async current=>{const data=await multiApi('/rest-suggestions','post',plan.value);if(!current())return;plan.value=clone(data.plan);localNote.value='已填入建议休息时段，尚未保存。'+data.notes.join('；')+(document.value?' 请核对后查看整趟变更影响。':' 请核对后建立这趟旅行。');openRest.value=plan.value.stops.filter((s:any)=>s.rest_periods?.length).map((s:any)=>s.id);editingCity.value=openRest.value[0]||'';await nextTick();window.document.getElementById('rest-'+openRest.value[0])?.scrollIntoView?.({block:'center'})})}
function addHotel(s:any){s.lodgings.push({id:uid(),name:'',check_in:s.start_date,check_out:s.end_date,rooms:1,amount:null,basis:'stay_total',currency:'CNY',source:'unknown',source_note:'',recorded_at:null,taxes_included:null,booked:false})}
function clearUnbookedTransfers(){plan.value.transfers=plan.value.transfers.filter((t:any)=>t.leg?.booking_status==='booked');localNote.value='城市变更后，未订旧班次已从待保存方案移除，请重新查票；已订班次保留，冲突需要手工处理。'}
function move(i:number,d:number){const a=plan.value.stops[i],b=plan.value.stops[i+d];const slots=plan.value.stops.map((s:any)=>[s.start_date,s.end_date]);plan.value.stops[i]=b;plan.value.stops[i+d]=a;plan.value.stops.forEach((s:any,j:number)=>{s.start_date=slots[j][0];s.end_date=slots[j][1]});clearUnbookedTransfers()}
function removeCity(i:number){const removed=plan.value.stops[i];if(removed.lodgings.some((h:any)=>h.booked)){error.value='这座城市有已订住宿，请先核对并修改住宿状态。';return}const next=plan.value.stops[i+1],prev=plan.value.stops[i-1];if(next)next.start_date=removed.start_date;else prev.end_date=removed.end_date;plan.value.stops.splice(i,1);clearUnbookedTransfers()}
function addCity(){const last=plan.value.stops.at(-1);const middle=shift(last.start_date,Math.max(1,Math.floor(nights(last.start_date,last.end_date)/2)));const end=last.end_date;last.end_date=middle;plan.value.stops.push(stop('',middle,end));clearUnbookedTransfers()}
async function compare(){if(!await validInput())return;await run(async current=>{const data=await multiApi('/compare','post',plan.value);if(current())options.value=data.options})}
function choose(o:any){plan.value=clone(o.plan);localNote.value='已载入这组城市日期，尚未保存；请核对住宿、车票和每日安排。'}
async function create(){if(!await validInput())return;await run(async current=>{const d=await multiApi('','post',plan.value);if(!current())return;accept(d);await router.push('/multi-trip/'+d.id)})}
async function previewChanges(ticketBasis?:unknown,adjustDays=false){if(!await validInput())return;await run(async current=>{const data=await multiApi('/'+id.value+'/preview','post',{plan:plan.value,revision:document.value.revision,ticket_basis:typeof ticketBasis==='string'?ticketBasis:undefined,adjust_days:adjustDays});if(current()){if(data.proposed_plan){plan.value=clone(data.proposed_plan);await nextTick()}preview.value=data}})}
async function saveChanges(){const p=preview.value;if(!p)return;await run(async current=>{const d=await multiApi('/'+id.value,'put',{plan:plan.value,revision:document.value.revision,preview_token:p.preview_token,acknowledge_booked:acknowledge.value,adjustment_id:p.adjustment_id,acknowledge_adjustments:acknowledgeAdjustments.value});if(!current())return;const ticket=pendingTicket.value;accept(d);transportSaved.value=ticket?.service_number||'';pendingTicket.value=null;message.value=d.summary.conflicts.length?'整趟草稿已更新，仍有时间冲突需要处理。':'整趟草稿已更新。'})}
async function finalize(){await run(async current=>{const d=await multiApi('/'+id.value+'/save','post',{revision:document.value.revision});if(!current())return;accept(d);message.value='已保存；后续修改请复制为新版本。'})}
async function copyVersion(){await run(async current=>{const d=await multiApi('/'+id.value+'/copy','post');if(!current())return;accept(d);await router.push('/multi-trip/'+d.id)})}
async function launchCity(stopId:string,edit:boolean,date?:string){await run(async current=>{
  const suffix=`/${id.value}/cities/${stopId}`
  const data=edit?await multiApi(suffix+'/edit','post',{revision:document.value.revision}):await multiApi(suffix+'/request')
  if(!current())return
  const query={multi:id.value,stop:stopId,basis:data.basis,revision:String(data.revision),...(date?{date,...(activeSection.value==='transport'?{returnSection:'transport',edge:String(edgeIndex.value)}:{})}:{})}
  if(edit)await router.push({path:'/draft/'+data.draft_id,query})
  else{sessionStorage.setItem('tripFormData',JSON.stringify(data.request));sessionStorage.setItem('journeyPreview',JSON.stringify({request:data.request,days:data.days||[]}));await router.push({path:'/discover',query})}
})}
const edgeIndex=ref(Number(route.query.edge)||0),legEdit=ref<Journey|null>(null),legOptions=ref<any[]>([])
const itineraryEdges=computed(()=>{const nodes=[{id:'origin',city:plan.value.origin},...plan.value.stops,{id:'destination',city:plan.value.destination}];return nodes.slice(0,-1).map((n:any,i:number)=>({from:n.id,to:nodes[i+1].id,fromName:n.city.name,toName:nodes[i+1].city.name,date:i===0?plan.value.start_date:plan.value.stops[i-1].end_date}))})
const orphanTransfers=computed(()=>plan.value.transfers.filter((t:any)=>!itineraryEdges.value.some((e:any)=>e.from===t.from_stop&&e.to===t.to_stop)))
const selectedEdge=computed(()=>itineraryEdges.value[edgeIndex.value]||itineraryEdges.value[0]),selectedLeg=computed(()=>plan.value.transfers.find((t:any)=>t.from_stop===selectedEdge.value?.from&&t.to_stop===selectedEdge.value?.to)?.leg)
const manualLegDirty=computed(()=>JSON.stringify(legEdit.value?.outbound||null)!==JSON.stringify(selectedLeg.value||null))
function selectTransport(index:number){if(index===edgeIndex.value)return;if(manualLegDirty.value&&!window.confirm('这一段手动输入还未预览保存。切换会丢失这些输入，仍要切换吗？'))return;edgeIndex.value=index}
watch(legEdit,()=>{if(manualLegDirty.value)preview.value=null},{deep:true})
const nextUnfilledEdge=computed(()=>itineraryEdges.value.findIndex(e=>!edgeLeg(e)))
const overviewTransfers=computed(()=>(summary.value?.transfers||[]).map((t:any)=>({...t,leg:savedLeg(t)})))
function openDayTransport(from?:string,to?:string){const i=itineraryEdges.value.findIndex(e=>e.from===from&&e.to===to);if(i>=0)selectTransport(i);activeSection.value='transport'}
const edgeDays=computed(()=>{const e=selectedEdge.value;if(!e)return [];return (summary.value?.cities||[]).filter((c:any)=>c.id===e.from||c.id===e.to).map((c:any)=>{const day=c.days?.find((d:any)=>d?.date===e.date);const items=(day?.timeline_schedule||[]).filter((i:any)=>!['free_time','gap','wait'].includes(i.kind)&&!(i.kind==='hotel'&&i.start_time===i.end_time));const rest=c.windows?.find((w:any)=>w.date===e.date)?.rest_periods||[];return {id:c.id,city:c.city,window:c.windows?.find((w:any)=>w.date===e.date),hotel:day?.hotel?.name,items,period:items.length?items[0].start_time+'—'+items.at(-1).end_time:'当天尚无安排',activities:items.filter((i:any)=>['attraction','meal'].includes(i.kind)).length,rest:rest.map((r:any)=>r.start_time+'—'+r.end_time+' 休息').join('；')}})})
const ticketRequest=computed(()=>({city:selectedEdge.value?.toName||'',start_date:selectedEdge.value?.date||plan.value.start_date,end_date:plan.value.end_date,travel_days:1,companions:plan.value.companions,transportation:plan.value.transportation,accommodation:plan.value.accommodation,preferences:[],food_preference:'本地特色',free_text_input:'',journey:{origin_city:selectedEdge.value?.fromName||'',return_city:selectedEdge.value?.fromName||'',destination_timezone:'Asia/Shanghai'}} as TripFormData))
watch([()=>selectedEdge.value?.from,()=>selectedEdge.value?.to,selectedLeg],()=>{legOptions.value=[];legEdit.value={origin_city:selectedEdge.value?.fromName||'',return_city:selectedEdge.value?.toName||'',destination_timezone:'Asia/Shanghai',outbound:selectedLeg.value?clone(selectedLeg.value):null}},{immediate:true})
function addLeg(leg:JourneyLeg|undefined|null,name:string){if(!leg)return;if(legOptions.value.length>=6){error.value='本段最多比较6个备选，请切换交通段后重新整理。';return}legOptions.value.push({name,leg:clone(leg)})}
function importTicket(c:any){addLeg(c.journey.outbound,c.name)}
const legDuration=(l:JourneyLeg)=>Math.round((Date.parse(l.arrival_time+'+08:00')-Date.parse(l.departure_time+'+08:00'))/60000)+l.transfer_before_minutes+l.station_buffer_minutes+l.baggage_minutes+l.transfer_after_minutes+(Number(selectedEdge.value.from!=='origin')+Number(selectedEdge.value.to!=='destination'))*l.lodging_buffer_minutes
async function selectLeg(leg:JourneyLeg|null,ticketBasis?:string,adjustDays=false){transportSaved.value='';pendingTicket.value=leg?clone(leg):null;const edge=selectedEdge.value;plan.value.transfers=plan.value.transfers.filter((t:any)=>!(t.from_stop===edge.from&&t.to_stop===edge.to));if(leg)plan.value.transfers.push({from_stop:edge.from,to_stop:edge.to,leg:clone(leg)});await previewChanges(ticketBasis,adjustDays)}
</script>
<style scoped src="./multi-trip.css"></style>
