const FIELDS=['runtime','id','requestId','gpu','highMemory','allocated','operation','kernel','jobId','kind','state','lastUsed','hasLocalResult'];
export class ToolSessions{
 constructor(storage,key='madar-tool-sessions-v3'){this.storage=storage;this.key=key;try{const parsed=JSON.parse(storage?.getItem(key));this.items=parsed&&typeof parsed==='object'&&!Array.isArray(parsed)?Object.fromEntries(Object.entries(parsed).filter(([tool,j])=>j&&typeof j==='object'&&j.kind===tool&&typeof j.runtime==='string').map(([tool,j])=>[tool,{...j,hasLocalResult:false}])):{};}catch{this.items={};}}
 get(tool){const j=this.items[tool];return j?.kind===tool?{...j}:null;}
 set(tool,job){if(job){if(job.kind&&job.kind!==tool)throw Error('جلسة تخص أداة أخرى');this.items[tool]=Object.fromEntries(FIELDS.filter(k=>job[k]!==undefined).map(k=>[k,job[k]]));this.items[tool].kind=tool;}else delete this.items[tool];this.save();}
 save(){try{this.storage?.setItem(this.key,JSON.stringify(this.items));}catch{}}
 list(){return Object.entries(this.items).map(([tool,j])=>({tool,...j}));}
 clearRuntime(runtime){for(const [tool,j]of Object.entries(this.items))if(j.runtime===runtime)delete this.items[tool];this.save();}
}

export function evictionCandidates(items,current){return items.filter(j=>j.kind!==current&&j.allocated&&(j.state==='error'||j.state==='done'&&j.hasLocalResult===true)).sort((a,b)=>(a.lastUsed||0)-(b.lastUsed||0));}
