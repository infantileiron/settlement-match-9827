<script setup lang="ts">
import {ref,onMounted,watch} from 'vue';
import {route} from '../router';
import {batches} from '../stores/batches';
import {canWrite} from '../stores/auth';
import {useTask} from '../hooks/useTask';
import {appendBatchImport,fetchBatchImports} from '../api/batches';
import PageHeading from '../components/common/PageHeading.vue';
import Notice from '../components/common/Notice.vue';
import ImportResult from '../components/ImportResult.vue';
const name=ref(''),text=ref(''),description=ref('');
const target=ref(route.value.query.get('batch')||''),appendText=ref('');
const result=ref<any>(null),history=ref<any[]>([]);
const {error,busy,act}=useTask();
const {error:appendError,busy:appendBusy,act:appendAct}=useTask();
onMounted(async()=>{await batches.load();if(!target.value)target.value=batches.items.value[0]?.id||'';if(target.value)await loadHistory()});
watch(target,next=>{if(result.value&&result.value.batch_id!==next)result.value=null;loadHistory()});
watch(()=>route.value.query.get('batch'),v=>{if(v)target.value=v});
async function loadHistory(){try{history.value=await fetchBatchImports(target.value)}catch(e){history.value=[]}}
async function file(e:Event,append=false){const f=(e.target as HTMLInputElement).files?.[0];if(!f)return;if(append)appendText.value=await f.text();else text.value=await f.text()}
function submit(){act(async()=>{const r=await batches.create({name:name.value,csv_text:text.value,description:description.value});name.value='';text.value='';target.value=r.id;result.value=r.import;await loadHistory()})}
function submitAppend(){appendAct(async()=>{const r=await appendBatchImport(target.value,{csv_text:appendText.value});result.value=r;appendText.value='';await batches.load();await loadHistory()})}
function show(r:any){result.value=r}
</script>
<template>
<PageHeading index="01 / 对账批次" title="把委托与凭证，留在同一份输入快照。" note="CSV列external_id,side,party,reference,amount_cents,currency,booking_date。方向milestone/receipt，金额只接正整数分，币种CNY，日期YYYY-MM-DD。续传只追加合法新分录，坏行隔离并保留原行，同编号内容冲突不覆盖原记录。"/>
<div class="two-col">
<section>
<Notice :message="batches.error.value"/>
<article v-for="r in batches.items.value" :key="r.id" class="batch-row"><p class="eyebrow">STATEMENT BATCH</p><h2>{{r.name}}</h2><p>{{r.description}}</p><a :href="'#/items?batch='+r.id" class="action-link">打开委托与凭证分录 →</a><div class="actions"><button class="secondary" @click="target=r.id">续传 / 查看导入结果</button></div></article>
<section v-if="target" class="import-history"><h2>导入结果</h2><p class="method-note">按时间倒序；逐行追溯写入、重复与隔离。</p><div class="history-list"><button v-for="h in history" :key="h.id" class="record-open" @click="show(h)"><span :class="h.totals_check.complete?'ok':'bad'">{{h.totals_check.complete?'合计一致':'合计不一致'}}</span> · 原始{{h.totals.total_rows}} / 写入{{h.totals.inserted}} / 重复{{h.totals.duplicate}} / 隔离{{h.totals.quarantined}} <small>{{h.created_at}}</small></button></div></section>
<ImportResult v-if="result" :result="result"/>
</section>
<div>
<form v-if="canWrite()" class="editor-panel" @submit.prevent="submit"><h2>导入结算批次</h2><label>批次名称<input v-model="name" required minlength="2"></label><label>CSV文件<input type="file" accept=".csv" @change="file"></label><label>整数分CSV<textarea v-model="text" rows="10" required placeholder="external_id,side,party,reference,amount_cents,currency,booking_date"></textarea></label><label>来源说明<input v-model="description"></label><Notice :message="error"/><button :disabled="busy">校验并导入批次</button></form>
<form v-if="canWrite()&&target" class="editor-panel section-space" @submit.prevent="submitAppend"><h2>向现有批次续传</h2><p class="method-note">追加到“{{batches.items.value.find(b=>b.id===target)?.name||target}}”；已入账分录按编号比对，内容一致记重复、内容冲突留待核对且不覆盖。修好隔离行后可再次导入。</p><label>CSV文件<input type="file" accept=".csv" @change="file($event,true)"></label><label>整数分CSV<textarea v-model="appendText" rows="10" required placeholder="external_id,side,party,reference,amount_cents,currency,booking_date"></textarea></label><Notice :message="appendError"/><button :disabled="appendBusy">续传并逐行核对</button></form>
</div>
</div>
</template>
