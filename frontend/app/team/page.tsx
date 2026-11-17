import {notFound} from 'next/navigation';
import type {Metadata} from 'next';
import {getChatGPTUser} from '../chatgpt-auth';
import FlowlyApp from '../../components/FlowlyApp';
export const dynamic='force-dynamic';
export const metadata:Metadata={title:'Team requests — Flowly',robots:{index:false,follow:false}};
export default async function TeamPage(){const user=await getChatGPTUser();if(user?.userId!=='32d273a1-b716-4c4a-91c4-eaad2b502c47')notFound();return <FlowlyApp initialPath="/team"/>;}
