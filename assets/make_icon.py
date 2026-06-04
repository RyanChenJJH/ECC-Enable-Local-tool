"""生成应用图标：渐变圆角方块 + 白色电源(启用)符号 + ECC 字样。
输出 assets/icon.ico(多尺寸) 与 assets/icon.png(用于 README)。
运行：python assets/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

S = 1024
OUT = Path(__file__).parent

# 1) 渐变底（teal -> indigo，逐行画）
top = (34, 211, 238)    # #22D3EE
bot = (99, 102, 241)    # #6366F1
grad = Image.new("RGB", (S, S))
gd = ImageDraw.Draw(grad)
for y in range(S):
    t = y / (S - 1)
    c = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3))
    gd.line([(0, y), (S, y)], fill=c)

# 2) 圆角方块裁切
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
img.paste(grad, (0, 0), mask)

d = ImageDraw.Draw(img)
white = (255, 255, 255, 255)

# 3) 电源符号（环留顶部缺口 + 竖条）= "启用"
cx, cy = S // 2, int(S * 0.45)
R = int(S * 0.21)
w = int(S * 0.055)
# 阴影
d.arc([cx - R + 6, cy - R + 8, cx + R + 6, cy + R + 8], start=300, end=600,
      fill=(20, 30, 80, 90), width=w)
# 环（缺口在正上方，约 270°）
d.arc([cx - R, cy - R, cx + R, cy + R], start=300, end=600, fill=white, width=w)
# 竖条
bw = w
d.rounded_rectangle([cx - bw // 2, cy - int(R * 1.18), cx + bw // 2, cy - int(R * 0.10)],
                    radius=bw // 2, fill=white)

# 4) ECC 字样
text = "ECC"
font = None
for fp in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf"):
    try:
        font = ImageFont.truetype(fp, int(S * 0.17))
        break
    except Exception:
        continue
if font is None:
    font = ImageFont.load_default()
bb = d.textbbox((0, 0), text, font=font)
tw, th = bb[2] - bb[0], bb[3] - bb[1]
d.text((cx - tw // 2 - bb[0], int(S * 0.76) - th // 2 - bb[1]), text, font=font, fill=white)

# 5) 输出
img.save(OUT / "icon.png")
img.save(OUT / "icon.ico", format="ICO",
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon.ico / icon.png 已生成于", OUT)
