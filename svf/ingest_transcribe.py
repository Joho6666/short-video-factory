import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import glob, os, subprocess, json
from faster_whisper import WhisperModel
from config import FF
m=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=4); from config import R; out={}
for f in sorted(glob.glob(R+'/素材/人物/*.mp4')):
    w=R+'/数据/_t.wav'; subprocess.run([FF,'-v','error','-y','-i',f,'-vn','-ac','1','-ar','16000',w])
    segs,_=m.transcribe(w,language='zh',initial_prompt=__import__('config').PROJECT.get('asr_prompt','以下是普通话的句子。'),vad_filter=True)
    out[os.path.basename(f)]=[dict(s=round(s.start,2),e=round(s.end,2),t=s.text.strip()) for s in segs]
    json.dump(out,open(R+'/数据/口播转写.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('done',len(out))
