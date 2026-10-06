/**
 ****************************************************************************************************
 * @file        lcd.c
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

/* Adaptation for the user's FMC NE1 / A18 / 16-bit H1 connector.
 * CubeMX owns HAL/MSP/GPIO/FMC/MPU/clock initialization.
 * No font, LTDC, touch, SDRAM framebuffer, DMA or printf dependencies.
 */
#include "lcd.h"

/* In 16-bit FMC mode external A18 is byte-address bit 19.
 * The original example's command alias 0x6007FFFE also selects RS = 0.
 * These explicit command/data addresses avoid reliance on a struct alias.
 */
#define LCD_REG16 (*(volatile uint16_t *)0x60000000UL)
#define LCD_RAM16 (*(volatile uint16_t *)0x60080000UL)

#define L2R_U2D 0
#define L2R_D2U 1
#define R2L_U2D 2
#define R2L_D2U 3
#define U2D_L2R 4
#define U2D_R2L 5
#define D2U_L2R 6
#define D2U_R2L 7
#define DFT_SCAN_DIR L2R_U2D

_lcd_dev lcddev;
volatile uint16_t g_lcd_raw_id;
volatile lcd_init_state_t g_lcd_init_state = LCD_INIT_NOT_STARTED;

void lcd_backlight(uint8_t enable)
{
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_5,
        (enable && g_lcd_init_state == LCD_INIT_READY)
        ? GPIO_PIN_SET : GPIO_PIN_RESET);
}


static void lcd_wr_data(volatile uint16_t data)
{
    data = data;            /* 使用-O2优化的时候,必须插入的延时 */
    LCD_RAM16 = data;
}

static void lcd_wr_regno(volatile uint16_t regno)
{
    regno = regno;          /* 使用-O2优化的时候,必须插入的延时 */
    LCD_REG16 = regno;   /* 写入要写的寄存器序号 */
}

static void lcd_write_reg(uint16_t regno, uint16_t data)
{
    LCD_REG16 = regno;   /* 写入要写的寄存器序号 */
    LCD_RAM16 = data;    /* 写入数据 */
}

static uint16_t lcd_rd_data(void)
{
    volatile uint16_t ram;  /* 防止被优化 */
    ram = LCD_RAM16;
    return ram;
}

static void lcd_write_ram_prepare(void)
{
    LCD_REG16 = lcddev.wramcmd;
}

static void lcd_set_cursor(uint16_t x, uint16_t y)
{
    if (lcddev.id == 0x1963)
    {
        if (lcddev.dir == 0)    /* 竖屏模式, x坐标需要变换 */
        {
            x = lcddev.width - 1 - x;
            lcd_wr_regno(lcddev.setxcmd);
            lcd_wr_data(0);
            lcd_wr_data(0);
            lcd_wr_data(x >> 8);
            lcd_wr_data(x & 0xFF);
        }
        else                    /* 横屏模式 */
        {
            lcd_wr_regno(lcddev.setxcmd);
            lcd_wr_data(x >> 8);
            lcd_wr_data(x & 0xFF);
            lcd_wr_data((lcddev.width - 1) >> 8);
            lcd_wr_data((lcddev.width - 1) & 0xFF);
        }

        lcd_wr_regno(lcddev.setycmd);
        lcd_wr_data(y >> 8);
        lcd_wr_data(y & 0xFF);
        lcd_wr_data((lcddev.height - 1) >> 8);
        lcd_wr_data((lcddev.height - 1) & 0xFF);
    }
    else if (lcddev.id == 0x5510)
    {
        lcd_wr_regno(lcddev.setxcmd);
        lcd_wr_data(x >> 8);
        lcd_wr_regno(lcddev.setxcmd + 1);
        lcd_wr_data(x & 0xFF);
        lcd_wr_regno(lcddev.setycmd);
        lcd_wr_data(y >> 8);
        lcd_wr_regno(lcddev.setycmd + 1);
        lcd_wr_data(y & 0xFF);
    }
    else    /* 9341/5310/7789 等 设置坐标 */
    {
        lcd_wr_regno(lcddev.setxcmd);
        lcd_wr_data(x >> 8);
        lcd_wr_data(x & 0xFF);
        lcd_wr_regno(lcddev.setycmd);
        lcd_wr_data(y >> 8);
        lcd_wr_data(y & 0xFF);
    }
}

