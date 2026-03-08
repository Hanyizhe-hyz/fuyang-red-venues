import os
import json
from datetime import date, datetime

import streamlit as st
import requests
import pandas as pd
import qrcode
from io import BytesIO
st.set_page_config(page_title="阜阳红色场馆管理平台", layout="wide")

# =========================
# 0) 配置：API 兜底 + 本地持久化
# =========================
# 将来如果拿到“安徽红旅”等平台接口，把环境变量 RED_TOUR_API_URL 配上即可
# Windows PowerShell:
#   $env:RED_TOUR_API_URL="https://example.com/api/venues"
API_URL = os.environ.get("RED_TOUR_API_URL", "").strip()
API_TIMEOUT = 3  # 秒

DATA_JSON = "venues.json"  # 本地持久化文件（同目录）
ORDERS_JSON = "orders.json"

# =========================
# 1) 本地默认数据（API/JSON 都失败才用它）
# =========================
VENUES_LOCAL = [
    {
        "id": 1,
        "name": "四九起义纪念馆",
        "desc": "展陈阜阳地区革命历史、人物与重要事件，适合研学与主题团日。",
        "address": "安徽省阜阳市颍泉区行流镇王官集行政村",
        "phone": "(0558)8624435",
        "status": "开放",
        "hours": "8：00-11：30，14：30—17：30，双休日9：00—17：00（中午不休息）；周一闭馆。",
        "price": 0,
        "lat": 32.8890,
        "lng": 115.8140,
    },
    {
        "id": 2,
        "name": "临泉挺近大别山纪念馆",
        "desc": "旧址复原+讲解，支持研学预约与团体参观。",
        "address": "安徽省阜阳市临泉县韦寨镇吴营村",
        "phone": "0558-5872546",
        "status": "开放",
        "hours": "周三至周日 09:30-16:30",
        "price": 20,
        "lat": 32.9000,
        "lng": 115.8300,
    },
    {
        "id": 3,
        "name": "王家坝抗洪纪念馆",
        "desc": "纪念园区+纪念碑+主题展陈",
        "address": "阜阳市阜南县王家坝镇",
        "phone": "0558-1245614",
        "status": "开放",
        "hours": "周一闭园；其余 08:30-17:30",
        "price": 10,
        "lat": 32.8750,
        "lng": 115.7900,
    },
]

HOTLINE = "0558-1234567"  # 平台统一客服电话（可改成真实电话）


# =========================
# 2) 数据源：API 优先 -> venues.json -> 本地默认
# =========================
def _normalize_venue(v: dict) -> dict:
    """把外部接口/CSV 的字段统一成平台字段"""
    return {
        "id": int(v.get("id", 0) or 0),
        "name": str(v.get("name", "") or ""),
        "desc": str(v.get("desc", "") or ""),
        "address": str(v.get("address", "") or ""),
        "phone": str(v.get("phone", "") or ""),
        "status": str(v.get("status", "开放") or "开放"),
        "hours": str(v.get("hours", "") or ""),
        "price": float(v.get("price", 0) or 0),
        "lat": float(v.get("lat", 0) or 0),
        "lng": float(v.get("lng", 0) or 0),
    }


def _basic_validate(venues: list[dict]) -> list[dict]:
    """基本校验：必须有 name、lat、lng；状态必须合法"""
    ok_status = {"开放", "闭馆", "维护中"}
    res = []
    for v in venues:
        vv = _normalize_venue(v)
        if not vv["name"]:
            continue
        if vv["lat"] == 0 or vv["lng"] == 0:
            continue
        if vv["status"] not in ok_status:
            vv["status"] = "开放"
        res.append(vv)
    return res


