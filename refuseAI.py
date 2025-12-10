import streamlit as st
import google.generativeai as genai
import os
import time
import json
import uuid
import re
import base64 

# --- 1. APIキーの設定 ---
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("GOOGLE_API_KEY が設定されていません。Streamlit Secretsまたは環境変数を確認してください。")
    st.stop()

# --- ログファイルのディレクトリ設定 ---
LOGS_DIR = "user_data" 

def get_user_files(user_id):
    """ユーザーIDに基づいてチャットログと進捗ログのパスを生成"""
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR, exist_ok=True)
    return {
        "chat": os.path.join(LOGS_DIR, f"chat_logs_{user_id}.json"),
        "progress": os.path.join(LOGS_DIR, f"element_progress_{user_id}.json"),
        "study_log": os.path.join(LOGS_DIR, f"study_logs_{user_id}.json")
    }

# --- 進捗のロード/セーブ関数 (既存) ---
def load_element_progress(training_elements, user_id):
    """進捗ファイルを読み込む。ない場合や破損時は初期状態を返す。"""
    file_path = get_user_files(user_id)["progress"]
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
    file_path = get_user_files(user_id)["progress"]
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=4)


# --- 学習時間記録関数 (既存) ---
def save_study_session(user_id, start_time, end_time):
    """セッションの開始と終了時刻から学習時間を計算し、ログに追記する"""
    if not start_time or not end_time:
        return

    duration = int(end_time - start_time)
    date_key = time.strftime("%Y-%m-%d", time.localtime(start_time))
    
    file_path = get_user_files(user_id)["study_log"]
    logs = {}
    
    # 既存のログを読み込む
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = {}

    if date_key not in logs:
        logs[date_key] = 0
    
    # 当日の合計学習時間に加算
    logs[date_key] += duration

    # ログを書き戻す
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=4)

