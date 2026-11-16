import{readdir}from'node:fs/promises';import{execFileSync}from'node:child_process';
for(const folder of['src','netlify/functions','scripts'])for(const file of await readdir(folder))if(file.endsWith('.mjs'))execFileSync(process.execPath,['--check',folder+'/'+file],{stdio:'inherit'});
console.log('JavaScript syntax checks passed.');
