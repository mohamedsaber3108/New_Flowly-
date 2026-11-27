import {env} from 'cloudflare:workers';
import {handleRequest,type ApiEnv} from '@/lib/api';
export async function POST(req:Request){return handleRequest(req,env as unknown as ApiEnv);}