# --- 学習時間表示関数 (既存) ---
def load_today_study_time(user_id):
    """当日の合計学習時間（秒）をロードし、分単位で返す"""
    file_path = get_user_files(user_id)["study_log"]
    today_key = time.strftime("%Y-%m-%d")
    
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
                total_seconds = logs.get(today_key, 0)
                # 現在のセッションの経過時間を追加
                if st.session_state.get('session_start_time'):
                    current_duration = time.time() - st.session_state.session_start_time
                    total_seconds += current_duration
                    
                return int(total_seconds // 60) # 分単位で返す
            except json.JSONDecodeError:
                return 0
    return 0


# --- 履歴管理関数 (既存) ---
def save_chat_history(history, user_id):
    file_path = get_user_files(user_id)["chat"]
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
    file_path = get_user_files(user_id)["chat"]
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
                return logs
            except json.JSONDecodeError:
                return []
    return []

def delete_chat_history(session_id_to_delete, user_id):
    file_path = get_user_files(user_id)["chat"]
    logs = load_all_chat_histories(user_id)
    updated_logs = [log for log in logs if log["session_id"] != session_id_to_delete]
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(updated_logs, f, ensure_ascii=False, indent=4)
    st.success("履歴を削除しました！")


# --- テキストの強調表示処理関数 (既存) ---
def highlight_text(text):
    """AIが出力する太字斜体下線マークアップ（_**...**_）を赤色に変換する"""
    highlighted = text.replace("_**", '<span style="color:red; font-weight:bold; text-decoration: underline;">')
    highlighted = highlighted.replace("**_**", '</span>')
    return highlighted


# --- 2. モデルの選択 (既存) ---
model = genai.GenerativeModel('models/gemini-pro-latest')


# --- スクロール機能のヘルパー関数 (既存) ---
def scroll_to_top():
    """ページトップにスクロールするためのJavaScriptを注入する"""
    js = """
    <script>
        window.parent.document.querySelector('section.main').scrollTo(0, 0);
    </script>
    """
    st.markdown(js, unsafe_allow_html=True)
    
def scroll_to_element(element_id):
    """特定の要素IDにスクロールするためのJavaScriptを注入する"""
    # 特定のIDを持つ要素（練習設定サブヘッダー）の場所にスクロールさせる
    js = f"""
    <script>
        var element = window.parent.document.querySelector('[data-testid="stSubheader"]');
        if (element) {{
            element.scrollIntoView({{behavior: "smooth", block: "start"}});
        }} else {{
            # 要素が見つからない場合はトップに戻る
             window.parent.document.querySelector('section.main').scrollTo(0, 0);
        }}
    </script>
    """
    st.markdown(js, unsafe_allow_html=True)


# --- ログアウト関数 (既存) ---
def logout_user():
    """セッション情報をクリアし、強制的にアプリを初期状態に戻す"""
    # 学習時間記録: ログアウト（終了）時間を記録
    if st.session_state.get('user_id'):
        save_study_session(
            st.session_state.user_id,
            st.session_state.get('session_start_time'),
            time.time()
        )
    
    # ユーザーIDをクリア
    if "user_id" in st.session_state:
        del st.session_state["user_id"]
    if "user_id_key" in st.session_state:
        del st.session_state["user_id_key"] # 入力フィールドの内容もクリア
    
    # その他のセッションデータもクリア
    keys_to_delete = ["user_id", "user_id_key", "chat_history", "genai_chat", "initial_prompt_sent", 
                      "current_scenario", "selected_element_display", 
                      "new_session_flag", "element_status", 
                      "scroll_to_top_flag", "practice_mode_select",
                      "training_element_select_display", "session_start_time"] 
    for key in keys_to_delete:
        if key in st.session_state:
            del st.session_state[key]
            
    st.info("ログアウトします。ユーザーIDを再入力してください。")
    time.sleep(0.5)
    st.rerun()


# --- 3. Streamlitアプリのタイトル設定 ---
st.title("誘いを断る練習AI")
st.write("断ることが苦手なあなたのための、コミュニケーション練習アプリです。AIからの誘いを断ってみましょう！")


# ==============================================================================
# ★★★ 新規配置：使い方ガイド (画面上部) ★★★
# ==============================================================================
with st.expander("❓ このシステムの使い方（操作ガイド）", expanded=False):
    st.markdown("""
    ### 🤝 システムの目的
    本システムは、AIからの断りにくい誘いに対して、**適切かつ丁寧な断り方**を練習し、コミュニケーションスキルを向上させることを目的としています。

    ### 📝 ステップ別操作手順

    1.  **🔑 ユーザー認証**:
        * アプリ上部の入力欄に、あなた専用の**ユーザーID**（半角英数字）を入力してください。
        * このIDにより、あなたの**学習進捗（合格状況）**と**会話履歴**が保存・復元されます。

    2.  **📝 練習設定**:
        * **モード選択**: 「要素別トレーニング」で特定のスキルに集中するか、「総合実践」で全てを試すかを選択します。
        * **シナリオ入力**: AIに設定してほしい具体的な状況を入力します。**空欄でも構いません。** (空欄の場合、AIが自動でシナリオを生成します)
        * **開始**: 「▶️ 練習を開始する」ボタンを押すと、ロールプレイングがスタートします。

    3.  **🗣️ 実践エリア**:
        * 上部に表示された**練習モードとシチュエーション**を確認し、AIからの誘いを待ちます。
        * チャット入力欄に、AIの誘いに対するあなたの**断り言葉**を入力し、Enterまたは送信ボタンを押してください。

    4.  **フィードバックと評価**:
        * AIがあなたの断り方について、**表現面**と**内容面**の2つの観点から**10点満点**で評価します。
        * 要素別トレーニングでは、目標を完全に満たした場合に**合格**となります。

    ### ✅ データと履歴の管理
    * **会話履歴の保存**: 会話が終了したら、「✅ 現在の会話履歴を保存」ボタンを押して記録できます。
    * **ログアウト**: 「🚪 ログアウト」ボタンを押すと、現在のセッションが終了します。
    """)
# --------------------------------------------------------------------------


# --- ユーザーID入力セクション ---
st.subheader("🔑 ユーザー認証と進捗のロード")
user_id_input = st.text_input(
    "あなたのユーザーID (半角英数字) を入力してください。進捗と履歴はこのIDで保存されます。",
    key="user_id_key"
)

if not user_id_input:
    st.info("練習を開始するには、まずユーザーIDを入力してください。")
    st.stop()

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

# --- 総合実践モード用の詳細なプロンプトテンプレート ---
SYSTEM_PROMPT_FULL_TEMPLATE = f"""
あなたはユーザーが誘いを断る練習をするためのロールプレイング相手です。

**【AIの役割と設定】**
あなたの役割は、**大学1年生から新卒1年目（社会人経験が浅い層）**のユーザーに対して、**大学生活、サークル、アルバイト、または初めての職場**で起こり得る具体的な誘いのシナリオを提供することです。

--- シナリオ開始 ---
**最初の応答では、以下の指示にのみ従ってください。ユーザーに何か誘いをかけてください。この応答に、ユーザーの断り方に対するフィードバックは絶対に含めないでください。**
**ユーザーがシナリオを入力していない場合、**あなたはターゲット層に合ったランダムな誘い（サークル、バイト、新卒職場など）を自動で設定してください。**
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

# --- 要素別トレーニング用プロンプト生成関数 ---
def create_focused_prompt(element_key, element_description):
    """選択された要素に特化したフィードバックプロンプトを生成する関数 (合否判定あり)"""
    
    score_info = element_description.split('(')[-1].replace(')', '')
    
    focused_prompt = f"""
あなたはユーザーが特定の要素を練習するためのコーチです。
あなたの役割は、ユーザーが断りの練習をする際、冷静にフィードバックを提供することです。

**【AIの役割と設定】**
あなたの役割は、**大学1年生から新卒1年目（社会人経験が浅い層）**のユーザーに対して、**大学生活、サークル、アルバイト、または初めての職場**で起こり得る具体的な誘いのシナリオを提供することです。

--- 練習目標 ---
このモードの目的は、**特定のスキル習得に集中**することです。
ユーザーの断り方を評価する際、**{element_key} (配点: {score_info})** の項目**のみ**を評価対象としてください。**他の項目、および総合点数や合否は一切無視し、絶対に点数を付けないでください。**

--- シナリオ開始 ---
最初の応答では、以下の指示にのみ従ってください。ユーザーに何か誘いをかけてください。この応答に、ユーザーの断り方に対するフィードバックは絶対に含めないでください。
**ユーザーがシナリオを入力していない場合、**あなたはターゲット層に合ったランダムな誘い（サークル、バイト、新卒職場など）を自動で設定してください。**
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

# --- セッションステートの初期化 ---
if "chat_history" not in st.session_state or "user_id" not in st.session_state or st.session_state.user_id != user_id:
    
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    st.session_state.initial_prompt_sent = False
    st.session_state.current_scenario = None
    st.session_state.user_id = user_id
    st.session_state.selected_element_display = "総合実践"
    st.session_state.new_session_flag = False
    
    # ログイン（開始）時刻を記録
    st.session_state.session_start_time = time.time()
    
    # 要素別トレーニングの合格状況をファイルからロードする
    st.session_state.element_status = load_element_progress(training_elements, user_id)
    
    # スクロール制御の初期化
    st.session_state.scroll_to_top_flag = False


# --- UI制御 ---
st.subheader("📝 練習設定")

# スクロール処理の実行
if st.session_state.scroll_to_top_flag:
    scroll_to_top()
    st.session_state.scroll_to_top_flag = False
# ---------------------------------

# 練習モードの選択 (ロック機能の実装)
all_elements_passed = all(st.session_state.element_status.values())

if all_elements_passed:
    st.success("🎉 すべての要素を合格しました！総合実践モードが解放されました。")
    mode_options = ('総合実践 (全要素を評価)', '要素別トレーニング (一点集中)')
else:
    st.warning("総合実践は、すべての要素別トレーニング（6要素）を合格後に解放されます。")
    mode_options = ('総合実践 (ロック中)', '要素別トレーニング (一点集中)')

initial_index = 1
if 'practice_mode_select' in st.session_state:
    try:
        initial_index = mode_options.index(st.session_state.practice_mode_select)
    except ValueError:
        initial_index = 1

practice_mode = st.radio(
    "1. 練習モードを選択してください:",
    mode_options,
    index=initial_index,
    key='practice_mode_select'
)

if not all_elements_passed and practice_mode == '総合実践 (ロック中)':
    practice_mode = '要素別トレーニング (一点集中)'
    st.session_state.selected_element_display = "総合実践"

# 要素ポイントの表示 (Expanderで常に開閉可能にする)
st.markdown("---")
st.markdown("### 🏆 要素別トレーニングの進捗と目標")

# 修正: element_keys をここで定義する
element_keys = list(training_elements.keys())

# 選択アクションがあったかどうかをチェックする変数
element_selection_made = False

# --- 1. 目標確認と選択ボタンの統合 ---
# 選択された要素を一時的に保持するためのキーを定義
ELEMENT_SELECT_KEY = 'selected_element_for_practice'

for i, key in enumerate(element_keys):
    passed = st.session_state.element_status[key]
    icon = "✅" if passed else "❌"
    
    # 要素名（点数除く）
    element_name_simple = key.split(' (')[0]
    
    # 現在この要素が選択中かどうかをチェック
    is_current_selection = (st.session_state.get('selected_element_display') == element_name_simple)
    
    # 選択中の要素はExpanderを強制的に開く
    expander_label = f"{icon} **{element_name_simple}**"
    if is_current_selection:
        expander_label += " (✨ 現在の目標)"
    
    with st.expander(expander_label, expanded=is_current_selection):
        st.markdown(f"**目標**:\n- {training_elements[key]}")
        
        # 集中モードが選択されている場合のみボタンを表示
        if practice_mode == '要素別トレーニング (一点集中)':
            
            # ボタンが押された場合の処理を定義するクロージャ (ボタンのキーが競合しないようにする)
            def handle_element_selection(selected_key, display_name):
                st.session_state[ELEMENT_SELECT_KEY] = selected_key
                st.session_state.selected_element_display = display_name
                st.info(f"目標を **'{display_name}'** に設定しました。")
                st.rerun()

            # ボタンのキーが個々にユニークであることを保証
            button_key = f"select_{i}_{key.replace(' ', '_')}"
            
            if st.button("この要素を選択する", key=button_key, disabled=is_current_selection):
                # クロージャを使って選択処理を実行
                st.session_state[ELEMENT_SELECT_KEY] = key
                st.session_state.selected_element_display = element_name_simple
                element_selection_made = True
                st.rerun() # ★ここで再実行をトリガーする★


st.markdown("---")

# --- 2. 選択された要素をセッションステートに反映し、メインロジックで使用可能にする ---
current_selected_element_display = "総合実践"
selected_element = None

# ロジックの最上部で初期化
if practice_mode == '総合実践 (全要素を評価)' or practice_mode == '総合実践 (ロック中)':
    st.session_state[ELEMENT_SELECT_KEY] = None
    current_selected_element_display = "総合実践"
    
elif st.session_state.get(ELEMENT_SELECT_KEY) is not None:
    # ボタンで選択された値がセッションステートにある場合
    selected_element = st.session_state[ELEMENT_SELECT_KEY]
    current_selected_element_display = st.session_state.selected_element_display
    
    st.success(f"✅ 選択中の集中要素: **{current_selected_element_display}**")
    
# 要素別モードが選択されているのに要素が未選択の場合
# (再実行時に element_selection_made はリセットされるため、このチェックは不要だが、
#  st.session_state[ELEMENT_SELECT_KEY] が None の場合に警告を表示する)
elif practice_mode == '要素別トレーニング (一点集中)' and st.session_state.get(ELEMENT_SELECT_KEY) is None:
    st.warning("☝️ 上のリストから、集中して練習する要素を一つ選択してください。")
    
    # 選択されていない場合は、ダミーとして最初の要素を割り当てておく
    selected_element = element_keys[0] if element_keys else None
    
    
# --- 選択UIの統合終了 ---

# ユーザーがシナリオを入力するUI
st.markdown("### 2. シナリオの入力 (オプション)")

# 課題解消: シナリオ入力の説明強化 ＆ 必須解除
st.info("💡 **希望するシナリオがない場合は空欄のまま**で構いません。空欄の場合、AIが自動でシナリオを生成します。")
scenario_input = st.text_area(
    "【任意】誘い手（誰から）、誘いの内容、断りにくさのレベル（低・中・高）を具体的に入力してください。",
    height=100,
    key="scenario_input"
)

# シナリオ入力が空欄でもボタンを有効にする
start_button_disabled = (practice_mode == '要素別トレーニング (一点集中)' and not selected_element)

# 「練習を開始する」ボタン
if st.button("▶️ 練習を開始する", disabled=start_button_disabled, key="start_button_main"):
    
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    
    st.session_state.initial_prompt_sent = False
    st.session_state.current_scenario = scenario_input.strip() # 入力がない場合は空文字列を渡す
    st.session_state.new_session_flag = True
    
    st.session_state.selected_element_display = current_selected_element_display
    
    # スクロールロジックは会話エリアの直後に誘導
    st.rerun()


st.markdown("---")
st.subheader("🗣️ ロールプレイング実践エリア")
# --------------------------------------------------------------------------

# --- 課題解消: 選択中の要素をロールプレイング画面で確認できるようにする ---
if st.session_state.get("current_scenario") is not None and st.session_state.initial_prompt_sent:
    
    mode_name = "総合実践 (全要素評価)"
    element_name = ""
    display_text = st.session_state.get("selected_element_display")
    
    if display_text and display_text != "総合実践":
        mode_name = f"要素別トレーニング"
        element_name = f" | 目標: **{display_text}**"
        
    st.markdown(f"**練習モード:** {mode_name}{element_name}")
    
    # シナリオ入力が空の場合の表示を調整
    scenario_display = st.session_state.current_scenario if st.session_state.current_scenario else "AIがランダムに設定"
    st.info(f"シチュエーション: **{scenario_display}**")
    
else:
    st.warning("「練習設定」エリアで設定を入力し、「練習を開始」ボタンを押してください。")


# --- 7. AIからの最初の誘いを生成し表示 (ロジック分岐) ---
if st.session_state.get("new_session_flag", False):
    
    st.session_state.new_session_flag = False 
    
    # シナリオ入力が空欄の場合の処理
    scenario_input_value = st.session_state.current_scenario
    
    if not scenario_input_value:
        # 入力がない場合、AIにランダム生成を指示するテキストをセット
        scenario_text = "**ユーザーはシナリオを指定しませんでした。ターゲット層（大学1年〜新卒1年）に合った、断りにくい誘いを一つ自動で設定してください。**"
    else:
        scenario_text = f"**ユーザーが設定したシナリオ:** {scenario_input_value}"
    
    
    element_key_for_prompt = next((key for key in training_elements if st.session_state.selected_element_display in key), None)
    
    if st.session_state.selected_element_display != "総合実践" and element_key_for_prompt:
        combined_prompt = create_focused_prompt(element_key_for_prompt, training_elements[element_key_for_prompt])
        combined_prompt += f"\n\n{scenario_text}"
    elif st.session_state.selected_element_display == "総合実践":
            combined_prompt = f"{SYSTEM_PROMPT_FULL_TEMPLATE}\n\n{scenario_text}"
    else:
            combined_prompt = "" 
    
    if combined_prompt:
        with st.spinner("AIが誘いを考えています..."):
            initial_response = st.session_state.genai_chat.send_message(combined_prompt)
            st.session_state.chat_history.append({"role": "assistant", "content": initial_response.text})
            st.session_state.initial_prompt_sent = True
            
            # View維持
            st.rerun()
    else:
        st.error("プロンプトの生成に失敗しました。設定を見直してください。")
        st.stop()


# --- 8. 会話履歴の表示 ---
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            st.markdown(highlight_text(message["content"]), unsafe_allow_html=True)
        else:
            st.markdown(message["content"])

# --- 9. ユーザー入力の処理 ---
user_input = st.chat_input("あなたの断り言葉を入力してください", disabled=not st.session_state.initial_prompt_sent)

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.spinner("AIが返答を考えています..."):
        ai_response = st.session_state.genai_chat.send_message(user_input)
        response_text = ai_response.text

        # 合否判定チェック
        if st.session_state.selected_element_display != "総合実践":
            match = re.search(r"【合否判定】:\s*(合格|不合格)", response_text)
            
            if match:
                current_element_key = next((key for key in training_elements if st.session_state.selected_element_display in key), None)
                
                if current_element_key and match.group(1) == "合格":
                    if not st.session_state.element_status[current_element_key]:
                        st.session_state.element_status[current_element_key] = True
                        save_element_progress(st.session_state.element_status, user_id)
                        response_text += "\n\n🎉 **おめでとうございます！この要素を合格しました。** 次の要素に進むか、すべての要素合格後に総合実践に挑戦しましょう！"
                
                response_text = response_text.replace("【合否判定】: 合格", "**【合否判定】: <span style='color:green;'>合格</span>**")
                response_text = response_text.replace("【合否判定】: 不合格", "**【合否判定】: <span style='color:red;'>不合格</span>**")


        st.session_state.chat_history.append({"role": "assistant", "content": response_text})
        with st.chat_message("assistant"):
            st.markdown(highlight_text(response_text), unsafe_allow_html=True)

    time.sleep(1)
    st.rerun()

st.markdown("---")
st.subheader("✅ データ管理")

# 「新しい練習を始める」ボタン
if st.button("🔄 新しい練習を始める（設定エリアへ戻る）", key="reset_and_go_to_settings"):
    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    st.session_state.initial_prompt_sent = False
    st.session_state.current_scenario = None
    st.session_state.selected_element_display = "総合実践"
    
    # 練習設定のサブヘッダーにスクロール
    st.session_state.scroll_to_top_flag = True
    st.rerun()
    
if st.button("✅ 現在の会話履歴を保存", key="save_button_view2"):
    if st.session_state.chat_history:
        save_chat_history(st.session_state.chat_history, user_id)
    else:
        st.warning("保存する会話履歴がありません。")

# ログアウトボタン
st.markdown("---")
if st.button("🚪 ログアウト", key="logout_button"):
    
    # ログアウト関数を呼び出す
    logout_user()


# ==============================================================================
# 履歴と分析 (画面下部に配置)
# ==============================================================================
st.markdown("---")
st.subheader("📚 これまでの練習履歴")

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

            if st.button(f"このセッションを削除 ({log['session_id'][-4:]})", key=f"delete_btn_{log['session_id']}"):
                delete_chat_history(log['session_id'], user_id)
                st.rerun()
                
st.markdown("---")
if st.button("すべての要素の進捗をリセット (研究用)", key="full_reset_button_view3"):
    st.session_state.element_status = {key: False for key in training_elements.keys()}
    progress_file_path = get_user_files(user_id)["progress"]
    if os.path.exists(progress_file_path):
        os.remove(progress_file_path)

    st.session_state.chat_history = []
    st.session_state.genai_chat = model.start_chat(history=[])
    st.session_state.initial_prompt_sent = False
    st.session_state.selected_element_display = "総合実践"
    
    st.info(f"ID: {user_id} の進捗がリセットされました。")
    scroll_to_top()
    st.rerun()




