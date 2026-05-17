from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ICO_OUT = ROOT / "assets" / "inversoria_launcher.ico"
PNG_OUT = ROOT / "assets" / "inversoria_logo.png"


def draw_logo():
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((0, 0, size, size), radius=220, fill="#070B12")
    draw.ellipse((156, 156, 868, 868), fill="#0B1220", outline="#10B981", width=28)
    draw.ellipse((254, 254, 770, 770), fill="#111827", outline="#1F2937", width=18)

    points = [(268, 650), (406, 486), (516, 548), (704, 324)]
    draw.line(points, fill="#A7F3D0", width=72, joint="curve")
    for idx, point in enumerate(points):
        color = "#10B981" if idx % 2 == 0 else "#34D399"
        x, y = point
        draw.ellipse((x - 46, y - 46, x + 46, y + 46), fill=color)

    draw.line((315, 752, 709, 752), fill="#064E3B", width=36)
    for line in [(512, 184, 512, 252), (512, 772, 512, 840), (184, 512, 252, 512), (772, 512, 840, 512)]:
        draw.line(line, fill="#34D399", width=28)
    return img

def make_icon():
    img = draw_logo()
    ICO_OUT.parent.mkdir(exist_ok=True)
    img.save(PNG_OUT, format="PNG")
    img.save(
        ICO_OUT,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(PNG_OUT)
    print(ICO_OUT)


if __name__ == "__main__":
    make_icon()
