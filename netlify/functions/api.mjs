import {createPublicHandler} from '../../src/netlify-public-server.js';
import {socketFetch} from '../../src/netlify-websocket.js';
import security from '../../src/headers.json' with {type:'json'};
export default createPublicHandler({fetcher:socketFetch,security});
export const config={path:'/api/*',rateLimit:{action:'rate_limit',windowLimit:600,windowSize:60,aggregateBy:['ip','domain']}};
