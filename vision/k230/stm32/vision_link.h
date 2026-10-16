#ifndef VISION_LINK_H
#define VISION_LINK_H
#include <stddef.h>
#include <stdint.h>

#define VISION_MAX_FRAME 112u
#define VISION_RESULT_TIMEOUT_MS 350u
enum { VISION_OPEN=1, VISION_COMMAND=2, VISION_RECEIPT=3, VISION_ACK=0x81, VISION_RESULT=0x82 };
enum { VISION_MATERIAL=1, VISION_RING=2 };
enum { VISION_STOPPED=0, VISION_WARMING_UP=1, VISION_TARGET_FOUND=2,
       VISION_TARGET_NOT_FOUND=3, VISION_AMBIGUOUS=4, VISION_NUMBER_PENDING=5,
       VISION_COMMAND_EXPIRED=6, VISION_INVALID_COMMAND=7,
       VISION_COMMAND_FILE_MISSING=8, VISION_LINK_RESET=9 };

typedef struct {
    uint8_t enabled, mode, color, position;
    uint16_t x,y,width,height;
    uint32_t lease_ms;
    uint16_t pose;
} VisionCommand;
typedef struct {
    uint8_t id;
    uint16_t cx10,cy10,width,height,number_age_ms,score1000;
} VisionTarget;
typedef struct {
    uint32_t command_seq,epoch,frame,captured_ms,command_age_ms;
    uint16_t algorithm_ms10,flags;
    uint8_t state,mode,count;
    VisionTarget targets[3];
} VisionSnapshot;
typedef struct {
    uint8_t bytes[VISION_MAX_FRAME];
    uint16_t used;
    uint32_t last_byte_ms,bad_crc,bad_header;
} VisionParser;
typedef struct {
    VisionParser parser;
    uint32_t session_id,expected_seq,last_frame,last_result_ms;
    uint8_t ready,have_frame,have_result;
    VisionCommand command;
    VisionSnapshot snapshot;
} VisionLink;

uint16_t vision_crc16(const uint8_t *data,size_t size);
void vision_link_init(VisionLink *link);
/* OPEN clears local observations. Use a different nonzero session after MCU reset/reconnect. */
size_t vision_link_open(VisionLink *link,uint32_t session_id,uint8_t *out,size_t capacity);
/* Send only after OPEN ACK (ready==1). New seq must increase; renew with a new seq. */
size_t vision_link_command(VisionLink *link,uint32_t seq,const VisionCommand *cmd,uint8_t *out,size_t capacity);
/* Call from one foreground owner, after draining a UART RX ring buffer. No HAL dependency. */
void vision_link_feed(VisionLink *link,const uint8_t *data,size_t size,uint32_t now_ms);
/* Copies zeroes and returns 0 after loss, mismatch or 350ms without a new result. */
int vision_link_get(VisionLink *link,uint32_t now_ms,VisionSnapshot *out);
/* Alignment observation only; this is never a complete grasp/motion authorization. */
int vision_link_can_align(VisionLink *link,uint32_t now_ms);
/* Optional bench receipt: report decoded frame/validity/first target back to K230. */
size_t vision_link_receipt(VisionLink *link,uint32_t now_ms,uint8_t *out,size_t capacity);
#endif
