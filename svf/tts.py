import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import asyncio, hashlib, os, subprocess, wave
from config import FF, R
VOICES={'云扬':'zh-CN-YunyangNeural','云健':'zh-CN-YunjianNeural','云希':'zh-CN-YunxiNeural','云夏':'zh-CN-YunxiaNeural'}
def dur(p):
    w=wave.open(p); return w.getnframes()/w.getframerate()
def synth(text,voice='云扬',rate='+12%',backend='edge',pitch='+0Hz'):
    os.makedirs(R+'/数据/tts_cache',exist_ok=True)
    k=hashlib.md5(f"{backend}|{voice}|{rate}|{pitch}|{text}".encode()).hexdigest()[:12]; wav=f"{R}/数据/tts_cache/{k}.wav"
    if os.path.exists(wav): return wav
    if backend=='edge':
        import edge_tts
        mp3=wav[:-4]+'.mp3'
        last=None
        for attempt in range(4):
            try:
                asyncio.run(edge_tts.Communicate(text,VOICES[voice],rate=rate,pitch=pitch).save(mp3)); last=None; break
            except Exception as e:
                last=e; import time; time.sleep(1.5*(attempt+1))
        if last is not None: raise RuntimeError(f'TTS failed: {text!r} {voice} {rate} {pitch}: {last}')
        subprocess.run([FF,'-v','error','-y','-i',mp3,'-ar','44100','-ac','1',wav],check=True); os.remove(mp3)
    else: raise NotImplementedError(backend)
    return wav
if __name__=='__main__':
    p=synth('这是一条配音测试'); print(p,round(dur(p),2))
