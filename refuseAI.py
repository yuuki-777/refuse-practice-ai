import streamlit as st
import google.generativeai as genai
import os
import time
import json
import uuid
import re

# --- 1. APIキーの設定 ---
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("GOOGLE_API_KEY が設定されていません。Streamlit Secretsまたは環境変数を確認してください。")
    st.stop()

# --- ログファイルのディレクトリ設定 ---
# ユーザーごとのデータを保存するディレクトリを定義
LOGS_DIR = "user_data" 

def get_user_files(user_id):
    """ユーザーIDに基づいてチャットログと進捗ログのパスを生成"""
    # ディレクトリが存在しない場合は作成 (Streamlit Cloudの永続化対応)
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR, exist_ok=True)
    return {
        "chat": os.path.join(LOGS_DIR, f"chat_logs_{user_id}.json"),
        "progress": os.path.join(LOGS_DIR, f"element_progress_{user_id}.json")
    }

# --- 進捗のロード/セーブ関数 (user_id対応) ---
def load_element_progress(training_elements, user_id):
    """進捗ファイルを読み込む。ない場合や破損時は初期状態を返す。"""
    file_path = get_user_files(user_id)["progress"] # 動的なパス
    initial_status = {key: False for key in training_elements.keys()}
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                loaded_status = json.load(f)
                initial_status.update(loaded_status)
            except json.JSONDecodeError:
                pass
    return initial_status

def save_element_progress(status, user_id):
    """進捗をファイルに保存する。"""
    file_path = get_user_files(user_id)["progress"] # 動的なパス
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=4)


# --- 履歴管理関数 (user_id対応) ---
def save_chat_history(history, user_id):
    file_path = get_user_files(user_id)["chat"] # 動的なパス
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
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
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=4)
    st.success("現在の会話履歴を保存しました！")

def load_all_chat_histories(user_id):
    file_path = get_user_files(user_id)["chat"] # 動的なパス
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
                return logs
            except json.JSONDecodeError:
                return []
    return []

def delete_chat_history(session_id_to_delete, user_id):
    file_path = get_user_files(user_id)["chat"] # 動的なパス
    logs = load_all_chat_histories(user_id)
    updated_logs = [log for log in logs if log["session_id"] != session_id_to_delete]
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(updated_logs, f, ensure_ascii=False, indent=4)
    st.success("履歴を削除しました！")


# --- テキストの強調表示処理関数 (変更なし) ---
def highlight_text(text):
    """AIが出力する太字斜体下線マークアップ（_**...**_）を赤色に変換する"""
    highlighted = text.replace("_**", '<span style="color:red; font-weight:bold; text-decoration: underline;">')
    highlighted = highlighted.replace("**_**", '</span>')
    return highlighted


# --- 2. モデルの選択 ---
model = genai.GenerativeModel('models/gemini-pro-latest')


# --- 3. Streamlitアプリのタイトル設定 ---
st.title("誘いを断る練習AI")
st.write("断ることが苦手なあなたのための、コミュニケーション練習アプリです。AIからの誘いを断ってみましょう！")

# --- 【新規】ユーザーID入力セクション ---
st.subheader("🔑 ユーザー認証と進捗のロード")
user_id_input = st.text_input(
    "あなたの学籍番号 (半角英数字) を入力してください。進捗と履歴はこのIDで保存されます。",
    key="user_id_key"
)

# ユーザーIDが入力されるまでアプリの実行を停止
if not user_id_input:
    st.info("練習を開始するには、まずユーザーIDを入力してください。")
    st.stop()

# ユーザーIDを変数に設定
user_id = user_id_input 

# --- 練習要素の定義 (要素別トレーニング用: 6要素) ---
training_elements = {
    "相手との関係性に応じた適切さ (1点)": "表現面：相手との関係性に応じた適切な言葉遣い、敬語、直接的な断り表現を避けているか。",
    "謝罪の言葉の有無と適切さ (1点)": "表現面：謝罪の言葉が適切に使われているか。",
    "断りの意思の明確さ (1点)": "内容面：曖昧さがなく、断りの意思がはっきりと伝わるか。",
    "理由の提示の有無と適切さ (1点)": "内容面：納得できる理由か、具体性があるか。",
    "代替案の提示の有無と適切さ (1点)": "内容面：別の機会や方法を提案しているか。",
    "相手への配慮 (感謝の言葉など) (1点)": "内容面：相手の誘い自体を否定せず、感謝の言葉があるか。",
}