@st.cache_data(ttl=300)
def _load_from_api(api_url: str):
    """从外部 API 拉取场馆数据；失败返回 None"""
    if not api_url:
        return None
    try:
        r = requests.get(api_url, timeout=API_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return None
        venues = _basic_validate(data)
        return venues or None
    except Exception:
        return None


def _load_from_json(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return None
        venues = _basic_validate(data)
        return venues or None
    except Exception:
        return None
    
def _load_orders(path: str):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _save_to_json(path: str, venues: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(venues, f, ensure_ascii=False, indent=2)

def _save_orders(path: str, orders: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

def get_venues():
    """最终给全平台用的数据源：API -> JSON -> LOCAL"""
    api_data = _load_from_api(API_URL)
    if api_data:
        return api_data, "API（外部平台接口）"

    json_data = _load_from_json(DATA_JSON)
    if json_data:
        return json_data, "本地 venues.json"

    return _basic_validate(VENUES_LOCAL), "内置示例数据（LOCAL）"


# =========================
# 3) Session：订单
# =========================
if "orders" not in st.session_state:
    st.session_state["orders"] = _load_orders(ORDERS_JSON)

# =========================
# 4) 小工具
# =========================
def venue_by_name(venues: list[dict], name: str):
    for v in venues:
        if v["name"] == name:
            return v
    return None


def next_id(venues: list[dict]) -> int:
    return (max([v["id"] for v in venues] or [0]) + 1)

def make_qr_png_bytes(url: str) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# =========================
# 5) 加载数据 + 顶部
# =========================
VENUES, DATA_SOURCE = get_venues()

st.title("阜阳红色场馆管理平台")
st.caption("功能：线上展示｜线路规划｜开放状态｜门票购买｜客服电话｜数据导入导出｜API 兜底")
st.info(f"平台统一客服电话：{HOTLINE}")
st.caption(f"数据来源：{DATA_SOURCE}（API 优先，本地兜底）")

tabs = st.tabs(
    ["线上展示", "线路规划", "门票购买", "开放状态/信息管理", "客服电话汇总", "订单查看&统计", "数据导入导出"]
)


# =========================
# Tab1：线上展示
# =========================
with tabs[0]:
    st.subheader("场馆列表（线上展示）")
    keyword = st.text_input("搜索（按名称/地址关键词）", "")

    cols = st.columns(3)
    filtered = []
    for v in VENUES:
        if keyword.strip() == "":
            filtered.append(v)
        else:
            if keyword in v["name"] or keyword in v["address"]:
                filtered.append(v)

    for i, v in enumerate(filtered):
        with cols[i % 3]:
            st.markdown(f"### {v['name']}")
            st.write(v["desc"])
            st.write(f"**地址：** {v['address']}")
            st.write(f"**开放时间：** {v['hours']}")
            st.write(f"**开放状态：** {v['status']}")
            st.write(f"**票价：** ￥{v['price']} / 人")
            st.write(f"**客服电话：** {v['phone']}")
            st.divider()


# =========================
# Tab2：线路规划（导航链接）
# =========================
with tabs[1]:
    st.subheader("线路规划（简易）")
    st.write("说明：用“生成导航链接”实现线路规划，简单可靠，答辩也好讲。")

    start = st.text_input("起点（你当前位置/学校/酒店等，直接输入文字即可）", "阜阳师范大学")
    end_name = st.selectbox("终点（选择一个红色场馆）", [v["name"] for v in VENUES])
    end_v = venue_by_name(VENUES, end_name)

    if st.button("生成导航链接"):
        gaode_url = f"https://uri.amap.com/navigation?to={end_v['lng']},{end_v['lat']},{end_v['name']}&mode=car&src=fy_red_demo"
        baidu_url = (
            f"https://api.map.baidu.com/direction?origin={start}"
            f"&destination=latlng:{end_v['lat']},{end_v['lng']}|name:{end_v['name']}"
            f"&mode=driving&region=阜阳&output=html"
        )
        st.subheader("导航二维码（扫码直达）")
        c1, c2 = st.columns(2)

        with c1:
            st.write("高德导航二维码")
            png1 = make_qr_png_bytes(gaode_url)
            st.image(png1, width=220)
            st.download_button("下载高德二维码", data=png1, file_name="gaode_nav.png", mime="image/png")

        with c2:
            st.write("百度导航二维码")
            png2 = make_qr_png_bytes(baidu_url)
            st.image(png2, width=220)
            st.download_button("下载百度二维码", data=png2, file_name="baidu_nav.png", mime="image/png")
        st.success("已生成导航链接（点击即可打开浏览器/手机地图）")
        st.markdown(f"- 高德导航：{gaode_url}")
        st.markdown(f"- 百度导航：{baidu_url}")

    st.divider()
    st.subheader("点位地图（可视化）")
    st.map([{"lat": v["lat"], "lon": v["lng"]} for v in VENUES])


# =========================
# Tab3：门票购买（模拟）
# =========================
with tabs[2]:
    st.subheader("门票购买（模拟下单）")
    name = st.selectbox("选择景点", [v["name"] for v in VENUES])
    v = venue_by_name(VENUES, name)

    st.write(f"**开放状态：** {v['status']}  ｜  **票价：** ￥{v['price']} / 人")
    if v["status"] != "开放":
        st.warning("该景点当前非开放状态，暂不支持购票（演示逻辑）。")
    else:
        buyer = st.text_input("姓名")
        phone = st.text_input("手机号")
        visit_date = st.date_input("参观日期", value=date.today())
        qty = st.number_input("购票数量", min_value=1, max_value=20, value=1, step=1)

        total = v["price"] * int(qty)
        st.write(f"合计：**￥{total}**")

if st.button("提交订单（模拟）"):
    if buyer.strip() == "" or phone.strip() == "":
        st.error("请填写姓名和手机号。")
    else:
        order = {
            "景点": v["name"],
            "姓名": buyer.strip(),
            "电话": phone.strip(),
            "日期": str(visit_date),
            "数量": int(qty),
            "金额": float(total),
            "下单时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        st.session_state["orders"].append(order)
        _save_orders(ORDERS_JSON, st.session_state["orders"])
        st.success("下单成功（已保存到 orders.json，刷新不丢）！")


# =========================
# Tab4：开放状态/信息管理（带持久化）
# =========================
with tabs[3]:
    st.subheader("开放状态/信息管理（演示）")
    st.write("说明：这里模拟管理员管理功能，并支持保存到 venues.json（刷新不丢）。")

    admin_pwd = st.text_input("管理员口令（演示用：1234）", type="password")
    if admin_pwd != "1234":
        st.info("输入口令后可管理（演示版口令：1234）。")
    else:
        venue_name = st.selectbox("选择要管理的景点", [v["name"] for v in VENUES])
        vv = venue_by_name(VENUES, venue_name)

        c1, c2 = st.columns(2)
        with c1:
            new_status = st.selectbox("开放状态", ["开放", "闭馆", "维护中"], index=["开放", "闭馆", "维护中"].index(vv["status"]))
            new_phone = st.text_input("客服电话", value=vv["phone"])
            new_price = st.number_input("票价（元/人）", min_value=0.0, value=float(vv["price"]), step=1.0)

        with c2:
            new_hours = st.text_input("开放时间", value=vv["hours"])
            new_address = st.text_input("地址", value=vv["address"])
            new_desc = st.text_area("简介", value=vv["desc"], height=120)

        colA, colB, colC = st.columns([1, 1, 2])
        with colA:
            if st.button("保存修改到本地"):
                for x in VENUES:
                    if x["name"] == venue_name:
                        x["status"] = new_status
                        x["phone"] = new_phone
                        x["price"] = float(new_price)
                        x["hours"] = new_hours
                        x["address"] = new_address
                        x["desc"] = new_desc
                _save_to_json(DATA_JSON, VENUES)
                st.success("已保存到 venues.json（下次打开仍然生效）。")

        with colB:
            if st.button("新增一个景点（空模板）"):
                VENUES.append(
                    {
                        "id": next_id(VENUES),
                        "name": f"新景点{next_id(VENUES)}",
                        "desc": "",
                        "address": "",
                        "phone": "",
                        "status": "开放",
                        "hours": "",
                        "price": 0,
                        "lat": 32.8890,
                        "lng": 115.8140,
                    }
                )
                _save_to_json(DATA_JSON, VENUES)
                st.success("已新增并保存。刷新页面后可在列表看到。")

        with colC:
            st.caption("提示：如果数据来源是 API，本页保存只写入本地 venues.json，不会改动外部平台数据。")


# =========================
# Tab5：客服电话汇总
# =========================
with tabs[4]:
    st.subheader("客服电话汇总")
    st.write(f"平台统一客服：**{HOTLINE}**")
    st.divider()
    for v in VENUES:
        st.write(f"- {v['name']}：{v['phone']}（{v['status']}）")


# =========================
# Tab6：订单查看 & 统计看板
# =========================
with tabs[5]:
    st.subheader("订单查看（演示）")
    orders = st.session_state["orders"]

    if len(orders) == 0:
        st.info("暂无订单。你可以在“门票购买”里先下个模拟单。")
    else:
        df = pd.DataFrame(orders)
        st.table(df)

        st.divider()
        st.subheader("订单统计（加分项）")

        total_orders = len(df)
        total_amount = float(df["金额"].sum())
        today_str = date.today().isoformat()
        today_orders = int((df["日期"] == today_str).sum())

        c1, c2, c3 = st.columns(3)
        c1.metric("订单总数", total_orders)
        c2.metric("总票额（元）", f"{total_amount:.2f}")
        c3.metric("今日订单数", today_orders)

        top = df.groupby("景点")["数量"].sum().sort_values(ascending=False).head(3)
        st.write("热门景点 Top3（按购票数量）")
        st.bar_chart(top)

        st.caption("提示：订单仅保存在当前浏览器会话中，刷新可能丢失。")
    if st.button("清空所有订单（演示）"):
        st.session_state["orders"] = []
        _save_orders(ORDERS_JSON, [])
        st.success("已清空 orders.json。")


# =========================
# Tab7：数据导入导出（CSV）
# =========================
with tabs[6]:
    st.subheader("数据导入导出（CSV）")
    st.write("用途：可以直接导入；也可以把当前数据导出交付。")

    # 导出
    df_venues = pd.DataFrame(VENUES)
    csv_bytes = df_venues.to_csv(index=False).encode("utf-8-sig")
    st.download_button("下载当前场馆数据 CSV", data=csv_bytes, file_name="venues.csv", mime="text/csv")

    st.divider()

    # 导入
    st.write("导入要求：CSV 列名建议包含 id,name,desc,address,phone,status,hours,price,lat,lng（缺少也能导入，但最好齐全）")
    up = st.file_uploader("上传 venues.csv", type=["csv"])
    if up is not None:
        try:
            df_in = pd.read_csv(up)
            data = df_in.to_dict(orient="records")
            imported = _basic_validate(data)
            if not imported:
                st.error("导入失败：数据为空或缺少关键字段（name/lat/lng）。")
            else:
                _save_to_json(DATA_JSON, imported)
                st.success(f"导入成功：{len(imported)} 条数据已写入 venues.json。请刷新页面查看效果。")
        except Exception as e:
            st.error(f"导入失败：{e}")

