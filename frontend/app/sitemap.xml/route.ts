import {sitemapXml} from '../../lib/seo';
export function GET(req:Request){return new Response(sitemapXml(new URL(req.url).origin),{headers:{'Content-Type':'application/xml; charset=utf-8','Cache-Control':'public, max-age=3600'}});}
