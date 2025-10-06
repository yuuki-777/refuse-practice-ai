import streamlit as st
import google.generativeai as genai
import os
import time
import json
import uuid

# --- 1. APIキーの設定 ---
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("GOOGLE_API_KEY が設定されていません。Streamlit Secretsまたは環境変数を確認してください。")
    st.stop()

# --- ログファイルのパス ---
CHAT_LOG_FILE = "chat_logs.json"

# チャット履歴をファイルに保存する関数
def save_chat_history(history):
    if os.path.exists(CHAT_LOG_FILE):
        with open(CHAT_LOG_FILE, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    else:
        logs = []

    session_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "session_id": str(uuid.uuid4()),
        "history": history
    }
    logs.append(session_data)

    with open(CHAT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=4)
    st.success("現在の会話履歴を保存しました！")

# チャット履歴をファイルから読み込む関数
def load_all_chat_histories():
    if os.path.exists(CHAT_LOG_FILE):
        with open(CHAT_LOG_FILE, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
                return logs
            except json.JSONDecodeError:
                return []
    return []

# 特定の履歴を削除する関数
def delete_chat_history(session_id_to_delete):
    logs = load_all_chat_histories()
    updated_logs = [log for log in logs if log["session_id"] != session_id_to_delete]
    with open(CHAT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_logs, f, ensure_ascii=False, indent=4)
    st.success("履歴を削除しました！")


# --- 2. モデルの選択 ---
model = genai.GenerativeModel('models/gemini-pro-latest')

# --- 3. Streamlitアプリのタイトル設定 ---
st.title("誘いを断る練習AI")
st.write("断ることが苦手なあなたのための、コミュニケーション練習アプリです。AIからの誘いを断ってみましょう！")

# ★★★ 変更箇所 ここから ★★★
# ユーザーがシナリオを入力するUI
scenario_input = st.text_area(
    "練習したいシナリオの内容を具体的に入力してください（例：会社の先輩、飲み会の誘い、断りにくさのレベルは中くらい）",
    height=150,
    key="scenario_input" # ユニークなkeyを追加
)

# シナリオ入力が空欄でないか確認
start_button_disabled = not scenario_input
start_button = st.button("練習を開始する", disabled=start_button_disabled, key="start_button") # ユニークなkeyを追加
# ★★★ 変更箇所 ここまで ★★★


# --- 4. チャット履歴とGeminiチャットオブジェクトの初期化 ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    st.session_state.initial_prompt_sent = False
    st.session_state.current_scenario_key = None # ユーザー入力の場合はNone

# --- 5. システムプロンプトの設定 ---
system_prompt_template = """
あなたはユーザーが誘いを断る練習をするためのロールプレイング相手です。

--- シナリオ開始 ---
**最初の応答では、以下の指示にのみ従ってください。ユーザーに何か誘いをかけてください。この応答に、ユーザーの断り方に対するフィードバックは絶対に含めないでください。**
**必ず、最初に提示するシナリオのシチュエーションを詳細に記載してから、誘い文を続けてください。**
例：誘い手の特長（例：先輩、友達、後輩、取引先）、誘いの内容（例：飲み会、仕事の依頼、プライベートなイベント）、断りにくさのレベル（例：断りやすい、少し断りにくい、かなり断りにくい）

--- ユーザーの応答後 ---
ユーザーがあなたの誘いを断った後の応答では、その断り方に応じて、納得して引き下がるか、あるいは少しだけ食い下がってください。

ユーザーの断り方に対してその断り方が適切かどうかフィードバックしてください。改善点があれば、その点も具体的に指摘してください。

フィードバックをする際に必ず取り入れてほしい要素は以下の通りです。

全体評価：
・回答に対して点数をつける（100点満点）
・点数の評価は厳しめに付けてください。
　・点数の基準
　　・誘いに対して「ごめん。その日は予定があっていけないから、また今度誘って。」これを５０点の回答とする。
　　・高評価（80点以上）の例：相手との関係性を考慮し、丁寧な言葉遣いで明確に断りつつ、代替案や感謝の気持ちを適切に伝え、相手への配慮が十分感じられる場合。
　　・満点（100点）の例：上記に加え、非常に自然で好印象を与え、かつ状況を完全に把握した上で最適な表現を選んでいる完璧な断り方。
・点数が８０点以上の場合に合格、それ未満の場合は不合格と表示してください。

"""
# --- 6. AIからの最初の誘いを生成し表示 ---
# シナリオ選択が変更された場合、または新規セッションの場合に誘いを生成
if st.session_state.get("current_scenario") != scenario_input or (start_button and not st.session_state.initial_prompt_sent):
    
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    
    # ユーザーが入力したシナリオをプロンプトに組み込む
    combined_prompt = f"{system_prompt_template}\n\n**ユーザーが設定したシナリオ:** {scenario_input}"
    
    with st.spinner("AIが誘いを考えています..."):
        initial_response = st.session_state.genai_chat.send_message(combined_prompt)
        st.session_state.chat_history.append({"role": "assistant", "content": initial_response.text})
        st.session_state.initial_prompt_sent = True
        st.session_state.current_scenario = scenario_input
        st.rerun()

# --- 7. 会話履歴の表示 ---
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 8. ユーザー入力の処理 ---
user_input = st.chat_input("あなたの断り言葉を入力してください")

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.spinner("AIが返答を考えています..."):
        ai_response = st.session_state.genai_chat.send_message(user_input)
        st.session_state.chat_history.append({"role": "assistant", "content": ai_response.text})
        with st.chat_message("assistant"):
            st.markdown(ai_response.text)

    time.sleep(1)
    st.rerun()

# 履歴を保存するボタン (既存)
if st.button("現在の会話履歴を保存"):
    if st.session_state.chat_history:
        save_chat_history(st.session_state.chat_history)
    else:
        st.warning("保存する会話履歴がありません。")

# 会話リセットボタン (既存)
if st.button("新しいシナリオで練習する"):
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    st.session_state.initial_prompt_sent = False
    st.session_state.current_scenario = None
    st.rerun()


# --- 履歴の閲覧セクション ---
st.subheader("これまでの練習履歴")

all_histories = load_all_chat_histories()

if not all_histories:
    st.info("まだ保存された練習履歴はありません。")
else:
    for i, log in enumerate(reversed(all_histories)):
        with st.expander(f"セッション: {log['timestamp']} (ID: {log['session_id'][-4:]})"):
            for message in log["history"]:
                if message["role"] == "assistant" and "あなたはユーザーが誘いを断る練習をするためのロールプレイング相手です。" in message["content"]:
                    continue
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            if st.button(f"このセッションを削除 ({log['session_id'][-4:]})", key=f"delete_btn_{log['session_id']}"):
                delete_chat_history(log['session_id'])
                st.rerun()