static void lcd_scan_dir(uint8_t dir)
{
    uint16_t regval = 0;
    uint16_t dirreg = 0;
    uint16_t temp;

    /* 横屏时，对1963不改变扫描方向！竖屏时1963改变方向(这里仅用于1963的特殊处理,对其他驱动IC无效) */
    if ((lcddev.dir == 1 && lcddev.id != 0x1963) || (lcddev.dir == 0 && lcddev.id == 0x1963))
    {
        switch (dir)   /* 方向转换 */
        {
            case 0:
                dir = 6;
                break;

            case 1:
                dir = 7;
                break;

            case 2:
                dir = 4;
                break;

            case 3:
                dir = 5;
                break;

            case 4:
                dir = 1;
                break;

            case 5:
                dir = 0;
                break;

            case 6:
                dir = 3;
                break;

            case 7:
                dir = 2;
                break;
        }
    }

    /* 根据扫描方式 设置 0x36/0x3600 寄存器 bit 5,6,7 位的值 */
    switch (dir)
    {
        case L2R_U2D:       /* 从左到右,从上到下 */
            regval |= (0 << 7) | (0 << 6) | (0 << 5);
            break;

        case L2R_D2U:       /* 从左到右,从下到上 */
            regval |= (1 << 7) | (0 << 6) | (0 << 5);
            break;

        case R2L_U2D:       /* 从右到左,从上到下 */
            regval |= (0 << 7) | (1 << 6) | (0 << 5);
            break;

        case R2L_D2U:       /* 从右到左,从下到上 */
            regval |= (1 << 7) | (1 << 6) | (0 << 5);
            break;

        case U2D_L2R:       /* 从上到下,从左到右 */
            regval |= (0 << 7) | (0 << 6) | (1 << 5);
            break;

        case U2D_R2L:       /* 从上到下,从右到左 */
            regval |= (0 << 7) | (1 << 6) | (1 << 5);
            break;

        case D2U_L2R:       /* 从下到上,从左到右 */
            regval |= (1 << 7) | (0 << 6) | (1 << 5);
            break;

        case D2U_R2L:       /* 从下到上,从右到左 */
            regval |= (1 << 7) | (1 << 6) | (1 << 5);
            break;
    }

    dirreg = 0x36;          /* 对绝大部分驱动IC, 由0x36寄存器控制 */

    if (lcddev.id == 0x5510)
    {
        dirreg = 0x3600;    /* 对于5510, 和其他驱动ic的寄存器有差异 */
    }

     /* 9341 & 7789 & 7796 要设置BGR位 */
    if (lcddev.id == 0x9341 || lcddev.id == 0x7789 || lcddev.id == 0x7796)
    {
        regval |= 0x08;
    }

    lcd_write_reg(dirreg, regval);

    if (lcddev.id != 0x1963)                    /* 1963不做坐标处理 */
    {
        if (regval & 0x20)
        {
            if (lcddev.width < lcddev.height)   /* 交换X,Y */
            {
                temp = lcddev.width;
                lcddev.width = lcddev.height;
                lcddev.height = temp;
            }
        }
        else
        {
            if (lcddev.width > lcddev.height)   /* 交换X,Y */
            {
                temp = lcddev.width;
                lcddev.width = lcddev.height;
                lcddev.height = temp;
            }
        }
    }

    /* 设置显示区域(开窗)大小 */
    if (lcddev.id == 0x5510)
    {
        lcd_wr_regno(lcddev.setxcmd);
        lcd_wr_data(0);
        lcd_wr_regno(lcddev.setxcmd + 1);
        lcd_wr_data(0);
        lcd_wr_regno(lcddev.setxcmd + 2);
        lcd_wr_data((lcddev.width - 1) >> 8);
        lcd_wr_regno(lcddev.setxcmd + 3);
        lcd_wr_data((lcddev.width - 1) & 0xFF);
        lcd_wr_regno(lcddev.setycmd);
        lcd_wr_data(0);
        lcd_wr_regno(lcddev.setycmd + 1);
        lcd_wr_data(0);
        lcd_wr_regno(lcddev.setycmd + 2);
        lcd_wr_data((lcddev.height - 1) >> 8);
        lcd_wr_regno(lcddev.setycmd + 3);
        lcd_wr_data((lcddev.height - 1) & 0xFF);
    }
    else
    {
        lcd_wr_regno(lcddev.setxcmd);
        lcd_wr_data(0);
        lcd_wr_data(0);
        lcd_wr_data((lcddev.width - 1) >> 8);
        lcd_wr_data((lcddev.width - 1) & 0xFF);
        lcd_wr_regno(lcddev.setycmd);
        lcd_wr_data(0);
        lcd_wr_data(0);
        lcd_wr_data((lcddev.height - 1) >> 8);
        lcd_wr_data((lcddev.height - 1) & 0xFF);
    }
}

