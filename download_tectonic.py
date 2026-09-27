"""可选工具：自动下载最新版 Tectonic 到 vendor/ 目录。

用法：python download_tectonic.py
如果你已经手动下载并把 tectonic.exe 放进了 vendor/，则无需运行。
注意：需要能访问 GitHub；国内网络可能需要设置代理（如 HTTPS_PROXY 环境变量）。
"""
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

VENDOR = Path(__file__).parent / "vendor"
TARGET_ASSET = "x86_64-pc-windows-msvc.zip"
API_URL = "https://api.github.com/repos/tectonic-typesetting/tectonic/releases/latest"


def main() -> None:
    VENDOR.mkdir(exist_ok=True)
    if (VENDOR / "tectonic.exe").is_file():
        print("vendor/tectonic.exe 已存在，无需下载。")
        return

    print("查询最新版本…")
    with urllib.request.urlopen(API_URL, timeout=30) as r:
        release = json.load(r)

    asset = next((a for a in release["assets"] if a["name"] == TARGET_ASSET), None)
    if not asset:
        sys.exit(
            f"未在最新 Release 中找到 {TARGET_ASSET}，"
            "请到 https://github.com/tectonic-typesetting/tectonic/releases 手动下载。"
        )

    print(f"下载 {asset['name']}（{asset['size'] / 1e6:.1f} MB）…")
    with urllib.request.urlopen(asset["browser_download_url"], timeout=300) as r:
        data = r.read()

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extract("tectonic.exe", VENDOR)
    print("已保存到 vendor/tectonic.exe ✔")


if __name__ == "__main__":
    main()
