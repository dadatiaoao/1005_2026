#include "vision_link.h"
#include <string.h>

static uint16_t get16(const uint8_t *p){return (uint16_t)((uint16_t)p[0]|((uint16_t)p[1]<<8));}
static uint32_t get32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void put16(uint8_t *p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void put32(uint8_t *p,uint32_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);p[2]=(uint8_t)(v>>16);p[3]=(uint8_t)(v>>24);}
uint16_t vision_crc16(const uint8_t *data,size_t size){
    uint16_t crc=0xffffu;size_t i;unsigned j;
    for(i=0;i<size;i++){
        crc^=(uint16_t)((uint16_t)data[i]<<8);
        for(j=0;j<8;j++)crc=(uint16_t)((crc&0x8000u)?((uint32_t)crc<<1)^0x1021u:((uint32_t)crc<<1));
    }
    return crc;
}
static void clear_result(VisionLink *l){l->have_result=0;memset(&l->snapshot,0,sizeof(l->snapshot));}
void vision_link_init(VisionLink *l){memset(l,0,sizeof(*l));}
static size_t frame(uint8_t *out,uint8_t type,uint32_t sid,uint32_t seq,uint16_t size){
    out[0]=0xa5;out[1]=0x5a;out[2]=1;out[3]=type;
    put16(out+4,size);put32(out+6,sid);put32(out+10,seq);
    put16(out+14+size,vision_crc16(out+2,(size_t)12+size));
    return (size_t)16+size;
}
size_t vision_link_open(VisionLink *l,uint32_t sid,uint8_t *out,size_t cap){
    if(!sid||!out||cap<16u)return 0;
    vision_link_init(l);l->session_id=sid;
    return frame(out,VISION_OPEN,sid,0,0);
}
size_t vision_link_command(VisionLink *l,uint32_t seq,const VisionCommand *c,uint8_t *out,size_t cap){
    uint8_t *p;
    if(!out||!c||!l->ready||!seq||seq<=l->expected_seq||cap<34u)return 0;
    if(c->enabled>1u||c->mode<1u||c->mode>2u||c->color<1u||c->color>6u||c->position>3u)return 0;
    if(c->width<40u||c->height<40u||(uint32_t)c->x+c->width>640u||(uint32_t)c->y+c->height>480u||c->lease_ms<500u||c->lease_ms>120000u)return 0;
    p=out+14;
    p[0]=c->enabled;p[1]=c->mode;p[2]=c->color;p[3]=c->position;
    put16(p+4,c->x);put16(p+6,c->y);put16(p+8,c->width);put16(p+10,c->height);
    put32(p+12,c->lease_ms);put16(p+16,c->pose);
    l->expected_seq=seq;l->command=*c;clear_result(l);
    return frame(out,VISION_COMMAND,l->session_id,seq,18);
}
static int read_result(const uint8_t *p,uint16_t size,VisionSnapshot *r){
    unsigned i,j;uint16_t count;
    if(size<24u)return 0;
    memset(r,0,sizeof(*r));
    r->state=p[0];r->mode=p[1];r->flags=get16(p+2);count=get16(p+22);
    if(r->state>9u||r->mode<1u||r->mode>2u||(r->flags&~7u)||count>3u||size!=24u+count*14u)return 0;
    if((r->state==VISION_TARGET_FOUND)!=(count>0u)||((r->flags&1u)!=0u)!=(count>0u)||((r->flags&2u)&&((r->flags&5u)!=5u)))return 0;
    if(r->mode==VISION_MATERIAL&&count>1u)return 0;
    r->epoch=get32(p+4);r->frame=get32(p+8);r->captured_ms=get32(p+12);r->command_age_ms=get32(p+16);
    r->algorithm_ms10=get16(p+20);r->count=(uint8_t)count;
    for(i=0;i<count;i++){
        const uint8_t *q=p+24u+i*14u;VisionTarget *t=&r->targets[i];
        t->id=q[0];t->cx10=get16(q+2);t->cy10=get16(q+4);t->width=get16(q+6);t->height=get16(q+8);
        t->number_age_ms=get16(q+10);t->score1000=get16(q+12);
        if(q[1]||t->id<1u||t->id>(r->mode==VISION_MATERIAL?6u:3u)||t->cx10>=6400u||t->cy10>=4800u||t->score1000>1000u)return 0;
        for(j=0;j<i;j++)if(r->targets[j].id==t->id)return 0;
        if(r->mode==VISION_MATERIAL&&(!t->width||t->width>640u||!t->height||t->height>480u||t->number_age_ms||t->score1000))return 0;
        if(r->mode==VISION_RING&&(t->width||t->height||t->number_age_ms>900u))return 0;
    }
    return 1;
}
static void receive(VisionLink *l,const uint8_t *b,uint32_t now){
    uint8_t kind=b[3];uint16_t size=get16(b+4);uint32_t seq=get32(b+10);const uint8_t *p=b+14;
    VisionSnapshot r;unsigned i;
    if(get32(b+6)!=l->session_id)return;
    if(kind==VISION_ACK&&size==6u&&p[1]<=1u){
        if(!seq&&!p[0])l->ready=1;
        else if(seq==l->expected_seq&&p[0]){
            clear_result(l);
            if(p[0]==2u)l->ready=0; /* K230 reset: reopen before sending more commands. */
        }
        return;
    }
    if(kind!=VISION_RESULT||!l->ready||!l->expected_seq||seq!=l->expected_seq||!read_result(p,size,&r))return;
    if(r.mode!=l->command.mode||(r.count&&r.command_age_ms>=l->command.lease_ms))return;
    if(l->have_frame&&(!(r.frame-l->last_frame)||(uint32_t)(r.frame-l->last_frame)>=0x80000000u))return;
    if(r.count&&!l->command.enabled)return;
    for(i=0;i<r.count;i++){
        if(r.mode==VISION_MATERIAL&&r.targets[i].id!=l->command.color)return;
        if(r.mode==VISION_RING&&l->command.position&&r.targets[i].id!=l->command.position)return;
        if(r.targets[i].cx10<(uint32_t)l->command.x*10u||r.targets[i].cx10>=((uint32_t)l->command.x+l->command.width)*10u||
           r.targets[i].cy10<(uint32_t)l->command.y*10u||r.targets[i].cy10>=((uint32_t)l->command.y+l->command.height)*10u)return;
    }
    r.command_seq=seq;l->snapshot=r;l->last_frame=r.frame;l->have_frame=1;l->last_result_ms=now;l->have_result=1;
}
static void drop(VisionParser *p,unsigned n){
    p->used=(uint16_t)(p->used-n);memmove(p->bytes,p->bytes+n,p->used);
}
void vision_link_feed(VisionLink *l,const uint8_t *data,size_t size,uint32_t now){
    VisionParser *p=&l->parser;size_t i;
    if(p->used&&(uint32_t)(now-p->last_byte_ms)>250u)p->used=0;
    if(size)p->last_byte_ms=now;
    for(i=0;i<size;i++){
        uint16_t payload,total;
        p->bytes[p->used++]=data[i];
        while(p->used>=2u){
            if(p->bytes[0]!=0xa5u||p->bytes[1]!=0x5au){drop(p,1);continue;}
            if(p->used<14u)break;
            payload=get16(p->bytes+4);
            if(p->bytes[2]!=1u||payload>96u||!get32(p->bytes+6)){p->bad_header++;drop(p,1);continue;}
            total=(uint16_t)(payload+16u);
            if(p->used<total)break;
            if(vision_crc16(p->bytes+2,(size_t)total-4u)!=get16(p->bytes+total-2u)){p->bad_crc++;drop(p,1);continue;}
            receive(l,p->bytes,now);drop(p,total);
        }
    }
}
int vision_link_get(VisionLink *l,uint32_t now,VisionSnapshot *out){
    if(!l->have_result||(uint32_t)(now-l->last_result_ms)>=VISION_RESULT_TIMEOUT_MS)clear_result(l);
    if(out)*out=l->snapshot;
    return l->have_result&&(l->snapshot.flags&1u)!=0u;
}
int vision_link_can_align(VisionLink *l,uint32_t now){
    return vision_link_get(l,now,0)&&(l->snapshot.flags&6u)==6u;
}
size_t vision_link_receipt(VisionLink *l,uint32_t now,uint8_t *out,size_t cap){
    VisionSnapshot s;int valid;
    if(!out||cap<26u||!l->ready||!l->expected_seq)return 0;
    valid=vision_link_get(l,now,&s);
    put32(out+14,s.frame);out[18]=(uint8_t)valid;out[19]=valid?s.targets[0].id:0;
    put16(out+20,valid?s.targets[0].cx10:0);put16(out+22,valid?s.targets[0].cy10:0);
    return frame(out,VISION_RECEIPT,l->session_id,l->expected_seq,10);
}
