export const VIDEO_INPUTS=['mp4','mkv','mov','webm','mpeg','mpg','avi','3gp','3g2','m4v','ts','m2ts','mts','vob','wmv','flv','ogv'];
export const AUDIO_INPUTS=['mp3','m4a','m4b','aac','wav','flac','ogg','opus','aiff','aif','wma','amr','ac3','eac3','mp2','alac'];
export const MEDIA_INPUTS=[...VIDEO_INPUTS,...AUDIO_INPUTS];
export const AUDIO_OUTPUTS=[['mp3','MP3 — متوافق مع معظم الأجهزة'],['m4a','M4A / AAC'],['wav','WAV — غير مضغوط وحجمه كبير'],['flac','FLAC — صوت بلا فقد إضافي'],['ogg','OGG / Vorbis'],['opus','Opus'],['aac','AAC']];
export const VIDEO_OUTPUTS=[['mp4','MP4 — مناسب للجوال'],['mkv','MKV'],['mov','MOV'],['webm','WebM / VP9'],['avi','AVI'],['ts','MPEG-TS']];
export const MEDIA_MIME={mp3:'audio/mpeg',m4a:'audio/mp4',wav:'audio/wav',flac:'audio/flac',ogg:'audio/ogg',opus:'audio/ogg',aac:'audio/aac',mp4:'video/mp4',mkv:'video/x-matroska',mov:'video/quicktime',webm:'video/webm',avi:'video/x-msvideo',ts:'video/mp2t'};
