/**
 ****************************************************************************************************
 * @file        lcd.h
 * @author      正点原子团队(ALIENTEK)
 * @version     V1.1
 * @date        2022-09-06
 * @brief       2.8寸/3.5寸/4.3寸/7寸 TFTLCD(MCU屏) 驱动代码
 *              支持驱动IC型号包括:ILI9341/NT35310/NT35510/SSD1963/ST7789/ST7796/ILI9806等
 *
 * @license     Copyright (c) 2020-2032, 广州市星翼电子科技有限公司
 ****************************************************************************************************
 * @attention
 *
 * 实验平台:正点原子 阿波罗 H743开发板
 * 在线视频:www.yuanzige.com
 * 技术论坛:www.openedv.com
 * 公司网址:www.alientek.com
 * 购买地址:openedv.taobao.com
 *
 * 修改说明
 * V1.0 20220906
 * 第一次发布
 * V1.1 20230607
 * 新增对ST7796和ILI9806 IC支持
 *
 ****************************************************************************************************
 */

/* CubeMX integration: only HAL headers and the existing FMC/GPIO/MPU setup. */
#ifndef LCD_MINIMAL_H
#define LCD_MINIMAL_H

#include "stm32h7xx_hal.h"

typedef struct
{
    uint16_t width;
    uint16_t height;
    uint16_t id;
    uint8_t dir;
    uint16_t wramcmd;
    uint16_t setxcmd;
    uint16_t setycmd;
} _lcd_dev;

typedef enum
{
    LCD_INIT_NOT_STARTED = 0,
    LCD_INIT_PROBING = 1,
    LCD_INIT_UNKNOWN_ID = 2,
    LCD_INIT_UNEXPECTED_SIZE = 3,
    LCD_INIT_READY = 4
} lcd_init_state_t;

extern _lcd_dev lcddev;
extern volatile uint16_t g_lcd_raw_id;
extern volatile lcd_init_state_t g_lcd_init_state;

#define LCD_COLOR_BLACK 0x0000U
#define LCD_COLOR_WHITE 0xFFFFU
#define LCD_COLOR_RED   0xF800U
#define LCD_COLOR_GREEN 0x07E0U
#define LCD_COLOR_BLUE  0x001FU

/* Requires MX_GPIO_Init(), MX_FMC_Init(), MPU permissions and a live HAL tick. */
/* Keeps PB5 low, detects the controller and initializes 800 x 480 landscape. */
HAL_StatusTypeDef lcd_init(void);
/* Valid only after lcd_init() returns HAL_OK. Uses the controller's own RAM. */
void lcd_clear(uint16_t color);
/* PB5 gate. Enabling is permitted only after a successful initialization. */
void lcd_backlight(uint8_t enable);

#endif
