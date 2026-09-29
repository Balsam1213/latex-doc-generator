"""首次运行引导：未配置 API Key 时，启动服务前弹出图形化设置窗口。

- 已配置 → 直接返回，不弹窗（之后永不重复提示）
- 配置成功写入 .env，立即生效，无需重启
- tkinter 不可用（异常环境）时回退为控制台输入
"""
import sys
import webbrowser

ZHIPU_HOME = "https://open.bigmodel.cn"


def ensure_api_key() -> bool:
    """确保已配置 Key；返回 False 表示用户放弃，调用方应退出程序。"""
    from . import config

    if config.llm_configured():
        return True
    try:
        return _gui_prompt(config)
    except Exception:
        # 无 GUI 环境（如某些精简 Python）时退回控制台
        try:
            return _console_prompt(config)
        except Exception:
            return False


def _save(config, key: str) -> bool:
    try:
        config.save_env_value("LLM_API_KEY", key.strip())
    except OSError:
        return False
    return config.llm_configured()


def _gui_prompt(config) -> bool:
    import tkinter as tk

    ok = {"v": False}
    root = tk.Tk()
    root.title("LaTeX 文档生成器 · 首次设置")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    w, h = 470, 340
    root.update_idletasks()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.configure(bg="white")

    frm = tk.Frame(root, bg="white", padx=20, pady=14)
    frm.pack(fill="both", expand=True)

    tk.Label(frm, text="🎉 欢迎使用 LaTeX 文档生成器",
             font=("Microsoft YaHei", 13, "bold"), bg="white").pack(anchor="w")
    tk.Label(frm, text="首次使用需要一个智谱 AI 的 API Key（永久免费档可用）：",
             font=("Microsoft YaHei", 10), bg="white").pack(anchor="w", pady=(6, 4))

    link = tk.Label(frm, text="① 打开智谱开放平台：open.bigmodel.cn（点击打开）",
                    fg="#3b6cf5", cursor="hand2", bg="white",
                    font=("Microsoft YaHei", 10, "underline"))
    link.pack(anchor="w", pady=2)
    link.bind("<Button-1>", lambda e: webbrowser.open(ZHIPU_HOME))

    tk.Label(frm, text="② 登录后进入「控制台 → API Keys」，点击「创建 API Key」并复制",
             font=("Microsoft YaHei", 10), bg="white").pack(anchor="w", pady=2)
    tk.Label(frm, text="③ 把 Key 粘贴到下面（只保存在本机 .env 文件中）：",
             font=("Microsoft YaHei", 10), bg="white").pack(anchor="w", pady=(6, 3))

    entry = tk.Entry(frm, font=("Consolas", 11), relief="solid", bd=1)
    entry.pack(fill="x", ipady=5)

    status = tk.Label(frm, text="", fg="#d23b3b", bg="white",
                      font=("Microsoft YaHei", 9), wraplength=420, justify="left")
    status.pack(anchor="w", pady=(6, 2))

    btns = tk.Frame(frm, bg="white")
    btns.pack(fill="x", pady=(10, 0))

    def on_save(event=None):
        key = entry.get().strip()
        if not key or "在此填入" in key:
            status.config(text="请先粘贴有效的 API Key")
            return
        if _save(config, key):
            ok["v"] = True
            root.destroy()
        else:
            status.config(text="保存失败：请检查项目目录是否可写")

    def on_quit():
        root.destroy()

    tk.Button(btns, text="保存并继续", command=on_save, bg="#3b6cf5", fg="white",
              activebackground="#2c56d4", activeforeground="white",
              font=("Microsoft YaHei", 10, "bold"), padx=16, pady=5,
              relief="flat", cursor="hand2").pack(side="right")
    tk.Button(btns, text="退出程序", command=on_quit,
              font=("Microsoft YaHei", 10), padx=12, pady=5).pack(side="right", padx=10)

    entry.focus_set()
    entry.bind("<Return>", on_save)
    root.protocol("WM_DELETE_WINDOW", on_quit)
    root.mainloop()
    return ok["v"]


def _console_prompt(config) -> bool:
    print("=" * 52)
    print(" 首次使用：请配置智谱 API Key（免费）")
    print(f" 1. 访问 {ZHIPU_HOME} 注册/登录")
    print(" 2. 控制台 → API Keys → 创建 API Key")
    print(" 3. 把 Key 粘贴到下面后回车（保存到本机 .env）")
    print("=" * 52)
    for _ in range(3):
        try:
            key = input("API Key: ").strip()
        except EOFError:
            return False
        if key and _save(config, key):
            return True
        print("输入无效，请重试。")
    return False
