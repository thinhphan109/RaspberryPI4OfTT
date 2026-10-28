"""Best-effort native YouTube player quality; report actual decoded size separately."""
import json

CHOICES = ('240', '360', 'auto')


def script(choice):
    if choice not in CHOICES:
        raise ValueError('Chất lượng YouTube không hợp lệ')
    return r"""(()=>{const desired=CHOICE,p=document.querySelector('#movie_player'),v=p?.querySelector('video');
if(!p||!v)return {applied:false,height:0};
const levels=p.getAvailableQualityLevels?.()||[],target=desired==='auto'?'auto':desired==='240'?'small':'medium';
// This is the native site player, not the deprecated iframe quality API.
// Capability checks and actual videoHeight prevent claiming a guaranteed cap.
if(typeof p.setPlaybackQualityRange==='function'&&(target==='auto'||levels.includes(target))){
 p.setPlaybackQualityRange(target,target);
 return {applied:true,height:v.videoHeight||0};
}return {applied:false,height:v.videoHeight||0};})()""".replace('CHOICE', json.dumps(choice))
