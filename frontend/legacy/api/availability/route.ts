import {env} from 'cloudflare:workers';
import {availability,type ApiEnv} from '@/lib/api';
export async function GET(req:Request){return availability(req,env as unknown as ApiEnv);}
