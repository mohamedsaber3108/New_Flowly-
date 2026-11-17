import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
import {handleRequest,availability,assistant,lookupRequest,listRequests,updateRequest,health,type Database,type DBStatement,type ApiEnv} from '../lib/api';
import {sitemapXml,robotsText} from '../lib/seo';
const here=path.dirname(fileURLToPath(import.meta.url));
const publicDir=path.join(here,'public');const dataDir=path.resolve(process.env.DATA_DIR||path.join(here,'data'));fs.mkdirSync(dataDir,{recursive:true,mode:0o700});
const sqlite=new DatabaseSync(path.join(dataDir,'flowly.sqlite'));sqlite.exec('PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;');
// The standalone Node adapter applies tracked migrations once at startup.
sqlite.exec('CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)');
const migrations=path.join(here,'migrations');if(fs.existsSync(migrations))for(const file of fs.readdirSync(migrations).filter(n=>n.endsWith('.sql')).sort()){if(!sqlite.prepare('SELECT name FROM schema_migrations WHERE name=?').get(file)){sqlite.exec('BEGIN');try{sqlite.exec(fs.readFileSync(path.join(migrations,file),'utf8'));sqlite.prepare('INSERT INTO schema_migrations VALUES (?,?)').run(file,new Date().toISOString());sqlite.exec('COMMIT');}catch(e){sqlite.exec('ROLLBACK');throw e;}}}
class Statement implements DBStatement{sql:string;params:unknown[];constructor(sql:string,params:unknown[]=[]){this.sql=sql;this.params=params;}bind(...params:unknown[]){return new Statement(this.sql,params);}async first<T=Record<string,unknown>>(){return (sqlite.prepare(this.sql).get(...this.params as never[])||null) as T|null;}async all(){return {results:sqlite.prepare(this.sql).all(...this.params as never[]) as Record<string,unknown>[]};}async run(){return sqlite.prepare(this.sql).run(...this.params as never[]);}}
const db:Database={prepare:(sql:string)=>new Statement(sql),async batch(statements){sqlite.exec('BEGIN');try{for(const s of statements)await s.run();sqlite.exec('COMMIT');return [];}catch(e){sqlite.exec('ROLLBACK');throw e;}}};
const env={...process.env,DB:db} as unknown as ApiEnv;
// Bedrock uses the EC2 IAM role / default AWS credential chain. No keys are shipped to the browser.
if(process.env.AI_PROVIDER==='bedrock'&&process.env.BEDROCK_MODEL_ID){env.PORTABLE_BEDROCK=async(system,message,history)=>{const sdkName:string='@aws-sdk/client-bedrock-runtime';const {BedrockRuntimeClient,ConverseCommand}=await import(sdkName);const client=new BedrockRuntimeClient({region:process.env.AWS_REGION||'us-east-1'});const clean=history.slice(-6).filter((x,i,a)=>!(i===a.length-1&&x.content===message));const messages=[...clean,{role:'user',content:message}].map(m=>({role:m.role as 'user'|'assistant',content:[{text:m.content}]}));const response=await client.send(new ConverseCommand({modelId:process.env.BEDROCK_MODEL_ID!,system:[{text:system}],messages,inferenceConfig:{maxTokens:500,temperature:.3}}));return response.output?.message?.content?.map((c:{text?:string})=>c.text||'').join('')||'';};}
const port=Number(process.env.PORT||3000);const host=process.env.HOST||'127.0.0.1';
const mime:Record<string,string>={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.ttf':'font/ttf','.otf':'font/otf','.png':'image/png','.json':'application/json','.txt':'text/plain'};
const server=http.createServer(async(req,res)=>{try{const base=process.env.PUBLIC_ORIGIN||`http://localhost:${port}`;const url=new URL(req.url||'/',base);if(!['GET','HEAD','POST','PATCH'].includes(req.method||'GET')){res.writeHead(405);return res.end('Method not allowed');}if(url.pathname.startsWith('/api/')){let raw='';for await(const chunk of req){raw+=chunk;if(Buffer.byteLength(raw)>25000){res.writeHead(413,{'Content-Type':'application/json'});return res.end(JSON.stringify({error:'Request too large'}));}}const headers=new Headers();for(const [k,v] of Object.entries(req.headers)){if(v)headers.set(k,Array.isArray(v)?v.join(','):v);}const forwarded=req.headers['x-forwarded-for'];const ip=process.env.TRUST_PROXY==='1'&&typeof forwarded==='string'?forwarded.split(',')[0].trim():req.socket.remoteAddress||'unknown';headers.set('x-real-ip',ip); // Enable TRUST_PROXY only behind a trusted reverse proxy; keep the app port private.
 headers.delete('cf-connecting-ip'); // Only the hosted dispatch may supply Cloudflare's visitor header.
 const request=new Request(url,{method:req.method,headers,...(['POST','PATCH'].includes(req.method||'')?{body:raw}: {})});let response:Response;
 if(url.pathname==='/api/health')response=await health(env);
 else if(url.pathname==='/api/requests'&&req.method==='POST')response=await handleRequest(request,env);
 else if(url.pathname==='/api/request-status'&&req.method==='POST')response=await lookupRequest(request,env);
 else if(url.pathname==='/api/availability'&&req.method==='GET')response=await availability(request,env);
 else if(url.pathname==='/api/assistant')response=await assistant(request,env);
 else if(url.pathname==='/api/admin/requests'&&req.method==='GET')response=await listRequests(request,env);
 else if(/^\/api\/admin\/requests\/FLW-\d{8}-[A-F0-9]{8}$/.test(url.pathname)&&req.method==='PATCH')response=await updateRequest(request,env,url.pathname.split('/').at(-1)!);
 else response=Response.json({error:'Not found'},{status:404});res.writeHead(response.status,Object.fromEntries(response.headers));return res.end(await response.text());}
 if(url.pathname==='/sitemap.xml'||url.pathname==='/robots.txt'){const text=url.pathname==='/sitemap.xml'?sitemapXml(new URL(base).origin):robotsText(new URL(base).origin);res.writeHead(200,{'Content-Type':url.pathname==='/sitemap.xml'?'application/xml; charset=utf-8':'text/plain; charset=utf-8','Cache-Control':'public, max-age=3600'});return res.end(req.method==='HEAD'?'':text);}
 let target=path.resolve(publicDir,'.'+decodeURIComponent(url.pathname));if(!target.startsWith(publicDir+path.sep)&&target!==publicDir){res.writeHead(403);return res.end('Forbidden');}if(!fs.existsSync(target)||fs.statSync(target).isDirectory()){if(path.extname(url.pathname)){res.writeHead(404);return res.end('Not found');}target=path.join(publicDir,'index.html');}
 const ext=path.extname(target);res.writeHead(200,{'Content-Type':mime[ext]||'application/octet-stream','X-Content-Type-Options':'nosniff','Referrer-Policy':'strict-origin-when-cross-origin','X-Frame-Options':'SAMEORIGIN','Cache-Control':target.includes('/assets/')?'public,max-age=31536000,immutable':'public,max-age=300'});if(req.method==='HEAD')return res.end();fs.createReadStream(target).pipe(res);
 }catch(e){console.error('Flowly server error:',e instanceof Error?e.message:'Unexpected error');if(!res.headersSent)res.writeHead(500,{'Content-Type':'application/json'});res.end(JSON.stringify({error:'Internal server error'}));}});
server.listen(port,host,()=>console.log(`Flowly listening on ${host}:${port}`));
const cleanup=setInterval(()=>{try{sqlite.prepare('DELETE FROM rate_limits WHERE expires < ?').run(Math.floor(Date.now()/1000));}catch{}},3600000);cleanup.unref();
process.on('SIGTERM',()=>{clearInterval(cleanup);server.close(()=>{sqlite.close();process.exit(0);});});
