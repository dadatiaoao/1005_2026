"""Single camera, selectable material/ring mode. USB commands or injected UART.
Both image channels remain configured; only the selected detector runs.
"""
COMMAND_PATH='/sdcard/codex_vision_control.json'

def main(command_io=None,diagnostics=False):
    import os,time,gc,json,cv2
    from ulab import numpy as np
    from media.sensor import Sensor,CAM_CHN_ID_0,CAM_CHN_ID_1
    from media.display import Display
    from media.media import MediaManager
    from six_color_locator import detect_colors,ColorStability
    from ring_locator import detect_rings,RingTracker,STABLE_FRAMES
    from ring_digits import recognize_digit
    from number_schedule import NumberSchedule
    from vision_session import VisionSession
    session=VisionSession()
    sensor=None
    tracker=RingTracker()
    numbers=NumberSchedule()
    stability=ColorStability()
    previous_text=None
    last_poll=None
    last_state=None
    drop_frames=3
    frame=0
    window_frames=0
    window_start=time.ticks_ms()
    try:
        sensor=Sensor()
        sensor.reset()
        sensor.set_framesize(width=640,height=480,chn=CAM_CHN_ID_0)
        sensor.set_pixformat(Sensor.RGB565,chn=CAM_CHN_ID_0)
        sensor.set_framesize(width=640,height=480,chn=CAM_CHN_ID_1)
        sensor.set_pixformat(Sensor.RGB888,chn=CAM_CHN_ID_1)
        Display.init(Display.VIRT,width=640,height=480,fps=20,to_ide=True)
        MediaManager.init()
        sensor.run()
        for _ in range(20):sensor.snapshot(chn=CAM_CHN_ID_0)
        print('VISION_READY','UART' if command_io is not None else 'USB_FILE_SIM',COMMAND_PATH if command_io is None else '')
        window_start=time.ticks_ms()
        while True:
            os.exitpoint()
            now=time.ticks_ms()
            reset=False
            if command_io is not None:
                try:reset=command_io.poll(now)
                except OSError:
                    command_io.on_io_error()
                    reset=True
                session=command_io.session
            elif last_poll is None or time.ticks_diff(now,last_poll)>=200:
                last_poll=now
                text=None
                try:
                    with open(COMMAND_PATH,'r') as f:text=f.read(2049)
                    if text!=previous_text:
                        if len(text)>2048:raise ValueError('Command too large')
                        command=json.loads(text)
                        reset=session.apply(command,now)
                        previous_text=text
                        print('VISION_COMMAND',{'seq':session.control.seq,'mode':session.mode,'epoch':session.epoch,'reset':reset,'cleared_targets':[] if reset else None})
                except OSError:
                    reset=session.control.fault!='COMMAND_FILE_MISSING'
                    session.invalidate('COMMAND_FILE_MISSING')
                    previous_text=None
                except (ValueError,TypeError) as error:
                    reset=True
                    session.invalidate('INVALID_COMMAND')
                    previous_text=text
                    print('VISION_COMMAND_ERROR',str(error))
            state=session.control.state(now)
            if reset or state!=last_state:
                tracker=RingTracker()
                numbers=NumberSchedule()
                stability=ColorStability()
                drop_frames=3
                last_state=state
            channel=CAM_CHN_ID_0 if session.mode=='MATERIAL' else CAM_CHN_ID_1
            img=sensor.snapshot(chn=channel)
            captured_ms=time.ticks_ms()
            begin=time.ticks_us()
            colors=[]
            raw=[]
            rings=[]
            ambiguous=[]
            observed=[]
            pending=False
            geometry_ms=0.0
            digit_ms=0.0
            warming=state=='ACTIVE' and drop_frames>0
            if warming:drop_frames-=1
            elif state=='ACTIVE' and session.mode=='MATERIAL':
                candidates,raw,ambiguous=detect_colors(img,session.control.roi)
                colors=stability.update([r for r in candidates if r['color']==session.control.color])
            elif state=='ACTIVE':
                reading=None
                gray=cv2.cvtColor(img.to_numpy_ref(),cv2.COLOR_BGR2GRAY)
                rx,ry,rw,rh=session.control.roi
                # Detect on a contiguous ROI; OCR uses global coordinates on gray.
                region=np.array(gray[ry:ry+rh,rx:rx+rw],dtype=np.uint8)
                detections,info=detect_rings(region,cv2)
                for det in detections:
                    x,y,a,b,rot,index=det['ellipse']
                    det['ellipse']=(x+rx,y+ry,a,b,rot,index)
                observed=tracker.update(detections)
                numbers.sync(observed,captured_ms)
                geometry_ms=time.ticks_diff(time.ticks_us(),begin)/1000
                selected=numbers.select(observed,captured_ms) if len(observed)<=3 else None
                if selected is not None:
                    before=time.ticks_us()
                    reading=recognize_digit(gray,selected['ellipse'],cv2,np)
                    digit_ms=time.ticks_diff(time.ticks_us(),before)/1000
                    numbers.record(selected['id'],reading,captured_ms)
                confirmed=numbers.positions(observed,time.ticks_ms())
                for track in observed:
                    number=confirmed.get(track['id'])
                    if number and track['stable']>=STABLE_FRAMES and len(observed)<=3:
                        x,y,a,b,rot,_=track['ellipse']
                        rings.append({'position':number['position'],'track':track['id'],'cx':round(x,1),'cy':round(y,1),'score':round(number['score'],3),'number_age_ms':number['number_age_ms']})
                pending=bool(observed) and not rings
                if diagnostics and frame<120:
                    print('VISION_RING_DIAG',{'frame':frame+1,'geometry':info,
                        'tracks':[(t['id'],round(t['ellipse'][0],1),t['stable'],numbers.states[t['id']]['digit'],numbers.states[t['id']]['count']) for t in observed],
                        'selected':selected['id'] if selected else None,'reading':reading,
                        'positions':[r['position'] for r in rings]})
                del region,gray
            result=session.result(colors,rings,ambiguous,time.ticks_ms(),pending,warming)
            algorithm_ms=time.ticks_diff(time.ticks_us(),begin)/1000
            if command_io is not None:
                try:command_io.publish(result,frame+1,captured_ms,algorithm_ms,time.ticks_ms())
                except OSError:
                    command_io.on_io_error()
                    result=session.result([],[],[],time.ticks_ms())
            # Keep IDE framebuffer format constant across both sensor channels.
            if session.mode=='RING':img=img.to_rgb565()
            if diagnostics and session.mode=='RING' and frame in (29,59,89):
                path='/sdcard/ring_diag_%d.jpg'%(frame+1)
                img.save(path,quality=95)
                print('VISION_RING_RAW',frame+1,path)
            # Drawing follows all processing so overlays never enter detection.
            for item in raw:
                if item['color']!=session.control.color:continue
                good=any(r['rect']==item['rect'] for r in result['targets'])
                color=(0,255,0) if good else (255,180,0)
                img.draw_rectangle(*item['rect'],color=color,thickness=2)
                img.draw_cross(item['cx'],item['cy'],color=color,size=10,thickness=2)
                img.draw_string_advanced(item['rect'][0],max(32,item['rect'][1]-22),18,'C%d'%item['color'],color=color)
            for track in observed:
                x,y,a,b,rot,_=track['ellipse']
                match=next((r for r in result['targets'] if r['track']==track['id']),None)
                known=next((r for r in rings if r['track']==track['id']),None)
                color=(0,255,0) if match else ((0,200,255) if known else (255,180,0))
                label='P%d'%known['position'] if known else 'T%d ?'%track['id']
                img.draw_ellipse(int(x),int(y),int(a),int(b),int(rot*180/3.141592654),color=color,thickness=2)
                img.draw_cross(int(x),int(y),color=color,size=10,thickness=2)
                img.draw_string_advanced(max(0,int(x-a)),max(32,int(y-b)-22),18,label,color=color)
            img.draw_rectangle(*session.control.roi,color=(0,200,255),thickness=2)
            img.draw_string_advanced(5,5,18,'%s %s'%(session.mode,result['state']),color=(255,255,0))
            img.draw_string_advanced(5,458,16,('UART' if command_io is not None else 'USB SIM')+' / DEMO / ALIGNMENT BLOCKED',color=(255,255,0))
            Display.show_image(img)
            frame+=1
            window_frames+=1
            gc.collect()
            now=time.ticks_ms()
            elapsed=time.ticks_diff(now,window_start)
            if elapsed>=1000:
                result.update({'frame':frame,'captured_ms':captured_ms,'transport':'UART' if command_io is not None else 'USB_FILE_SIM','algorithm_ms':round(algorithm_ms,1),'geometry_ms':round(geometry_ms,1),'digit_ms':round(digit_ms,1),'window_fps':round(window_frames*1000/elapsed,1)})
                if command_io is not None:
                    result.update({'uart_rx_bytes':command_io.rx_bytes,'uart_tx_bytes':command_io.tx_bytes,'wire_bad_crc':command_io.parser.bad_crc,'wire_bad_header':command_io.parser.bad_header})
                print('VISION_RESULT',result)
                window_frames=0
                window_start=now
            # Give USB background services time even during continuous OCR.
            time.sleep_ms(10)
    except KeyboardInterrupt:print('VISION_STOPPED')
    except Exception as error:
        if str(error)=='IDE interrupt':print('VISION_STOPPED')
        else:
            print('VISION_ERROR',repr(error))
            raise
    finally:
        try:
            if sensor is not None:sensor.stop()
        finally:
            try:Display.deinit()
            finally:
                os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
                time.sleep_ms(100)
                try:MediaManager.deinit()
                finally:
                    if command_io is not None:command_io.close()

if __name__=='__main__':main()
