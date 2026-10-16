"""Circle interior glyph recognition. Returns 0 for unknown/non-target digits.
Template similarity is a heuristic score, not a calibrated probability.
"""
import math
from digit_templates import TEMPLATES

SIZE=24
MIN_SCORE=0.80
MIN_MARGIN=0.055

def recognize_digit(gray,ellipse,cv2,np):
    x,y,a,b,rot,_=ellipse
    cr,sr=math.cos(rot),math.sin(rot)
    sx,sy=30/a,30/b
    transform=np.array([[sx*cr,sx*sr,32-sx*(cr*x+sr*y)],
                        [-sy*sr,sy*cr,32+sy*(sr*x-cr*y)]],dtype=np.float)
    tile=cv2.warpAffine(gray,transform,(64,64),flags=cv2.INTER_LINEAR,borderValue=(255,))
    _,binary=cv2.threshold(tile,0,255,cv2.THRESH_BINARY_INV|cv2.THRESH_OTSU)
    # Eliminate the circle edges and everything outside the central disk.
    disk=np.zeros((64,64),dtype=np.uint8)
    cv2.circle(disk,(32,32),24,(255,),-1)
    binary=cv2.bitwise_and(binary,disk)
    contours,_=cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    regions=[]
    for contour in contours:
        area=abs(cv2.contourArea(contour))
        bx,by,bw,bh=cv2.boundingRect(contour)
        if area>=10 and bw>=2 and bh>=4:
            regions.append((area,bx,by,bw,bh))
    regions.sort(reverse=True)
    if not regions:
        return {'digit':0,'score':0.0,'margin':0.0,'reason':'NO_GLYPH'}
    area,bx,by,bw,bh=regions[0]
    if max(bw,bh)<9 or max(bw,bh)>45 or (bx+bw/2-32)**2+(by+bh/2-32)**2>120:
        return {'digit':0,'score':0.0,'margin':0.0,'reason':'BAD_GLYPH_GEOMETRY'}
    if len(regions)>1 and regions[1][0]>0.25*area:
        return {'digit':0,'score':0.0,'margin':0.0,'reason':'MULTIPLE_GLYPHS'}
    scale=20/max(bw,bh)
    nw,nh=max(1,int(round(bw*scale))),max(1,int(round(bh*scale)))
    small=cv2.resize(binary[by:by+bh,bx:bx+bw],(nw,nh),interpolation=cv2.INTER_LINEAR)
    ox,oy=(SIZE-nw)//2,(SIZE-nh)//2
    bits=0
    count=0
    for row in range(SIZE):
        for col in range(SIZE):
            value=0
            if ox<=col<ox+nw and oy<=row<oy+nh:
                value=1 if int(small[row-oy,col-ox])>=100 else 0
            bits=(bits<<1)|value
            count+=value
    # Exact overlap: an 8x8 top-three shortlist can discard the best 24x24
    # template when a few edge pixels change. Bound only by pixel counts,
    # which cannot exclude any candidate capable of improving its class score.
    scores=[0.0]*10
    for item in TEMPLATES:
        digit,template,template_count,_,_=item
        total=count+template_count
        if 2*min(count,template_count)<=scores[digit]*total:continue
        intersection=bin(bits&template).count('1')
        score=2*intersection/total
        if score>scores[digit]:scores[digit]=score
    order=sorted(range(10),key=lambda d:scores[d],reverse=True)
    best=order[0]
    score=scores[best]
    margin=score-scores[order[1]]
    accepted=best in (1,2,3) and score>=MIN_SCORE and margin>=MIN_MARGIN
    return {'digit':best if accepted else 0,'score':score,'margin':margin,
            'reason':'OK' if accepted else 'UNRECOGNIZED'}

class DigitConsensus:
    """Require 3 consecutive matching reads; unknown resets immediately."""
    def __init__(self):self.states={}
    def update(self,readings):
        retained={}
        for track_id,reading in readings:
            digit=reading['digit']
            previous,count=self.states.get(track_id,(0,0))
            count=count+1 if digit and digit==previous else (1 if digit else 0)
            retained[track_id]=(digit,count)
        self.states=retained
        confirmed={i:d for i,(d,n) in retained.items() if d and n>=3}
        # Two rings claiming one printed ID are ambiguous, never valid positions.
        current=[d for d,n in retained.values() if d]
        duplicates={d for d in current if current.count(d)>1}
        return {i:d for i,d in confirmed.items() if d not in duplicates}
