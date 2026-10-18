import { fileURLToPath } from 'node:url';
export default { output: 'standalone', outputFileTracingRoot: fileURLToPath(new URL('.', import.meta.url)), poweredByHeader: false, experimental: {cpus:1}, devIndicators:false, webpack(config,{dev}) {if(!dev)config.cache=false;return config;} };
