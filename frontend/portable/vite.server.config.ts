import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';
export default defineConfig({build:{ssr:fileURLToPath(new URL('./server.ts',import.meta.url)),outDir:'ec2-dist',emptyOutDir:false,rollupOptions:{external:['node:sqlite','node:fs','node:http','node:path','node:url','node:crypto','@aws-sdk/client-bedrock-runtime'],output:{entryFileNames:'server.mjs'}}}});
