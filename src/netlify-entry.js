// Local tools are public. Cloud tools request each visitor's own Google/Groq grant.
import './app.js';

if('serviceWorker' in navigator&&location.protocol==='https:')navigator.serviceWorker.register('/sw.js').catch(()=>{});
