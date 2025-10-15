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

ユーザーの断り方に対して、以下の「表現面」と「内容面」の観点から、その断り方が適切かどうかフィードバックしてください。改善点があれば、その点も具体的に指摘してください。

フィードバックをする際に必ず取り入れてほしい要素は以下の通りです。

全体評価：
・回答に対して点数をつける（100点満点）
・点数の評価は厳しめに付けてください。
　・点数の基準
　　・誘いに対して「ごめん。その日は予定があっていけないから、また今度誘って。」これを５０点の回答とする。
　　・高評価（80点以上）の例：相手との関係性を考慮し、丁寧な言葉遣いで明確に断りつつ、代替案や感謝の気持ちを適切に伝え、相手への配慮が十分感じられる場合。
　　・満点（100点）の例：上記に加え、非常に自然で好印象を与え、かつ状況を完全に把握した上で最適な表現を選んでいる完璧な断り方。
・点数が８０点以上の場合に合格、それ未満の場合は不合格と表示してください。
・点数をつける際は、なぜその点数になったのか、表現面、内容面の点数の内訳、それぞれどこの要素が足りないのかなどをユーザーが分かりやすいように説明してください。

表現面（言葉遣い、態度、丁寧さなど）：
・相手との関係性に応じた適切さ:
    ・相手が目上の人の場合、直接的な断り表現になっていないか、適切な敬語が使用されているか。
    ・相手が親しい関係の場合、フランクで自然な表現か。
・謝罪の言葉の有無と適切さ。
・文法的な正確さ、自然な言い回しか。

内容面（断りの理由、代替案など）：
・断りの意思の明確さ: 曖昧さがないか、はっきりと伝わるか。
・理由の提示の有無と適切さ: 納得できる理由か、具体性があるか。
・代替案の提示の有無と適切さ: 別の機会や方法を提案しているか。
・相手への配慮: 相手の誘い自体を否定せず、感謝の言葉があるか。
・内容の一貫性: 矛盾した内容になっていないか。

重み付けの考慮：
・提示されたシチュエーション（誘い手の特長、誘いの内容など）を考慮し、その状況において「表現面」と「内容面」のどちらがより重要であったか（あるいは両方が同等に重要であったか）を判断し、フィードバックに反映させてください。
　・目上の人やフォーマルな関係: 表現面（敬語、丁寧さ、クッション言葉、間接的な表現、謝罪の言葉）
　・親しい友人や家族: 内容面（具体的な理由、代替案の提示）
　・ビジネスシーン（取引先など）: 丁寧な表現面に加えて、内容面での明確な理由や建設的な代替案（例：別日程の提案、他の担当者の紹介）が重要

改善提案：
・フィードバックの結果から、不足している要素（表現面、内容面それぞれ）を補うためにどんな練習をしたらよいかを具体的に提示してください。

例：
誘い：[シチュエーション詳細：誘い手は会社の先輩、飲み会の誘い、少し断りにくい] 今度の金曜の夜、一緒に飲みに行かない？
ユーザー：すみません、その日は予定があって。
あなたの反応：そっか、残念！また今度ね。
あなたのフィードバック：
**全体評価： 60点 （不合格）**
**点数内訳：表現面～点　理由～～～～～～
　　　　　　内容面～点　理由～～～～～～

**表現面（言葉遣い、態度、丁寧さなど）：**
・相手との関係性に応じた適切さ： 目上の方への断り方としては、やや直接的で、もう少し丁寧さやクッション言葉があっても良かったでしょう。敬語は使用されていますが、より丁寧な表現を検討できます。
・謝罪の言葉の有無と適切さ：「すみません」という謝罪の言葉は適切でした。
・全体的な丁寧さ、配慮が感じられるか：まだ改善の余地があります。
・文法的な正確さ、自然な言い回しか：文法は正しいですが、より自然で配慮のある言い回しが可能です。

**内容面（断りの理由、代替案など）：**
・断りの意思の明確さ：「予定があって」という理由は提示されていますが、具体性に欠けるため、相手に納得感を与えにくい可能性があります。
・理由の提示の有無と適切さ：理由が抽象的でした。
・代替案の提示の有無と適切さ：代替案の提示がありませんでした。別の機会を提案することで、相手への配慮を示すことができます。
・相手への配慮：誘いへの感謝の言葉がありませんでした。
・内容の一貫性：矛盾はありません。

**重み付けの考慮：**
今回のシチュエーションでは、会社の先輩からの誘いであるため、表現面での丁寧さや配慮が特に重要でした。内容面でも具体的な理由や代替案を提示することで、よりスムーズな断りができたでしょう。

**改善提案：**
・**表現面の練習**： 「大変恐縮なのですが」「あいにくその日は」「せっかくお誘いいただいたのに申し訳ありません」といったクッション言葉や、より丁寧な断り方を練習してみましょう。
・**内容面の練習**： 「その日は先約がありまして、もしよろしければ〇曜日でしたらお伺いできます」のように、具体的な理由を簡潔に伝えつつ、代替案を提示する練習をしてみましょう。

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







