import {createPublicHandler} from '../../src/netlify-public-server.js';
import {socketFetch} from '../../src/netlify-websocket.js';
import headers from '../../src/headers.json' with {type:'json'};
import {netlifySecurity} from '../../src/netlify-static.js';
import {getStore} from '@netlify/blobs';
const security=netlifySecurity(headers);
export default createPublicHandler({fetcher:socketFetch,security,p2pStore:()=>getStore({name:'madar-p2p',consistency:'strong'}),fastStore:()=>getStore({name:'madar-fast',consistency:'strong'})});
export const config={path:'/api/*',rateLimit:{action:'rate_limit',windowLimit:600,windowSize:60,aggregateBy:['ip','domain']}};
