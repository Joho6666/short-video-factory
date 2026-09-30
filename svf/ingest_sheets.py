import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import cv2, glob, os, numpy as np, json
from config import R; info={}
for k in ['人物','空镜']:
    fs=sorted(glob.glob(f"{R}/预览/{k}/*.mp4")); th=[]
    for f in fs:
        c=cv2.VideoCapture(f); d=c.get(7)/c.get(5); info[k+'/'+os.path.basename(f)]=dict(类别=k,时长=round(d,2))
        c.set(cv2.CAP_PROP_POS_MSEC,d*500); ok,fr=c.read()
        fr=cv2.resize(fr,(210,373)) if ok else np.zeros((373,210,3),np.uint8)
        idn=os.path.basename(f)[11:17]; cv2.rectangle(fr,(0,0),(78,24),(0,0,0),-1); cv2.putText(fr,idn,(3,18),0,0.6,(0,255,255),2); th.append(fr)
    for i in range(0,len(th),24):
        b=th[i:i+24]; 
        while len(b)%8: b.append(np.zeros((373,210,3),np.uint8))
        im=np.vstack([np.hstack(b[j:j+8]) for j in range(0,len(b),8)])
        open(f"{R}/联系表/{k}_{i//24+1}.jpg","wb").write(cv2.imencode(".jpg",im,[cv2.IMWRITE_JPEG_QUALITY,80])[1].tobytes())
json.dump(info,open(R+'/数据/素材基础信息.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print(len(info))