# --- 6. システムプロンプトの設定 (テンプレート) ---
# ... (SYSTEM_PROMPT_FULL_TEMPLATEとcreate_focused_promptの定義はそのまま)

# --- 総合実践モード用の詳細なプロンプトテンプレート ---
SYSTEM_PROMPT_FULL_TEMPLATE = f"""
あなたはユーザーが誘いを断る練習をするためのロールプレイング相手です。

**【AIの役割と設定】**
あなたの役割は、**大学1年生から新卒1年目（社会人経験が浅い層）**のユーザーに対して、**大学生活、サークル、アルバイト、または初めての職場**で起こり得る具体的なメールでの誘いのシナリオを提供することです。
シナリオは、ご飯の誘いの他に、サークルの仕事やアルバイト先でのお願いなど**絶対に！**幅広いシナリオをまんべんなく提供してください。

--- シナリオ開始 ---
**最初の応答では、以下の指示にのみ従ってください。ユーザーに何か誘いをかけてください。この応答に、ユーザーの断り方に対するフィードバックは絶対に含めないでください。**
**必ず、最初に提示するシナリオのシチュエーションを詳細に記載し、**相手との関係性（サークルの先輩、バイトの同僚、大学の友人、新卒の教育担当など）**を明確にしてから、誘い文を続けてください。**

--- ユーザーの応答後 ---
ユーザーがあなたの誘いを断った後の応答では、その断り方に応じて、納得して引き下がるか、あるいは少しだけ食い下がってください。

ユーザーの断り方に対して、以下の「表現面」と「内容面」の観点から、その断り方が適切かどうかフィードバックしてください。改善点があれば、その点も具体的に指摘してください。

**【出力形式の厳守】**
* **結論ファースト**: まず、以下の形式で「全体評価」と「点数内訳」を**# 見出し**として表示してください。その後に、詳細な評価に入ってください。
* **簡潔な箇条書き**: 評価理由や改善提案は、**冗長な文章を避け、必ず箇条書き（ハイフン`-`を使用）**で簡潔に記述してください。説明は各項目につき1〜2行に収めてください。

フィードバックをする際に必ず取り入れてほしい要素は以下の通りです。

# 全体評価
- 回答に対して点数をつける（10点満点）
- 表現面、内容面をそれぞれ**5点満点**で評価し、その合計を全体の点数としてください。
- 点数が**10点満点の場合にのみ合格**、9点以下の場合は不合格と表示してください。
- **点数内訳**: 以下の形式で簡潔にまとめてください。
  - **表現面**: X/5点 (理由の要約)
  - **内容面**: Y/5点 (理由の要約)

表現面（言葉遣い、態度、丁寧さなど）：以下の内容が含まれているかで判断（5点満点）
- 相手との関係性に応じた適切さ: 1点
- 謝罪の言葉の有無と適切さ：1点
- 全体的な丁寧さ、配慮が感じられるか：1点
- 文法的な正確さ、自然な言い回しか：2点

内容面（断りの理由、代替案など）：以下の内容が含まれているかで判断（5点満点）
- 断りの意思の明確さ: 1点
- 理由の提示の有無と適切さ: 1点
- 代替案の提示の有無と適切さ: 1点
- 相手への配慮: 相手の誘い自体を否定せず、感謝の言葉があるか：1点
- 内容の一貫性: 1点 

# 表現面（詳細）
- **評価**: 表現面で加点・減点された点を、具体的な言葉遣いに言及しながら説明してください。

# 内容面（詳細）
- **評価**: 内容面で加点・減点された点を、理由や代替案の具体性に言及しながら説明してください。

# 重み付けの考慮
- 提示されたシチュエーションを考慮し、**どちらの面（表現面/内容面）が重要であったか**を結論づけてください。

# 改善提案
- フィードバックの結果から、不足している要素を補うためにどんな練習をしたらよいかを具体的に提示してください。
"""

