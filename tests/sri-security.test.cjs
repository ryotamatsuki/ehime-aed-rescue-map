const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const html=fs.readFileSync('index.html','utf8');
test('all external scripts are pinned with SHA384 and anonymous CORS',()=>{
 const tags=[...html.matchAll(/<script\b[^>]*\bsrc=["']https:\/\/[^"']+["'][^>]*>/g)].map(x=>x[0]);
 assert.ok(tags.length>0,'expect at least one external script');
 for(const tag of tags){
  assert.match(tag,/\bintegrity="sha384-[A-Za-z0-9+/=]+"/);
  assert.match(tag,/\bcrossorigin="anonymous"/);
 }
});
test('avoid known obsolete third-party versions',()=>{
 assert.doesNotMatch(html,/jquery-1\.12\.4\.min\.js/);
 assert.doesNotMatch(html,/leaflet@1\.3\.0/);
});
