"""
爬虫的窗口界面（tkinter，Python 自带，无需安装）。
布局：顶部输入网址，右侧"生成/清空"两个按钮，其余空间是大日志区，
爬虫的运行进度和生成的文件都会显示在这里。

本文件只定义界面。窗口由 main.py 的 launch_ui() 创建并运行。
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

import main   # 复用 main.py 里的爬虫，不复制代码

OUTPUT = "data.csv"   # 生成的主文件名，统计文件自动带 _daily / _keywords 后缀
PAGES = 3             # 网址里含 {}（翻页模板）时抓几页；不含 {} 就只抓这一个页面
FILES = [
    OUTPUT,
    OUTPUT.replace(".csv", "_daily.csv"),
    OUTPUT.replace(".csv", "_keywords.csv"),
]


class TextRedirector:
    """把 print() 的输出转发到窗口文本框，爬虫的进度就能在界面上看到。"""

    def __init__(self, widget):
        self.widget = widget

    def write(self, text):
        if text.strip():
            # after(): 让界面线程稍后更新文本框，爬虫在别的线程跑也不冲突
            self.widget.after(0, self._append, text)

    def _append(self, text):
        self.widget.insert("end", text.rstrip() + "\n")
        self.widget.see("end")   # 自动滚到底部

    def flush(self):
        pass


class CrawlerUI:
    def __init__(self, root):
        self.root = root
        root.title("新闻爬虫")
        root.geometry("800x600")

        # ── 顶部：网址输入行（矮） ──
        top = tk.Frame(root)
        top.pack(fill="x", padx=8, pady=6)
        tk.Label(top, text="网址：").pack(side="left")
        self.url_var = tk.StringVar()
        tk.Entry(top, textvariable=self.url_var).pack(side="left", fill="x", expand=True)

        # ── 主体：左边大日志区（大），右边按钮列（窄） ──
        body = tk.Frame(root)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log = scrolledtext.ScrolledText(body)
        self.log.pack(side="left", fill="both", expand=True)

        side = tk.Frame(body)
        side.pack(side="right", fill="y")
        self.btn_gen = tk.Button(side, text="生成", width=10, command=self.on_generate)
        self.btn_gen.pack(pady=(8, 4), padx=8)
        tk.Button(side, text="清空", width=10, command=self.on_clear).pack(pady=4, padx=8)

        sys.stdout = TextRedirector(self.log)
        self.log.insert("end",
                        "在上方输入网址后点【生成】。\n"
                        f"网址里含 {{}} 时按翻页模板抓 {PAGES} 页，否则只抓这一个页面。\n"
                        "解析用的选择器仍是 main.py 里 SITE 的配置。\n")

    def on_generate(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入网址")
            return
        self.btn_gen.config(state="disabled")   # 抓取期间禁用，防止重复点击
        threading.Thread(target=self._worker, args=(url,), daemon=True).start()

    def _worker(self, url):
        """爬虫放在子线程里跑，窗口才不会卡死几分钟。"""
        try:
            pages = PAGES if "{}" in url else 1
            main.run(url, pages, OUTPUT)     # 爬虫主体在 main.py，这里只负责调用
            done = "、".join(f for f in FILES if os.path.exists(f))
            print(f"\n生成完毕：{done}")
        except Exception as e:
            print(f"\n出错了：{e!r}")
        finally:
            self.root.after(0, lambda: self.btn_gen.config(state="normal"))

    def on_clear(self):
        """删除本次生成的 CSV 文件，并清空日志区。"""
        removed = []
        for f in FILES:
            if os.path.exists(f):
                os.remove(f)
                removed.append(f)
        self.log.delete("1.0", "end")
        if removed:
            print("已删除生成的文件：" + "、".join(removed))
        else:
            print("没有找到生成的 CSV 文件。")