# --- 要素別トレーニング用プロンプト生成関数 (合否判定の追加) ---
def create_focused_prompt(element_key, element_description):
    """選択された要素に特化したフィードバックプロンプトを生成する関数 (合否判定あり)"""
    
    score_info = element_description.split('(')[-1].replace(')', '')
    
    focused_prompt = f"""
あなたはユーザーが特定の要素を練習するためのコーチです。
あなたの役割は、ユーザーが断りの練習をする際、冷静にフィードバックを提供することです。

**【AIの役割と設定】**
あなたの役割は、**大学1年生から新卒1年目（社会人経験が浅い層）**のユーザーに対して、**大学生活、サークル、アルバイト、または初めての職場**で起こり得る具体的なメールでの誘いのシナリオを提供することです。
シナリオは、ご飯の誘いの他に、サークルの仕事やアルバイト先でのお願いなど**絶対に！**幅広いシナリオをまんべんなく提供してください。
--- 練習目標 ---
このモードの目的は、**特定のスキル習得に集中**することです。
ユーザーの断り方を評価する際、**{element_key} (配点: {score_info})** の項目**のみ**を評価対象としてください。**他の項目、および総合点数や合否は一切無視し、絶対に点数を付けないでください。**

--- シナリオ開始 ---
最初の応答では、以下の指示にのみ従ってください。ユーザーに何か誘いをかけてください。この応答に、ユーザーの断り方に対するフィードバックは絶対に含めないでください。
必ず、最初に提示するシナリオのシチュエーションを詳細に記載し、**相手との関係性（サークルの先輩、バイトの同僚、大学の友人、新卒の教育担当など）**を明確にしてから、誘い文を続けてください。

--- ユーザーの応答後 ---
ユーザーがあなたの誘いを断った後の応答では、その断り方に応じて、納得して引き下がるか、あるいは少しだけ食い下がってください。

ユーザーの断り方に対して、以下の【評価観点】に**厳密に**従ってフィードバックしてください。

**【出力形式の厳守】**
* **結論ファースト**: まず「評価」を太字の見出しで表示してください。
* **簡潔な箇条書き**: 評価理由や改善提案は、**冗長な文章を避け、必ず箇条書き（ハイフン`-`を使用）**で簡潔に記述してください。説明は各項目につき1〜2行に収めてください。

【評価観点】
1. **評価**: **{element_key}** の観点から、具体的にどの言葉が良かったか/悪かったかを、ユーザーの感情に配慮しつつ**コーチング形式**で説明してください。
2. **改善提案**: この**特定の要素**を補うために、どんな練習をしたらよいかを具体的に提示してください。

**【AIへの追加指示】**
ユーザーの断り方（例：「大変恐縮なのですが、その日は先約がありまして」）を、あなたの応答の**最初に**、以下の手順で**マークアップして引用**してください。
1. **練習目標である要素に最も関連する部分（単語または句）**を見つけます。
2. その部分を、**太字と斜体、下線**でマークアップ（_**...**_）してください。
3. その後に、通常の評価と改善提案を続けてください。
4. フィードバックの**末尾に**、以下の厳密な形式で合否判定を必ず追加してください。
    - 基準: ユーザーの断り方が、この要素の基準を完全に満たした場合のみ「合格」としてください。少しでも改善の余地がある場合は「不合格」です。
    - 形式: 【合否判定】: 合格 または 【合否判定】: 不合格
"""
    return focused_prompt


# --- 4. UIの配置とモード選択 ---

# --- セッションステートの初期化とIDチェック ---
# ユーザーIDが変わった場合や、セッション開始時にリセット＆ロードを実行
if "chat_history" not in st.session_state or "user_id" not in st.session_state or st.session_state.user_id != user_id:
    
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    st.session_state.initial_prompt_sent = False
    st.session_state.current_scenario = None
    st.session_state.user_id = user_id # 現在のIDを記憶
    
    # 【変更】要素別トレーニングの合格状況をIDからロード
    st.session_state.element_status = load_element_progress(training_elements, user_id) 

# 進捗状況の計算
all_elements_passed = all(st.session_state.element_status.values())

st.subheader("練習モードの選択とシナリオ設定")

# 練習モードの選択 (ロック機能の実装)
if all_elements_passed:
    st.success("🎉 すべての要素を合格しました！総合実践モードが解放されました。")
    mode_options = ('総合実践 (全要素を評価)', '要素別トレーニング (一点集中)')
