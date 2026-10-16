"""K230 native RGB565/LAB color candidates, not a trained object detector.
Screen demonstration thresholds are explicitly uncalibrated.
"""
from six_color_profile import COLORS,PROFILE_NAME,CALIBRATED,MIN_PIXELS,MIN_SIDE,MAX_AREA_FRACTION,MIN_DENSITY,ROI

def filter_blob(blob,roi=ROI):
    x,y,w,h=blob.rect()
    rx,ry,rw,rh=roi
    if min(w,h)<MIN_SIDE or not 0.45<=w/max(1,h)<=2.2:
        return False
    if x<=rx+1 or y<=ry+1 or x+w>=rx+rw-1 or y+h>=ry+rh-1:
        return False
    return MIN_PIXELS<=blob.pixels()<=rw*rh*MAX_AREA_FRACTION and blob.density()>=MIN_DENSITY

def detect_colors(img,roi=ROI):
    thresholds=[row[2] for row in COLORS]
    blobs=img.find_blobs(thresholds,roi=roi,pixels_threshold=MIN_PIXELS,area_threshold=MIN_PIXELS,x_stride=2,y_stride=2,merge=False)
    raw=[]
    for blob in blobs:
        if not filter_blob(blob,roi):continue
        bits=int(blob.code())
        if bits<=0 or bits&(bits-1):
            raw.append({'color':0,'reason':'OVERLAPPING_RANGES','rect':tuple(blob.rect()),'cx':blob.cx(),'cy':blob.cy(),'pixels':blob.pixels()})
            continue
        index=0
        while bits>1:
            bits>>=1
            index+=1
        if index>=len(COLORS):continue
        code,name,_=COLORS[index]
        raw.append({'color':code,'name':name,'rect':tuple(blob.rect()),'cx':blob.cx(),'cy':blob.cy(),'pixels':blob.pixels(),'reason':'CANDIDATE'})
    accepted=[]
    ambiguous=[]
    for i,item in enumerate(raw):
        for other in raw[i+1:]:
            if not item['color'] or not other['color'] or item['color']==other['color']:continue
            x,y,w,h=item['rect']
            ox,oy,ow,oh=other['rect']
            overlap=max(0,min(x+w,ox+ow)-max(x,ox))*max(0,min(y+h,oy+oh)-max(y,oy))
            union=w*h+ow*oh-overlap
            if union and overlap/union>0.5:
                ambiguous.extend([item['color'],other['color']])
                item['reason']=other['reason']='OVERLAPPING_RANGES'
    for code,name,_ in COLORS:
        if code in ambiguous:continue
        group=sorted([r for r in raw if r['color']==code and r['reason']=='CANDIDATE'],key=lambda r:r['pixels'],reverse=True)
        if not group:continue
        # Refuse comparable same-color objects instead of silently selecting one.
        if len(group)>1 and group[1]['pixels']>=0.35*group[0]['pixels']:
            ambiguous.append(code)
        else:accepted.append(group[0])
    return accepted,raw,sorted(set(ambiguous))

class ColorStability:
    def __init__(self):self.previous={}
    def update(self,observations):
        retained={}
        result=[]
        for observation in observations:
            code=observation['color']
            prior=self.previous.get(code)
            count=1
            if prior is not None:
                last,n=prior
                _,_,w,h=observation['rect']
                distance=(observation['cx']-last['cx'])**2+(observation['cy']-last['cy'])**2
                ratio=observation['pixels']/max(1,last['pixels'])
                if distance<=max(12,0.35*min(w,h))**2 and 0.60<ratio<1.67:
                    count=n+1
            retained[code]=(observation,count)
            if count>=3:result.append(observation)
        self.previous=retained
        return result

def main():
    import os,time,gc
    from media.sensor import Sensor
    from media.display import Display
    from media.media import MediaManager
    sensor=None
    stability=ColorStability()
    window_start=time.ticks_ms()
    window_frames=0
    frame=0
    try:
        sensor=Sensor()
        sensor.reset()
        sensor.set_framesize(width=640,height=480)
        sensor.set_pixformat(Sensor.RGB565)
        Display.init(Display.VIRT,width=640,height=480,fps=20,to_ide=True)
        MediaManager.init()
        sensor.run()
        for _ in range(20):sensor.snapshot()
        print('SIX_COLOR_READY',PROFILE_NAME,'calibrated',CALIBRATED)
        window_start=time.ticks_ms()
        while True:
            os.exitpoint()
            loop_start=time.ticks_us()
            img=sensor.snapshot()
            captured_ms=time.ticks_ms()
            start=time.ticks_us()
            accepted,raw,ambiguous=detect_colors(img)
            stable=stability.update(accepted)
            algorithm_ms=time.ticks_diff(time.ticks_us(),start)/1000
            # Sampling precedes all overlays, so graphics cannot affect calibration.
            center=(300,220,40,40)
            sample=None
            if time.ticks_diff(time.ticks_ms(),window_start)>=1500:
                stats=img.get_statistics(roi=center)
                sample={'lab':(stats.l_mean(),stats.a_mean(),stats.b_mean()),'rgb':img.get_pixel(320,240)}
            stable_keys=[(r['color'],r['cx'],r['cy']) for r in stable]
            for item in raw:
                green=(item['color'],item['cx'],item['cy']) in stable_keys and item['color'] not in ambiguous
                color=(0,255,0) if green else (255,180,0)
                img.draw_rectangle(*item['rect'],color=color,thickness=2)
                img.draw_cross(item['cx'],item['cy'],color=color,size=10,thickness=2)
                label='C%d %s'%(item['color'],item.get('name','UNKNOWN'))
                if item['color'] in ambiguous:label+=' ?MULTI'
                elif not green:label+=' ?'
                x,y,_,_=item['rect']
                img.draw_string_advanced(max(0,x),max(35,y-22),18,label,color=color)
            img.draw_rectangle(*ROI,color=(100,100,100),thickness=1)
            img.draw_rectangle(*center,color=(255,255,255),thickness=1)
            img.draw_string_advanced(5,5,18,'DEMO n=%d %.1fms'%(len(stable),algorithm_ms),color=(255,255,0))
            Display.show_image(img)
            frame+=1
            window_frames+=1
            gc.collect()
            if sample is not None:
                elapsed=time.ticks_diff(time.ticks_ms(),window_start)
                print('COLOR_RESULT',{'frame':frame,'captured_ms':captured_ms,'valid':bool(stable),'calibrated':CALIBRATED,'profile':PROFILE_NAME,'targets':[{'color':r['color'],'cx':r['cx'],'cy':r['cy'],'rect':r['rect'],'pixels':r['pixels']} for r in stable],'ambiguous':ambiguous,'center_sample':sample,'algorithm_ms':round(algorithm_ms,1),'window_fps':round(window_frames*1000/max(1,elapsed),1)})
                window_start=time.ticks_ms()
                window_frames=0
    except KeyboardInterrupt:print('SIX_COLOR_STOPPED')
    except Exception as error:
        if str(error)=='IDE interrupt':print('SIX_COLOR_STOPPED')
        else:
            print('SIX_COLOR_ERROR',repr(error))
            raise
    finally:
        try:
            if sensor is not None:sensor.stop()
        finally:
            try:Display.deinit()
            finally:
                os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
                time.sleep_ms(100)
                MediaManager.deinit()

if __name__=='__main__':main()
