"""K230 ring locator: inner ellipse detection and short-term target tracking.
T1/T2/... are temporary track IDs, never the printed location numbers 1/2/3.
Only pixel coordinates are reported. No UART or motion control is configured.
"""
import math

MIN_RADIUS = 10
MAX_CONTOURS = 1200
STABLE_FRAMES = 3

def _parent(hierarchy, index):
    if len(hierarchy.shape) == 2:
        return int(hierarchy[index, 3])
    return int(hierarchy[0, index, 3])

def _point(contour, index):
    if len(contour.shape) == 3:
        return float(contour[index, 0, 0]), float(contour[index, 0, 1])
    return float(contour[index, 0]), float(contour[index, 1])

def _sample(e, scale, phi):
    x,y,a,b,rot,index = e
    cr,sr = math.cos(rot),math.sin(rot)
    u,v = scale*a*math.cos(phi),scale*b*math.sin(phi)
    return int(round(x+cr*u-sr*v)),int(round(y+sr*u+cr*v))

def detect_rings(gray, cv2):
    """Return [{ellipse:(cx,cy,rx,ry,rad,index),support:int}], diagnostics.
    A candidate is a complete elliptical white opening within concentric bands.
    Central digits are ignored by sampling a white annulus near its inner edge.
    """
    height,width = gray.shape[0],gray.shape[1]
    blurred = cv2.GaussianBlur(gray,(3,3),0)
    threshold,mask = cv2.threshold(blurred,0,255,cv2.THRESH_BINARY_INV|cv2.THRESH_OTSU)
    contours,hierarchy = cv2.findContours(mask,cv2.RETR_TREE,cv2.CHAIN_APPROX_NONE)
    info = {'status':'NOT_FOUND','contours':len(contours),'ellipses':0}
    if len(contours)>MAX_CONTOURS:
        info['status']='TOO_MUCH_NOISE'
        return [],info
    if hierarchy is None:
        return [],info
    fitted = {}
    for index,contour in enumerate(contours):
        n = contour.shape[0]
        if n<32:
            continue
        area = abs(cv2.contourArea(contour))
        if area<math.pi*MIN_RADIUS*MIN_RADIUS:
            continue
        bx,by,bw,bh = cv2.boundingRect(contour)
        if bx<=1 or by<=1 or bx+bw>=width-1 or by+bh>=height-1:
            continue
        center,size,angle = cv2.fitEllipse(contour)
        x,y = float(center[0]),float(center[1])
        a,b = float(size[0])/2,float(size[1])/2
        if min(a,b)<MIN_RADIUS or min(a,b)/max(a,b)<0.48:
            continue
        if not 0.86<area/(math.pi*a*b)<1.10:
            continue
        rot = float(angle)*math.pi/180
        cr,sr = math.cos(rot),math.sin(rot)
        residual,count = 0.0,0
        for k in range(0,n,max(1,n//24)):
            px,py = _point(contour,k)
            dx,dy = px-x,py-y
            u,v = (cr*dx+sr*dy)/a,(-sr*dx+cr*dy)/b
            residual+=abs(math.sqrt(u*u+v*v)-1)
            count+=1
        if residual/count<=0.065:
            fitted[index]=(x,y,a,b,rot,index)
    info['ellipses']=len(fitted)
    candidates=[]
    for index,e in fitted.items():
        ancestors=[]
        p=_parent(hierarchy,index)
        while p>=0:
            ancestors.append(p)
            p=_parent(hierarchy,p)
        # In inverted binary, odd-depth contours bound white holes.
        if len(ancestors)%2!=1:
            continue
        x,y,a,b,rot,_=e
        support=0
        largest=1.0
        for p in ancestors:
            other=fitted.get(p)
            if other is None:
                continue
            ox,oy,oa,ob,_,_=other
            ratio=math.sqrt(oa*ob/(a*b))
            if 1.01<ratio<2.6 and (ox-x)**2+(oy-y)**2<(0.12*min(a,b)+3)**2:
                support+=1
                largest=max(largest,ratio)
        if support<3 or largest<1.15:
            continue
        white=0
        for scale in (0.76,0.88):
            for k in range(32):
                px,py=_sample(e,scale,k*math.pi/16)
                if 0<=px<width and 0<=py<height and int(mask[py,px])==0:
                    white+=1
        if white<58:
            continue
        dark=0
        for k in range(32):
            for scale in (1.015,1.04,1.07,1.10):
                px,py=_sample(e,scale,k*math.pi/16)
                if 0<=px<width and 0<=py<height and int(mask[py,px])!=0:
                    dark+=1
                    break
        if dark<27:
            continue
        candidates.append({'ellipse':e,'support':support,'ancestors':ancestors})
    # Keep the innermost qualifying hole in each contour tree, all target groups.
    result=[]
    for candidate in candidates:
        index=candidate['ellipse'][5]
        if any(index in other['ancestors'] for other in candidates if other is not candidate):
            continue
        result.append({'ellipse':candidate['ellipse'],'support':candidate['support']})
    result.sort(key=lambda r:r['ellipse'][0])
    info['status']='FOUND' if result else 'NOT_FOUND'
    return result,info

class RingTracker:
    """Associate geometry only; no predictions are emitted on missing frames."""
    def __init__(self):
        self.tracks=[]
        self.next_id=1

    def update(self,detections):
        pairs=[]
        for i,track in enumerate(self.tracks):
            x,y,a,b,_,_=track['ellipse']
            radius=math.sqrt(a*b)
            for j,det in enumerate(detections):
                ox,oy,oa,ob,_,_=det['ellipse']
                ratio=math.sqrt(oa*ob)/radius
                distance=math.sqrt((ox-x)**2+(oy-y)**2)
                if 0.70<ratio<1.43 and distance<max(12,0.35*min(a,b)):
                    pairs.append((distance/radius+abs(ratio-1),i,j))
        pairs.sort()
        used_tracks,used_detections=set(),set()
        observed=[]
        for cost,i,j in pairs:
            if i in used_tracks or j in used_detections:
                continue
            used_tracks.add(i)
            used_detections.add(j)
            track=self.tracks[i]
            # A frame gap requires stability to be confirmed again.
            track['stable']=track['stable']+1 if track['misses']==0 else 1
            track['misses']=0
            track['ellipse']=detections[j]['ellipse']
            observed.append(track)
        retained=[]
        for i,track in enumerate(self.tracks):
            if i not in used_tracks:
                track['misses']+=1
                track['stable']=0
            if track['misses']<=3:
                retained.append(track)
        for j,det in enumerate(detections):
            if j in used_detections:
                continue
            track={'id':self.next_id,'ellipse':det['ellipse'],'stable':1,'misses':0}
            self.next_id+=1
            retained.append(track)
            observed.append(track)
        self.tracks=retained
        return sorted(observed,key=lambda t:t['id'])

def main():
    import os,time,gc,cv2
    from media.sensor import Sensor
    from media.display import Display
    from media.media import MediaManager
    width,height=640,480
    sensor=None
    tracker=RingTracker()
    frame=0
    last_log=0
    try:
        sensor=Sensor()
        sensor.reset()
        sensor.set_framesize(width=width,height=height)
        sensor.set_pixformat(Sensor.RGB888)
        Display.init(Display.VIRT,width=width,height=height,fps=20,to_ide=True)
        MediaManager.init()
        sensor.run()
        print('RING_LOCATOR_READY 640x480; T labels are tracks, not printed digits')
        while True:
            os.exitpoint()
            img=sensor.snapshot()
            begin=time.ticks_us()
            gray=cv2.cvtColor(img.to_numpy_ref(),cv2.COLOR_BGR2GRAY)
            rings,info=detect_rings(gray,cv2)
            observed=tracker.update(rings)
            algorithm_ms=time.ticks_diff(time.ticks_us(),begin)/1000
            valid=[]
            for track in observed:
                x,y,a,b,rot,_=track['ellipse']
                stable=track['stable']>=STABLE_FRAMES
                color=(0,255,0) if stable else (255,255,0)
                img.draw_ellipse(int(x),int(y),int(a),int(b),int(rot*180/math.pi),color=color,thickness=2)
                img.draw_cross(int(x),int(y),color=color,size=10,thickness=2)
                img.draw_string_advanced(max(0,int(x-a)),max(25,int(y-b)-24),18,'T%d'%track['id'],color=color)
                if stable:
                    valid.append((track['id'],round(x,1),round(y,1)))
            state='VALID' if valid else ('UNSTABLE' if observed else info['status'])
            img.draw_string_advanced(5,5,18,'%s n=%d %.1fms'%(state,len(valid),algorithm_ms),color=(0,255,0) if valid else (255,255,0))
            Display.show_image(img)
            frame+=1
            if time.ticks_diff(time.ticks_ms(),last_log)>1500:
                print('RING_RESULT',{'frame':frame,'status':state,'valid':bool(valid),'targets':valid,'algorithm_ms':round(algorithm_ms,1)})
                last_log=time.ticks_ms()
            del gray
            gc.collect()
    except KeyboardInterrupt:
        print('RING_LOCATOR_STOPPED')
    except Exception as error:
        if str(error)=='IDE interrupt':
            print('RING_LOCATOR_STOPPED')
        else:
            print('RING_LOCATOR_ERROR',repr(error))
            raise
    finally:
        try:
            if sensor is not None:
                sensor.stop()
        finally:
            try:
                Display.deinit()
            finally:
                os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
                time.sleep_ms(100)
                MediaManager.deinit()

if __name__=='__main__':
    main()
