import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath} from 'node:url';
export default defineConfig({root:fileURLToPath(new URL('.',import.meta.url)),publicDir:'../public',plugins:[react()],server:{proxy:{'/api':'http://127.0.0.1:3000'}},build:{outDir:'../ec2-dist/public',emptyOutDir:true,sourcemap:false}});
