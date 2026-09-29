"""生成桌面快捷方式：双击「LaTeX 文档生成器」即可无窗口启动服务并打开页面。

用法：python make_shortcut.py
快捷方式指向 pythonw + start_app.pyw（不出现命令提示符窗口）；
停止服务用页面右上角「退出服务」按钮（控制台方式启动则直接关窗口）。
会同时生成程序图标 app.ico（需要 Pillow，未安装则使用默认图标）。
"""
import base64
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICON = ROOT / "app.ico"
SHORTCUT_NAME = "LaTeX 文档生成器.lnk"


def make_icon() -> bool:
    """用 Pillow 画一个蓝底白字 TeX 图标并保存为 app.ico。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("未安装 Pillow，跳过图标生成（快捷方式将使用默认图标）。")
        return False

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=56, fill=(59, 108, 245, 255))

    text = "TeX"
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 88)
    except OSError:
        font = ImageFont.load_default()
    left, top, right, bottom = d.textbbox((0, 0), text, font=font)
    d.text(((size - (right - left)) / 2 - left, (size - (bottom - top)) / 2 - top),
           text, font=font, fill=(255, 255, 255, 255))

    img.save(ICON, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"图标已生成：{ICON}")
    return True


def create_shortcut() -> None:
    # 优先用 pythonw（无控制台窗口）；不存在则退回 python
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    launcher = pythonw if pythonw.is_file() else Path(sys.executable)
    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = $ws.CreateShortcut((Join-Path $desktop '{SHORTCUT_NAME}'))
$lnk.TargetPath = '{launcher}'
$lnk.Arguments = '"{ROOT / "start_app.pyw"}"'
$lnk.WorkingDirectory = '{ROOT}'
$lnk.IconLocation = '{ICON},0'
$lnk.Description = 'LaTeX 文档生成器 - 无窗口启动服务并打开页面（退出：页面右上角按钮）'
$lnk.Save()
Write-Output ("已创建快捷方式: " + (Join-Path $desktop '{SHORTCUT_NAME}'))
"""
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode()
    result = subprocess.run(
        ["powershell", "-NoProfile", "-EncodedCommand", encoded],
        capture_output=True,
    )
    # PowerShell 控制台输出为系统 ANSI 编码（中文 Windows 为 GBK）
    enc = "mbcs" if sys.platform == "win32" else "utf-8"
    out = (result.stdout or b"").decode(enc, errors="replace")
    err = (result.stderr or b"").decode(enc, errors="replace")
    if result.returncode != 0:
        sys.exit(f"创建快捷方式失败：{err.strip()}")
    print(out.strip())


if __name__ == "__main__":
    make_icon()
    create_shortcut()
