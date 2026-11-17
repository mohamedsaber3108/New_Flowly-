import {env} from 'cloudflare:workers';
import {lookupRequest,type ApiEnv} from '../../../lib/api';
export async function POST(req:Request){return lookupRequest(req,env as unknown as ApiEnv);}
