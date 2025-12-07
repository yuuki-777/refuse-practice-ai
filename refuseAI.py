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
        "progress": os.path.join(LOGS_DIR, f"element_progress_{user_id}.json")
    }

# --- 進捗のロード/セーブ関数 ---
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


# --- 履歴管理関数 ---
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


# --- テキストの強調表示処理関数 ---
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
4. フィード
