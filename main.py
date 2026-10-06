"""
新闻爬虫：抓取静态新闻列表页，解析标题/时间/正文，
清洗去重后存 CSV，并输出统计（每天多少条、关键词 Top20）。
"""

import argparse
import re
import sys
import time
from collections import Counter
from urllib.parse import urljoin, urlsplit

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ================= 站点配置：换个网站只改这里 =================
SITE = {
    "first_page": 1,                           # 从第几页开始
    "item": "div.content_list li",             # 列表页：每条新闻
    "title_link": "div.dd_bt a",               # 列表页：标题（含链接）
    "detail_title": "h1.content_left_title",   # 详情页：标题
    "detail_time": "div.news_source div.left", # 详情页：完整发布时间
    "detail_content": "div.left_zw",           # 详情页：正文
    "encoding": "utf-8",                       # 网页编码；填 None 则自动检测
    "delay": 0.5,                              # 每次请求间隔(秒)，别太快
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch(url, retries=3):
    """请求页面，返回 HTML 文本；失败自动重试，最终失败返回 None。"""
    for i in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if SITE["encoding"]:
                resp.encoding = SITE["encoding"]   # 关键：别让 requests 默认按 ISO-8859-1 解码
            else:
                resp.encoding = resp.apparent_encoding
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"    请求失败({i + 1}/{retries}): {e}")
            time.sleep(2)
    return None


def parse_list(html, base):
    """列表页 → [(标题, 详情页链接), ...]"""
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for li in soup.select(SITE["item"]):
        a = li.select_one(SITE["title_link"])
        if a and a.get_text(strip=True) and a.get("href"):
            title = a.get_text(strip=True)
            url = urljoin(base, a["href"])  # 相对路径转绝对路径
            entries.append((title, url))
    return entries


def parse_detail(html):
    """详情页 → (完整发布时间, 正文文本)"""
    soup = BeautifulSoup(html, "html.parser")
    t_node = soup.select_one(SITE["detail_time"])
    c_node = soup.select_one(SITE["detail_content"])
    raw_time = t_node.get_text(strip=True) if t_node else ""
    content = clean_text(c_node.get_text()) if c_node else ""
    return raw_time, content


def clean_text(text):
    """清洗：去 HTML 残留标签、把连续空白/换行/全角空格压成一个空格、去首尾空白。"""
    text = BeautifulSoup(text, "html.parser").get_text()  # 保险：处理转义实体
    return re.sub(r"\s+", " ", text).strip()


def to_date(raw_time):
    """'2026年10月06日 15:51:21' 或 '2026-10-6 15:51' → '2026-10-06'，解析失败返回空串。"""
    m = re.search(r"(\d{4})[年\-/.](\d{1,2})[月\-/.](\d{1,2})", raw_time)
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def crawl(list_url, pages):
    """主流程：翻页 → 去重 → 抓详情 → 汇总成列表。list_url 含 {} 时作为翻页模板。"""
    parts = urlsplit(list_url)
    base = f"{parts.scheme}://{parts.netloc}/"   # 域名从输入的网址自动提取
    rows = []
    seen_urls, seen_titles = set(), set()   # 去重用

    for page in range(SITE["first_page"], SITE["first_page"] + pages):
        url = list_url.format(page)
        html = fetch(url)
        if html is None:
            print(f"第{page}页请求失败，跳过")
            continue
        entries = parse_list(html, base)
        print(f"第{page}页：{len(entries)} 条")

        for title, link in entries:
            title = clean_text(title)
            if not title or title in seen_titles or link in seen_urls:
                continue                    # 去重：跳过已见过的标题和链接
            seen_titles.add(title)
            seen_urls.add(link)

            time.sleep(SITE["delay"])       # 礼貌间隔
            detail = fetch(link)
            raw_time, content = parse_detail(detail) if detail else ("", "")
            rows.append({
                "标题": title,
                "日期": to_date(raw_time),
                "发布时间": raw_time,
                "链接": link,
                "正文": content,
            })
            if len(rows) % 50 == 0:
                print(f"  已完成 {len(rows)} 条...")
    return rows


def stat_daily(df):
    """统计每天多少条，按日期排序。"""
    return df[df["日期"] != ""].groupby("日期").size().rename("条数").sort_index()


def stat_keywords(df, topn=20):
    """正文关键词 Top20（需要 jieba 分词）。"""
    try:
        import jieba
    except ImportError:
        print("（未安装 jieba，跳过关键词统计。安装：py -3.14 -m pip install jieba）")
        return []
    all_text = " ".join(df["正文"])
    words = [w for w in jieba.lcut(all_text)
             if len(w) >= 2 and not re.match(r"^[\d\W_]+$", w)]  # 去掉单字、纯数字/标点
    return Counter(words).most_common(topn)


def run(list_url, pages, output="data.csv"):
    """抓取 + 保存 + 统计。命令行和 UI 共用这一个入口。"""
    rows = crawl(list_url, pages)
    df = pd.DataFrame(rows, columns=["标题", "日期", "发布时间", "链接", "正文"])
    df.to_csv(output, index=False, encoding="utf-8-sig")  # utf-8-sig: Excel 打开不乱码
    print(f"\n共抓到 {len(df)} 条，已保存到 {output}")

    daily = stat_daily(df)
    daily.to_csv(output.replace(".csv", "_daily.csv"), encoding="utf-8-sig")
    print(f"\n—— 每天多少条 ——\n{daily.to_string()}")

    top = stat_keywords(df)
    if top:
        pd.DataFrame(top, columns=["关键词", "频次"]).to_csv(
            output.replace(".csv", "_keywords.csv"),
            index=False, encoding="utf-8-sig")
        print("\n—— 关键词 Top20 ——")
        for word, count in top:
            print(f"  {word}: {count}")
    return df


def main():
    parser = argparse.ArgumentParser(description="新闻爬虫")
    parser.add_argument("--url", required=True,
                        help="列表页网址，含 {} 可作为翻页模板")
    parser.add_argument("--pages", type=int, default=3, help="抓取列表页的页数")
    parser.add_argument("--output", default="data.csv", help="输出 CSV 文件名")
    args = parser.parse_args()
    run(args.url, args.pages, args.output)


def launch_ui():
    """主函数入口之一：创建窗口并进入消息循环。"""
    import tkinter as tk
    from ui import CrawlerUI
    root = tk.Tk()
    CrawlerUI(root)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()            # 带参数 → 命令行模式
    else:
        launch_ui()       # 不带参数 → 弹出窗口