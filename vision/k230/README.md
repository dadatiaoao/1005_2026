# K230 智能搬运视觉程序

2026-10-16 源码快照，适配本项目 01Studio CanMV K230 + GC2093 单摄像头。图像尺寸640×480，使用 CanMV 固件内置的 `media`、`ulab`、`cv2`、`machine`；不是桌面 OpenCV 程序。

## 当前能力与限制

- MATERIAL：红、黄、蓝、绿、黑、浅蓝六色候选，按主控指定颜色输出像素中心。
- RING：同心环最内环定位，识别印刷数字1/2/3，可按实际编号选择目标；编号不是左右顺序。
- 同一程序按串口命令切模式、ROI和目标；目标丢失、命令超时及模式切换会清空旧坐标。
- 已有屏幕测试卡和两板台架测试记录；本次上传只做主机检查，没有重新连接或运行硬件。
- **尚未完成实车颜色、镜头/工作平面、机械臂姿态与夹爪偏置标定。当前输出是像素坐标，`calibrated=false`、`usable_for_alignment=false`，不是自动抓取许可。**
- 仅包含视觉与通信，不含扫码模块、K210、底盘或机械臂运动程序。

## 部署到 K230

1. 先备份SD卡原有 `main.py`、`boot.py` 及同名模块。
2. 将本目录根部的13个 `.py` 文件复制到K230的 `/sdcard/`，保持同一目录。不要把整个 `vision/k230` 层级直接复制进去。
3. 首次调试先运行 `/sdcard/vision_uart_entry.py`；调通后再放置 `main.py` 启用上电启动。`main.py` 等待5秒后启动串口视觉入口。
4. 在 `/sdcard/` 创建空文件 `vision_autostart.off` 可禁用自启；删除它恢复。异常信息尽可能记录到 `vision_autostart_error.txt`。
5. 启动后等待H743发送OPEN及COMMAND；没有主控指令时不自动选择检测任务。

## 接线与协议

115200、8N1，3.3V TTL。两板分别供电并共地。

| K230 | H743 |
|---|---|
| IO5 / 40针排针第11脚，UART2 TX | PA3 / USART2 RX |
| IO6 / 第12脚，UART2 RX | PA2 / USART2 TX |
| GND，例如第14脚 | GND |

协议为 A5 5A 帧头、版本1、session/seq、CRC16-CCITT。先OPEN建立新会话，再COMMAND；新序号续期。主控参考每500ms续期、lease=2000ms。详细字段见 [串口协议与接线说明](docs/串口协议与接线说明.md)。该文档保留了原台架工程路径描述，这些历史工程未包含在本包中。

`stm32/vision_link.c/.h` 是当前主程序使用的纯C协议参考实现，需由主控工程接入UART收发和毫秒时钟；不能仅复制文件就宣称完成HAL接入。请勿把观测有效位当作标定/抓取许可。

## 文件与测试

- `main.py` → `vision_uart_entry.py` → `vision_unified.py`：自启、UART引脚、相机与模式管理。
- `six_color_*`、`material_session.py`：颜色筛选及连续确认。
- `ring_locator.py`、`ring_digits.py`、`digit_templates.py`、`number_schedule.py`：内环定位、数字模板及轮流识别。
- `vision_session.py`、`vision_uart.py`、`vision_wire.py`：模式路由、失效处理与串口成帧。
- `test_cards/`：三圆环2/1/3、六色卡、空白卡，仅作台架辅助。
- `tests/`：不接触硬件的协议、模式切换和自启保护检查。

在电脑安装Python后，于本目录执行：

```shell
python tests/run_host_checks.py
```

颜色阈值仍为演示参数；更换照明、实物、高度或摄像头后需要现场重新验证。主机检查不证明真实识别率、串口电气可靠性或比赛全流程完成。

`manifest.json` 记录交付文件SHA256，`tests/host_check_results.json` 记录本次主机检查。未包含原始串口日志、电脑路径配置、其他模块草稿或旧版本压缩包。
