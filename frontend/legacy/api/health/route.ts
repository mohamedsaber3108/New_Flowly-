import {env} from 'cloudflare:workers';
import {health,type ApiEnv} from '@/lib/api';
export async function GET(){return health(env as unknown as ApiEnv);}
