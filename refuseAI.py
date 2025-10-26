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

# --- 履歴管理関数 (省略) ---
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

def load_all_chat_histories():
    if os.path.exists(CHAT_LOG_FILE):
        with open(CHAT_LOG_FILE, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
                return logs
            except json.JSONDecodeError:
                return []
    return []

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


# ★★★ 修正箇所：training_elements の定義 ★★★
# --- 練習要素の定義 (要素別トレーニング用: 6要素) ---
training_elements = {
    "相手との関係性に応じた適切さ ": "表現面：相手との関係性に応じた適切な言葉遣い、敬語、直接的な断り表現を避けているか。",
    "謝罪の言葉の有無と適切さ ": "表現面：謝罪の言葉が適切に使われているか。",
    "断りの意思の明確さ ": "内容面：曖昧さがなく、断りの意思がはっきりと伝わるか。",
    "理由の提示の有無と適切さ ": "内容面：納得できる理由か、具体性があるか。",
    "代替案の提示の有無と適切さ ": "内容面：別の機会や方法を提案しているか。",
    "相手への配慮 (感謝の言葉など) ": "内容面：相手の誘い自体を否定せず、感謝の言葉があるか。",
}
# ★★★ 修正箇所 ここまで ★★★


# --- 4. UIの配置とモード選択 (変更なし) ---
st.subheader("練習モードの選択とシナリオ設定")

# 練習モードの選択
practice_mode = st.radio(
    "1. 練習モードを選択してください:",
    ('総合実践 (全要素を評価)', '要素別トレーニング (一点集中)'),
    index=0,
    key='practice_mode_select'
)

selected_element = ""
if practice_mode == '要素別トレーニング (一点集中)':
    st.info("練習したい要素を一つ選んでください。AIがその点に絞ってフィードバックします（点数評価はありません）。")
    # 要素を選択させる
    selected_element = st.selectbox(
        "▼ 集中して練習する要素を選択",
        list(training_elements.keys()), # 6要素のみが表示される
        key='training_element_select'
    )
    st.markdown(f"**目標**: *{training_elements[selected_element]}*")


# ユーザーがシナリオを入力するUI
scenario_input = st.text_area(
    "2. 練習したいシナリオの内容を具体的に入力してください（例：会社の先輩、飲み会の誘い、断りにくさのレベルは中くらい）",
    height=100,
    key="scenario_input"
)

# シナリオ入力が空欄でないか確認
start_button_disabled = not scenario_input
start_button = st.button("3. 練習を開始する", disabled=start_button_disabled, key="start_button")


# --- 5. チャット履歴とGeminiチャットオブジェクトの初期化 (変更なし) ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    st.session_state.initial_prompt_sent = False
    st.session_state.current_scenario = None


# --- 6. システムプロンプトの設定 (テンプレート) ---

# --- 総合実践モード用の詳細なプロンプトテンプレート (9要素評価のまま維持) ---
SYSTEM_PROMPT_FULL_TEMPLATE = f"""
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
・回答に対して点数をつける（10点満点）
・表現面、内容面をそれぞれ**5点満点**で評価し、その合計を全体の点数としてください。
・点数をつける際は、なぜその点数になったのか、表現面、内容面の点数の内訳（各項目）、それぞれどこの要素が足りないのかなどをユーザーが分かりやすいように説明してください。

表現面（言葉遣い、態度、丁寧さなど）：以下の内容が含まれているかで判断（5点満点）
・相手との関係性に応じた適切さ: 1点
    ・相手が目上の人の場合、直接的な断り表現になっていないか、適切な敬語が使用されているか。
    ・相手が親しい関係の場合、フランクで自然な表現か。
・謝罪の言葉の有無と適切さ：1点
・全体的な丁寧さ、配慮が感じられるか：1点
・文法的な正確さ、自然な言い回しか：2点

内容面（断りの理由、代替案など）：以下の内容が含まれているかで判断（5点満点）
・断りの意思の明確さ: 曖昧さがないか、はっきりと伝わるか：1点
・理由の提示の有無と適切さ: 納得できる理由か、具体性があるか：1点
・代替案の提示の有無と適切さ: 別の機会や方法を提案しているか：1点
・相手への配慮: 相手の誘い自体を否定せず、感謝の言葉があるか：1点
・内容の一貫性: 矛盾した内容になっていないか：1点

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
**全体評価： 6/10点 （不合格）**
**点数内訳：表現面: 3/5点 (理由：謝罪はあるがクッション言葉なし)、内容面: 3/5点 (理由：代替案なし、理由が抽象的)**
... (中略) ...
"""

# --- 要素別トレーニング用プロンプト生成関数 (変更なし) ---
def create_focused_prompt(element_key, element_description):
    """選択された要素に特化したフィードバックプロンプトを生成する関数 (点数評価なし)"""
    
    score_info = element_description.split('(')[-1].replace(')', '')
    
    focused_prompt = f"""
あなたはユーザーが特定の要素を練習するためのコーチです。
あなたの役割は、ユーザーが断りの練習をする際、冷静にフィードバックを提供することです。

--- 練習目標 ---
このモードの目的は、**特定のスキル習得に集中**することです。
ユーザーの断り方を評価する際、**{element_key} (配点: {score_info})** の項目**のみ**を評価対象としてください。**他の項目、および総合点数や合否は一切無視し、絶対に点数を付けないでください。**

--- シナリオ開始 ---
最初の応答では、以下の指示にのみ従ってください。ユーザーに何か誘いをかけてください。この応答に、ユーザーの断り方に対するフィードバックは絶対に含めないでください。
必ず、最初に提示するシナリオのシチュエーションを詳細に記載してから、誘い文を続けてください。

--- ユーザーの応答後 ---
ユーザーがあなたの誘いを断った後の応答では、その断り方に応じて、納得して引き下がるか、あるいは少しだけ食い下がってください。

ユーザーの断り方に対して、以下の【評価観点】に**厳密に**従ってフィードバックしてください。

【評価観点】
1. **評価**: **{element_key}** の観点から、具体的にどの言葉が良かったか/悪かったかを、ユーザーの感情に配慮しつつ**コーチング形式**で説明してください。
2. **改善提案**: この**特定の要素**を補うために、どんな練習をしたらよいかを具体的に提示してください。

**フィードバックの例:**
**評価:** 謝罪の言葉はありましたが、少し軽すぎる印象を与えました。「すみません」ではなく、「大変申し訳ありません」という表現を使うと、相手への配慮がより伝わります。
**改善提案:** 次のターンでは、「大変恐縮ですが」のような、より重みのある**クッション言葉**を使うことを意識して、もう一度断ってみましょう。
"""
    return focused_prompt


# --- 7. AIからの最初の誘いを生成し表示 (ロジック分岐) ---
if st.session_state.get("current_scenario") != scenario_input or (start_button and not st.session_state.initial_prompt_sent):
    
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    
    # ユーザーが入力したシナリオをプロンプトに組み込む
    scenario_text = f"**ユーザーが設定したシナリオ:** {scenario_input}"
    
    if practice_mode == '要素別トレーニング (一点集中)':
        # 要素別トレーニングモード
        combined_prompt = create_focused_prompt(selected_element, training_elements[selected_element])
        combined_prompt += f"\n\n{scenario_text}"
        
    else: # 総合実践 (全要素を評価)
        # 総合実践モード
        combined_prompt = f"{SYSTEM_PROMPT_FULL_TEMPLATE}\n\n{scenario_text}"
        
    # AIへの送信ロジックは共通
    with st.spinner("AIが誘いを考えています..."):
        initial_response = st.session_state.genai_chat.send_message(combined_prompt)
        st.session_state.chat_history.append({"role": "assistant", "content": initial_response.text})
        st.session_state.initial_prompt_sent = True
        st.session_state.current_scenario = scenario_input
        st.rerun()

# --- 8. 会話履歴の表示 (変更なし) ---
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 9. ユーザー入力の処理 (変更なし) ---
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

# 履歴を保存するボタン (変更なし)
if st.button("現在の会話履歴を保存", key="save_button"):
    if st.session_state.chat_history:
        save_chat_history(st.session_state.chat_history)
    else:
        st.warning("保存する会話履歴がありません。")

# 会話リセットボタン (変更なし)
if st.button("新しいシナリオで練習する", key="reset_button"):
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    st.session_state.initial_prompt_sent = False
    st.session_state.current_scenario = None
    st.rerun()


# --- 履歴の閲覧セクション (変更なし) ---
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
