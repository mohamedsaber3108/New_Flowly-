import {env} from 'cloudflare:workers';
import {assistant,type ApiEnv} from '@/lib/api';
export async function GET(req:Request){return assistant(req,env as unknown as ApiEnv);}
export async function POST(req:Request){return assistant(req,env as unknown as ApiEnv);}