static void lcd_ssd_backlight_set(uint8_t pwm)
{
    lcd_wr_regno(0xBE);             /* 配置PWM输出 */
    lcd_wr_data(0x05);              /* 1设置PWM频率 */
    lcd_wr_data(pwm * 2.55);        /* 2设置PWM占空比 */
    lcd_wr_data(0x01);              /* 3设置C */
    lcd_wr_data(0xFF);              /* 4设置D */
    lcd_wr_data(0x00);              /* 5设置E */
    lcd_wr_data(0x00);              /* 6设置F */
}

static void lcd_display_dir(uint8_t dir)
{
    lcddev.dir = dir;               /* 竖屏/横屏 */

    if (dir == 0)                   /* 竖屏 */
    {
        lcddev.width = 240;
        lcddev.height = 320;

        if (lcddev.id == 0x5510)
        {
            lcddev.wramcmd = 0x2C00;
            lcddev.setxcmd = 0x2A00;
            lcddev.setycmd = 0x2B00;
            lcddev.width = 480;
            lcddev.height = 800;
        }
        else if (lcddev.id == 0x1963)
        {
            lcddev.wramcmd = 0x2C;  /* 设置写入GRAM的指令 */
            lcddev.setxcmd = 0x2B;  /* 设置写X坐标指令 */
            lcddev.setycmd = 0x2A;  /* 设置写Y坐标指令 */
            lcddev.width = 480;     /* 设置宽度480 */
            lcddev.height = 800;    /* 设置高度800 */
        }
        else                        /* 其他IC, 包括: 9341/5310/7789/7796/9806等IC */
        {
            lcddev.wramcmd = 0x2C;
            lcddev.setxcmd = 0x2A;
            lcddev.setycmd = 0x2B;
        }

        if (lcddev.id == 0x5310 || lcddev.id == 0x7796)     /* 如果是5310/7796 则表示是 320*480分辨率 */
        {
            lcddev.width = 320;
            lcddev.height = 480;
        }         
        if (lcddev.id == 0X9806)    /* 如果是9806 则表示是 480*800 分辨率 */
        {
            lcddev.width = 480;
            lcddev.height = 800;
        }
    }                               /* dir = 0 */
    else                            /* 横屏 */
    {
        lcddev.width = 320;         /* 默认宽度 */
        lcddev.height = 240;        /* 默认高度 */

        if (lcddev.id == 0x5510)
        {
            lcddev.wramcmd = 0x2C00;
            lcddev.setxcmd = 0x2A00;
            lcddev.setycmd = 0x2B00;
            lcddev.width = 800;
            lcddev.height = 480;
        }
        else if (lcddev.id == 0x1963 || lcddev.id == 0x9806)
        {
            lcddev.wramcmd = 0x2C;  /* 设置写入GRAM的指令 */
            lcddev.setxcmd = 0x2A;  /* 设置写X坐标指令 */
            lcddev.setycmd = 0x2B;  /* 设置写Y坐标指令 */
            lcddev.width = 800;     /* 设置宽度800 */
            lcddev.height = 480;    /* 设置高度480 */
        }
        else                        /* 其他IC, 包括:9341/5310/7789/7796等IC */
        {
            lcddev.wramcmd = 0x2C;
            lcddev.setxcmd = 0x2A;
            lcddev.setycmd = 0x2B;
        }

        if (lcddev.id == 0x5310 || lcddev.id == 0x7796)     /* 如果是5310/7796 则表示是 320*480分辨率 */
        {
            lcddev.width = 480;
            lcddev.height = 320;
        }
    }

    lcd_scan_dir(DFT_SCAN_DIR);     /* 默认扫描方向 */
}