else:
    st.warning("総合実践は、すべての要素別トレーニング（6要素）を合格後に解放されます。")
    mode_options = ('総合実践 (ロック中)', '要素別トレーニング (一点集中)')

# 過去に選択されていたモードを記憶
initial_index = 1 
if 'practice_mode_select' in st.session_state:
    try:
        initial_index = mode_options.index(st.session_state.practice_mode_select)
    except ValueError:
        # ロック中に総合実践が選択されていた場合、要素別トレーニングにリセット
        initial_index = 1

practice_mode = st.radio(
    "1. 練習モードを選択してください:",
    mode_options,
    index=initial_index,
    key='practice_mode_select'
)

# ロック中のモード選択を無効化
if not all_elements_passed and practice_mode == '総合実践 (ロック中)':
    # 選択されてしまった場合、要素別トレーニングに強制的に切り替え
    practice_mode = '要素別トレーニング (一点集中)'
    # UI上のラジオボタンの見た目は変わらないが、内部ロジックで制御

# 進捗状況の表示
st.markdown("---")
st.markdown("### 🏆 要素別トレーニングの進捗")
cols = st.columns(3)
element_keys = list(training_elements.keys())
for i, key in enumerate(element_keys):
    passed = st.session_state.element_status[key]
    icon = "✅" if passed else "❌"
    cols[i % 3].markdown(f"**{icon} {key.split(' (')[0]}**")
st.markdown("---")


selected_element = ""
if practice_mode == '要素別トレーニング (一点集中)':
    st.info("練習したい要素を一つ選んでください。合格を目指しましょう！")
    # 合格済みの要素は選択肢の末尾に移動させる
    available_elements = [k for k, v in st.session_state.element_status.items() if not v]
    passed_elements = [k for k, v in st.session_state.element_status.items() if v]
    
    # 選択肢の表示
    display_options = available_elements + [f"{e} (✅ 合格済み)" for e in passed_elements]
    # 要素のキーを抽出するため、合格済みマークを削除したリストを作成
    key_options = available_elements + passed_elements

    if not key_options:
        st.success("すべての要素を合格しました！総合実践モードへ進んでください。")
        selected_element = list(training_elements.keys())[0] # ダミーで一つ選択
    else:
        # ユーザーが選択した表示テキストを取得
        selected_display_text = st.selectbox(
            "▼ 集中して練習する要素を選択",
            display_options,
            key='training_element_select_display'
        )
        # 実際のキーを特定 (合格済みマークを削除)
        selected_element_index = display_options.index(selected_display_text)
        selected_element = key_options[selected_element_index]
        
    st.markdown(f"**目標**: *{training_elements[selected_element]}*")


# ユーザーがシナリオを入力するUI
scenario_input = st.text_area(
    "2. 練習したいシナリオの内容を具体的に入力してください（例：会社の先輩、飲み会の誘い、断りにくさのレベルは中くらい）",
    height=100,
    key="scenario_input"
)

start_button_disabled = not scenario_input or (practice_mode == '要素別トレーニング (一点集中)' and not selected_element)
start_button = st.button("3. 練習を開始する", disabled=start_button_disabled, key="start_button")


# --- 7. AIからの最初の誘いを生成し表示 (ロジック分岐) ---
if st.session_state.get("current_scenario") != scenario_input or (start_button and not st.session_state.initial_prompt_sent):
    
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    
    scenario_text = f"**ユーザーが設定したシナリオ:** {scenario_input}"
    
    if practice_mode == '要素別トレーニング (一点集中)':
        element_key_for_prompt = selected_element 
        if element_key_for_prompt:
            combined_prompt = create_focused_prompt(element_key_for_prompt, training_elements[element_key_for_prompt])
            combined_prompt += f"\n\n{scenario_text}"
        else:
            combined_prompt = "" 
        
    else: # 総合実践 (全要素を評価)
        combined_prompt = f"{SYSTEM_PROMPT_FULL_TEMPLATE}\n\n{scenario_text}"
    
    if combined_prompt:
        with st.spinner("AIが誘いを考えています..."):
            initial_response = st.session_state.genai_chat.send_message(combined_prompt)
            st.session_state.chat_history.append({"role": "assistant", "content": initial_response.text})
            st.session_state.initial_prompt_sent = True
            st.session_state.current_scenario = scenario_input
            st.rerun()
    else:
        st.info("練習を開始するには、総合実践モードを選択してください。")


