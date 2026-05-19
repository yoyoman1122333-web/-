import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# ==================== 1. 核心演算法：水軍與時間密集度過濾 ====================
def calculate_real_rating(reviews, original_rating, w_length, w_extreme, w_empty, w_time):
    if not reviews:
        return original_rating
        
    parsed_reviews = []
    for rev in reviews:
        text = rev.get('text', {}).get('text', '')
        rating = rev.get('rating', 0)
        time_str = rev.get('publishTime', '')
        
        dt = None
        if time_str:
            try:
                # 移除非 ISO 格式的微秒部分並解析
                clean_time = time_str.split('.')[0].replace('Z', '')
                dt = datetime.strptime(clean_time, '%Y-%m-%dT%H:%M:%S')
            except:
                pass
                
        parsed_reviews.append({
            'text': text,
            'rating': rating,
            'date': dt,
            'trust': 1.0
        })
        
    parsed_reviews.sort(key=lambda x: x['date'] if x['date'] else datetime.min)
    
    # 時間密集度偵測：前後評論在 24 小時內則視為異常
    for i in range(len(parsed_reviews)):
        if i > 0 and parsed_reviews[i]['date'] and parsed_reviews[i-1]['date']:
            delta_seconds = abs((parsed_reviews[i]['date'] - parsed_reviews[i-1]['date']).total_seconds())
            if delta_seconds <= 86400:  # 24小時以內
                parsed_reviews[i]['trust'] -= (w_time / 2)
                parsed_reviews[i-1]['trust'] -= (w_time / 2)
                
    total_weighted_stars = 0
    total_trust_score = 0
    
    for rev in parsed_reviews:
        text = rev['text']
        rating = rev['rating']
        trust = rev['trust']
        
        if len(text) < 5:
            trust -= w_length
        if not text.strip():
            trust -= w_empty
        if (rating == 5 or rating == 1) and len(text) < 10:
            trust -= w_extreme
            
        trust = max(trust, 0.05)
        
        total_weighted_stars += (rating * trust)
        total_trust_score += trust
        
    return round(total_weighted_stars / total_trust_score, 2)

# ==================== 2. API 撈取資料 ====================
def fetch_restaurants(api_key, location, radius, open_now):
    url = "https://googleapis.com"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.primaryType,places.rating,places.userRatingCount,places.currentOpeningHours,places.reviews"
    }
    try:
        lat, lng = map(float, location.split(','))
    except:
        st.error("經緯度格式錯誤，請輸入如: 22.6253,120.3094")
        return []
        
    payload = {
        "includedTypes": ["restaurant"],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius)
            }
        }
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code == 200:
            results = res.json().get('places', [])
            if open_now:
                return [r for r in results if r.get('currentOpeningHours', {}).get('openNow') == True]
            return results
        else:
            st.error(f"API 請求失敗: {res.text}")
            return []
    except Exception as e:
        st.error(f"連線失敗: {e}")
        return []

# ==================== 3. Streamlit 網頁介面 ====================
st.set_page_config(page_title="AI 真實餐廳推薦系統", layout="wide")
st.title("🛡️ AI 餐廳防假點評推薦系統")
st.caption("自動過濾文字過短、極端評分、密集刷榜的水軍留言，還原最真實的店家實力。")

st.sidebar.header("🔑 API 金鑰設定")
api_key = st.sidebar.text_input("輸入 Google Places API Key", type="password")

st.sidebar.header("📍 搜尋條件")
location = st.sidebar.text_input("我的地點 (緯度,經度)", "22.6253,120.3094")
radius = st.sidebar.slider("搜尋半徑 (公尺)", min_value=500, max_value=10000, value=2000, step=500)
open_now = st.sidebar.checkbox("只顯示目前營業中", value=True)

st.sidebar.header("🕵️ 水軍過濾權重調校")
w_length = st.sidebar.slider("字數過短扣分權重", 0.0, 0.5, 0.3, 0.05)
w_empty = st.sidebar.slider("空白零字扣分權重", 0.0, 0.5, 0.2, 0.05)
w_extreme = st.sidebar.slider("無理由極端分扣分權重", 0.0, 0.5, 0.2, 0.05)
w_time = st.sidebar.slider("時間密集爆發扣分權重", 0.0, 0.5, 0.3, 0.05)

if st.button("🔍 開始偵測並分析前 20 家餐廳"):
    if not api_key:
        st.warning("請先在左側輸入您的 Google Places API Key！")
    else:
        with st.spinner("正在抓取周邊店家並對評論進行分析..."):
            raw_data = fetch_restaurants(api_key, location, radius, open_now)
            
            if not raw_data:
                st.info("沒有找到符合條件的餐廳。")
            else:
                final_results = []
                for idx, r in enumerate(raw_data, 1):
                    name = r.get('displayName', {}).get('text', '未知餐廳')
                    orig_rating = r.get('rating', 0.0)
                    reviews = r.get('reviews', [])
                    
                    real_rating = calculate_real_rating(reviews, orig_rating, w_length, w_extreme, w_empty, w_time)
                    drop = round(orig_rating - real_rating, 2)
                    
                    final_results.append({
                        "排名": idx,
                        "餐廳名稱": name,
                        "真實 AI 評價 ⭐": real_rating,
                        "原 Google 評價": orig_rating,
                        "水軍水分落差 💧": drop,
                        "狀態": "營業中" if r.get('currentOpeningHours', {}).get('openNow') else "休息中"
                    })
                
                df = pd.DataFrame(final_results)
                df = df.sort_values(by="真實 AI 評價 ⭐", ascending=False).reset_index(drop=True)
                df["排名"] = df.index + 1
                
                st.subheader("🏆 真實評價最高 Top 3")
                cols = st.columns(3)
                for i in range(min(3, len(df))):
                    with cols[i]:
                        st.metric(label=f"No.{i+1} {df.iloc[i]['餐廳名稱']}", 
                                  value=f"{df.iloc[i]['真實 AI 評價 ⭐']} ⭐", 
                                  delta=f"原始: {df.iloc[i]['原 Google 評價']}")
                
                st.subheader("📋 完整 20 家餐廳分析報告")
                st.dataframe(df, use_container_width=True)
                
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 匯出餐廳分析 Excel/CSV 檔",
                    data=csv,
                    file_name=f"AI_restaurant_report_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime='text/csv',
                )
