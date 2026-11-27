import {env} from 'cloudflare:workers';
import {getChatGPTUser} from '@/app/chatgpt-auth';
import {updateRequest,type ApiEnv} from '@/lib/api';
const OWNER_ID='32d273a1-b716-4c4a-91c4-eaad2b502c47';
export async function PATCH(req:Request,{params}:{params:Promise<{reference:string}>}){const user=await getChatGPTUser();const {reference}=await params;return updateRequest(req,env as unknown as ApiEnv,reference,user?.userId===OWNER_ID);}