#include "lcd_controller_init.inc"

HAL_StatusTypeDef lcd_init(void)
{
    lcd_backlight(0);
    g_lcd_init_state = LCD_INIT_PROBING;
    g_lcd_raw_id = 0;
    lcddev.id = 0;
    lcddev.width = 0;
    lcddev.height = 0;
    lcddev.dir = 0;
    lcddev.wramcmd = 0;
    lcddev.setxcmd = 0;
    lcddev.setycmd = 0;
    HAL_Delay(50);

    /* 尝试9341 ID的读取 */
    lcd_wr_regno(0xD3);
    lcddev.id = lcd_rd_data();          /* dummy read */
    lcddev.id = lcd_rd_data();          /* 读到0x00 */
    lcddev.id = lcd_rd_data();          /* 读取93 */
    lcddev.id <<= 8;
    lcddev.id |= lcd_rd_data();         /* 读取41 */

    if (lcddev.id != 0x9341)            /* 不是 9341 , 尝试看看是不是 ST7789 */
    {
        lcd_wr_regno(0x04);
        lcddev.id = lcd_rd_data();      /* dummy read */
        lcddev.id = lcd_rd_data();      /* 读到0x85 */
        lcddev.id = lcd_rd_data();      /* 读取0x85 */
        lcddev.id <<= 8;
        lcddev.id |= lcd_rd_data();     /* 读取0x52 */
        
        g_lcd_raw_id = lcddev.id;
        if (lcddev.id == 0x8552)        /* 将8552的ID转换成7789 */
        {
            lcddev.id = 0x7789;
        }

        if (lcddev.id != 0x7789)        /* 也不是ST7789, 尝试是不是 NT35310 */
        {
            lcd_wr_regno(0xD4);
            lcddev.id = lcd_rd_data();  /* dummy read */
            lcddev.id = lcd_rd_data();  /* 读回0x01 */
            lcddev.id = lcd_rd_data();  /* 读回0x53 */
            lcddev.id <<= 8;
            lcddev.id |= lcd_rd_data(); /* 这里读回0x10 */

            if (lcddev.id != 0x5310)    /* 也不是NT35310,尝试看看是不是ST7796 */
            {
                lcd_wr_regno(0XD3);
                lcddev.id = lcd_rd_data();  /* dummy read */
                lcddev.id = lcd_rd_data();  /* 读到0X00 */
                lcddev.id = lcd_rd_data();  /* 读取0X77 */
                lcddev.id <<= 8;
                lcddev.id |= lcd_rd_data(); /* 读取0X96 */
                
                if (lcddev.id != 0x7796)    /* 也不是ST7796,尝试看看是不是NT35510 */
                {
                    /* 发送密钥（厂家提供） */
                    lcd_write_reg(0xF000, 0x0055);
                    lcd_write_reg(0xF001, 0x00AA);
                    lcd_write_reg(0xF002, 0x0052);
                    lcd_write_reg(0xF003, 0x0008);
                    lcd_write_reg(0xF004, 0x0001);
                    
                    lcd_wr_regno(0xC500);       /* 读取ID低八位 */
                    lcddev.id = lcd_rd_data();  /* 读回0x80 */
                    lcddev.id <<= 8;

                    lcd_wr_regno(0xC501);       /* 读取ID高八位 */
                    lcddev.id |= lcd_rd_data(); /* 读回0x00 */
                    HAL_Delay(5);                /* 等待5ms, 因为0XC501指令对1963来说就是软件复位指令, 等待5ms让1963复位完成再操作 */


                    if (lcddev.id != 0x5510)    /* 也不是NT5510,尝试看看是不是ILI9806 */
                    {
                        lcd_wr_regno(0XD3);
                        lcddev.id = lcd_rd_data();  /* dummy read */
                        lcddev.id = lcd_rd_data();  /* 读回0X00 */
                        lcddev.id = lcd_rd_data();  /* 读回0X98 */
                        lcddev.id <<= 8;
                        lcddev.id |= lcd_rd_data(); /* 读回0X06 */
                        
                        if (lcddev.id != 0x9806)    /* 也不是ILI9806,尝试看看是不是SSD1963 */
                        {
                            lcd_wr_regno(0xA1);
                            lcddev.id = lcd_rd_data();
                            lcddev.id = lcd_rd_data();  /* 读回0x57 */
                            lcddev.id <<= 8;
                            lcddev.id |= lcd_rd_data(); /* 读回0x61 */

                            g_lcd_raw_id = lcddev.id;
                            if (lcddev.id == 0x5761)lcddev.id = 0x1963; /* SSD1963读回的ID是5761H,为方便区分,我们强制设置为1963 */
                        }
                    }
                }
            }
        }
    }

    /* Preserve normalized and raw IDs separately for the Keil Watch window. */
    if (lcddev.id != 0x7789 && lcddev.id != 0x1963)
    {
        g_lcd_raw_id = lcddev.id;
    }

    switch (lcddev.id)
    {
        case 0x7789: lcd_ex_st7789_reginit(); break;
        case 0x9341: lcd_ex_ili9341_reginit(); break;
        case 0x5310: lcd_ex_nt35310_reginit(); break;
        case 0x7796: lcd_ex_st7796_reginit(); break;
        case 0x5510: lcd_ex_nt35510_reginit(); break;
        case 0x9806: lcd_ex_ili9806_reginit(); break;
        case 0x1963:
            lcd_ex_ssd1963_reginit();
            lcd_ssd_backlight_set(100);
            break;
        default:
            g_lcd_init_state = LCD_INIT_UNKNOWN_ID;
            return HAL_ERROR;
    }

    lcd_display_dir(1); /* Original example's landscape command/dimension logic. */
    /* Diagnostic: use the dimensions selected by the recognized controller. */
    if (lcddev.width == 0 || lcddev.height == 0)
    {
        g_lcd_init_state = LCD_INIT_UNEXPECTED_SIZE;
        return HAL_ERROR;
    }

    /* Keep the conservative CubeMX FMC timings; no direct timing rewrite. */
    g_lcd_init_state = LCD_INIT_READY;
    return HAL_OK;
}

void lcd_clear(uint16_t color)
{
    uint32_t index = 0;
    uint32_t totalpoint = lcddev.width;

    if (g_lcd_init_state != LCD_INIT_READY)
    {
        return;
    }

    totalpoint *= lcddev.height;               /* 得到总点数 */
    lcd_set_cursor(0x00, 0x0000);              /* 设置光标位置 */
    lcd_write_ram_prepare();                   /* 开始写入GRAM */

    for (index = 0; index < totalpoint; index++)
    {
        LCD_RAM16 = color;
    }
}
