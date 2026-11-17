import {env} from 'cloudflare:workers';
import {getChatGPTUser} from '../../../chatgpt-auth';
import {listRequests,type ApiEnv} from '../../../../lib/api';
const OWNER_ID='32d273a1-b716-4c4a-91c4-eaad2b502c47';
export async function GET(req:Request){const user=await getChatGPTUser();return listRequests(req,env as unknown as ApiEnv,user?.userId===OWNER_ID);}