# --- 8. 会話履歴の表示 ---
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
             st.markdown(highlight_text(message["content"]), unsafe_allow_html=True)
        else:
             st.markdown(message["content"])

# --- 9. ユーザー入力の処理 ---
user_input = st.chat_input("あなたの断り言葉を入力してください")

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.spinner("AIが返答を考えています..."):
        ai_response = st.session_state.genai_chat.send_message(user_input)
        response_text = ai_response.text

        # 要素別トレーニングでの合否判定チェック
        if practice_mode == '要素別トレーニング (一点集中)' and selected_element:
            # 正規表現で合否判定を抽出
            match = re.search(r"【合否判定】:\s*(合格|不合格)", response_text)
            
            if match and match.group(1) == "合格":
                current_element_key = selected_element
                if not st.session_state.element_status[current_element_key]:
                    # 合格フラグを立てる
                    st.session_state.element_status[current_element_key] = True
                    # 【変更】進捗をファイルに保存する (IDベース)
                    save_element_progress(st.session_state.element_status, user_id)
                    # ユーザーに分かりやすいメッセージを追加
                    response_text += "\n\n🎉 **おめでとうございます！この要素を合格しました。** 次の要素に進むか、すべての要素合格後に総合実践に挑戦しましょう！"
            
            # 合否判定のメッセージを強調する
            response_text = response_text.replace("【合否判定】: 合格", "**【合否判定】: <span style='color:green;'>合格</span>**")
            response_text = response_text.replace("【合否判定】: 不合格", "**【合否判定】: <span style='color:red;'>不合格</span>**")


        st.session_state.chat_history.append({"role": "assistant", "content": response_text})
        with st.chat_message("assistant"):
            st.markdown(highlight_text(response_text), unsafe_allow_html=True)

    time.sleep(1)
    st.rerun()

# 履歴を保存するボタン
# 【変更】user_idを引数として渡す
if st.button("現在の会話履歴を保存", key="save_button"):
    if st.session_state.chat_history:
        save_chat_history(st.session_state.chat_history, user_id)
    else:
        st.warning("保存する会話履歴がありません。")

# 会話リセットボタン
if st.button("新しいシナリオで練習する (進捗は維持)", key="reset_button"):
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    st.session_state.initial_prompt_sent = False
    st.session_state.current_scenario = None
    st.rerun()

# 全進捗リセットボタン
if st.button("すべての要素の進捗をリセット", key="full_reset_button"):
    # 【変更】element_statusを初期化し、進捗ファイルも削除する (IDベース)
    st.session_state.element_status = {key: False for key in training_elements.keys()}
    progress_file_path = get_user_files(user_id)["progress"]
    if os.path.exists(progress_file_path):
        os.remove(progress_file_path)

    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    st.session_state.initial_prompt_sent = False
    st.session_state.current_scenario = None
    st.info(f"ID: {user_id} の進捗がリセットされました。")
    st.rerun()


# --- 履歴の閲覧セクション ---
st.subheader("これまでの練習履歴")

# 【変更】user_idを引数として渡す
all_histories = load_all_chat_histories(user_id)

if not all_histories:
    st.info("まだ保存された練習履歴はありません。")
else:
    for i, log in enumerate(reversed(all_histories)):
        with st.expander(f"セッション: {log['timestamp']} (ID: {log['session_id'][-4:]})"):
            for message in log["history"]:
                if message["role"] == "assistant" and "あなたはユーザーが誘いを断る練習をするためのロールプレイング相手です。" in message["content"]:
                    continue 
                with st.chat_message(message["role"]):
                    if message["role"] == "assistant":
                        st.markdown(highlight_text(message["content"]), unsafe_allow_html=True)
                    else:
                        st.markdown(message["content"])

            # 【変更】user_idを引数として渡す
            if st.button(f"このセッションを削除 ({log['session_id'][-4:]})", key=f"delete_btn_{log['session_id']}"):
                delete_chat_history(log['session_id'], user_id)
                st.rerun()





