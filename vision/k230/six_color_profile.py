"""Demonstration LAB ranges; replace after real-material calibration."""
PROFILE_NAME='screen_demo_v1'
CALIBRATED=False
# Competition color codes: red1, yellow2, blue3, green4, black5, light-blue6.
COLORS=[
    (1,'RED',(18,85,25,95,8,90)),
    (2,'YELLOW',(35,100,-25,25,30,100)),
    (3,'BLUE',(8,75,10,90,-110,-25)),
    (4,'GREEN',(15,92,-90,-18,0,90)),
    (5,'BLACK',(0,25,-12,12,-12,12)),
    (6,'LIGHTBLUE',(30,95,-60,5,-80,-8)),
]
MIN_PIXELS=300
MIN_SIDE=18
MAX_AREA_FRACTION=0.20
MIN_DENSITY=0.50
ROI=(10,35,620,435)

def matching_colors(lab):
    l,a,b=lab
    return [code for code,name,t in COLORS if t[0]<=l<=t[1] and t[2]<=a<=t[3] and t[4]<=b<=t[5]]
