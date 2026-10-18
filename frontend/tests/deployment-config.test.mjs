import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
const source=await readFile(new URL('../next.config.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
function load(overrides={}){
 const context={exports:{},URL,Buffer,process:{env:{STORYVERSE_PUBLIC_DEPLOYMENT:'true',
  API_INTERNAL_URL:'https://api.example.com',NEXT_PUBLIC_SUPABASE_URL:'https://project.supabase.co',
  NEXT_PUBLIC_SUPABASE_ANON_KEY:'sb_publishable_synthetic',...overrides}}};
 vm.runInNewContext(compiled,context);return context.exports.default;
}
const config=load();
assert.equal((await config.rewrites())[0].destination,'https://api.example.com/api/:path*');
const headers=(await config.headers())[0].headers;
assert.ok(headers.some(h=>h.key==='Strict-Transport-Security'));
assert.ok(headers.some(h=>h.key==='Content-Security-Policy' && h.value.includes("frame-ancestors 'none'")));
for(const endpoint of ['http://127.0.0.1:8000','http://api.example.com','https://user:pass@api.example.com','https://api.example.com/path','https://api.example.com/?key=bad']){
 assert.throws(()=>load({API_INTERNAL_URL:endpoint}));
}
assert.throws(()=>load({NEXT_PUBLIC_SUPABASE_ANON_KEY:''}));
assert.throws(()=>load({NEXT_PUBLIC_SUPABASE_ANON_KEY:'sb_secret_synthetic'}));
assert.throws(()=>load({NEXT_PUBLIC_SUPABASE_ANON_KEY:'eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.synthetic'}));
console.log('PASS: production frontend HTTPS origin, public-key-only configuration, rewrite and security headers.');
