import{createHandler}from'../../src/server.mjs';import{WORKER_SOURCE,FONT_ASSETS}from'../../generated/worker.mjs';
export default async(request,context)=>createHandler({workerSource:WORKER_SOURCE,fontAssets:FONT_ASSETS,clientId:Netlify.env.get('GOOGLE_OAUTH_CLIENT_ID')||'186468726329-rr3ehnmr9grubdhftbjdos2od25jv4j0.apps.googleusercontent.com',project:Netlify.env.get('GOOGLE_CLOUD_PROJECT')||'madarfiles'})(request,context);
export const config={path:'/api/*',rateLimit:{action:'rate_limit',windowLimit:600,windowSize:60,aggregateBy:['ip','domain']}};
