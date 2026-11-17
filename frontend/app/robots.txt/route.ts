import {robotsText} from '../../lib/seo';
export function GET(req:Request){return new Response(robotsText(new URL(req.url).origin),{headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'public, max-age=3600'}});}
