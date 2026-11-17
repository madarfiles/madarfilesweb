// Local tools are public. Cloud tools request each visitor's own Google/Groq grant.
import './app.js';
import {startReceiveFromLocation} from './p2p.js';
startReceiveFromLocation();

if('serviceWorker' in navigator&&location.protocol==='https:')navigator.serviceWorker.register('/sw.js').catch(()=>{});
