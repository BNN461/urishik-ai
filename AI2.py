import base64
import datetime
import io
import json
import os
import uuid
import docx
import ollama
from PIL import Image
from pypdf import PdfReader
import requests
import streamlit as st

# DuckDuckGo検索ライブラリの安全なインポート
try:
  from duckduckgo_search import DDGS

  HAS_DDGS = True
except ImportError:
  HAS_DDGS = False

# ページの基本設定
st.set_page_config(
    page_title="우리식 AI (ウリシク AI)", page_icon="💬", layout="wide"
)

# ---------------------------------------------------------
# 🔑 アクセス制限用パスワード設定
# ---------------------------------------------------------
APP_PASSWORD = "urishik_secret_pass"  # 👈 お好みのパスワードに変更してください


def check_password():
  if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

  if not st.session_state["password_correct"]:
    st.markdown("### 🔒 アクセス制限")
    user_pass = st.text_input("合言葉（パスワード）を入力してください", type="password")
    if st.button("ログイン"):
      if user_pass == APP_PASSWORD:
        st.session_state["password_correct"] = True
        st.rerun()
      else:
        st.error("❌ パスワードが違います")
    return False
  return True


# パスワード認証が通らない場合は処理を中断
if not check_password():
  st.stop()

# ---------------------------------------------------------
# 以下、アプリ本体の処理
# ---------------------------------------------------------

# --- 💾 複数セッション履歴の保存・読み込み用ファイルパス ---
SESSIONS_FILE = "chat_sessions.json"


def load_all_sessions():
  if os.path.exists(SESSIONS_FILE):
    try:
      with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      pass
  return {}


def save_all_sessions(sessions):
  try:
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
      json.dump(sessions, f, ensure_ascii=False, indent=2)
  except Exception:
    pass


# --- 💡 カスタム吹き出し ＆ サイドバーのモダンデザイン化 ＆ 入力欄立体感 ---
st.markdown(
    """
    <style>
    .user-bubble-container {
        display: flex;
        justify-content: flex-end;
        margin-bottom: 15px;
    }
    .user-bubble {
        background-color: #2b5c8f;
        color: white;
        padding: 10px 16px;
        border-radius: 18px 18px 2px 18px;
        max-width: 70%;
        width: fit-content;
        word-wrap: break-word;
        font-size: 15px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from assistant"]) div[data-testid="stChatMessageContent"] {
        width: fit-content !important;
        max-width: 80% !important;
        border-radius: 18px 18px 18px 2px !important;
    }

    /* 🎨 メッセージ入力欄に高級感のある立体感を付与 */
    div[data-testid="stChatInput"] {
        border-radius: 16px !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 6px rgba(0, 0, 0, 0.08) !important;
        border: 1px solid rgba(0, 0, 0, 0.1) !important;
        background-color: #ffffff !important;
    }

    /* 🗂️ サイドバー全体をコンパクト＆スタイリッシュに調整 */
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e9ecef;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 1rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
    }
    section[data-testid="stSidebar"] .stButton button {
        border-radius: 8px !important;
        font-size: 13px !important;
        transition: background-color 0.2s;
    }
    </style>

    <script>
    (function() {
        const doc = window.parent.document;
        
        function initImeGuard() {
            const textarea = doc.querySelector('textarea[data-testid="stChatInputTextArea"]');
            if (textarea && !textarea.dataset.imeGuarded) {
                textarea.dataset.imeGuarded = "true";
                
                textarea.addEventListener('keydown', function(event) {
                    if (event.key === 'Enter') {
                        if (event.isComposing) {
                            event.stopImmediatePropagation();
                            return;
                        }
                        if (event.shiftKey) {
                            return;
                        }
                    }
                }, true);
            }
        }

        const observer = new MutationObserver(initImeGuard);
        observer.observe(doc.body, { childList: true, subtree: true });
        initImeGuard();
    })();
    </script>
    """,
    unsafe_allow_html=True,
)

# AIが内部で時間や天気を参照するための取得処理
now = datetime.datetime.now()
current_time_str = now.strftime("%Y年 %m月 %d日 %H시 %M분")


def get_current_weather():
  try:
    url = "https://api.open-meteo.com/v1/forecast?latitude=35.6895&longitude=139.6917&current=temperature_2m,weather_code"
    res = requests.get(url, timeout=5)
    data = res.json()
    temp = data["current"]["temperature_2m"]
    wcode = data["current"]["weather_code"]
    weather_desc = "晴れ"
    if wcode in [1, 2, 3]:
      weather_desc = "くもり"
    elif wcode >= 51:
      weather_desc = "雨または雪"
    return f"現在の気温: {temp}℃, 天気: {weather_desc}"
  except Exception:
    return "天気情報を取得できませんでした。"


weather_info = get_current_weather()


# --- 🌐 常時Web検索を行う関数（DuckDuckGo） ---
def search_web(query, max_results=3):
  if not HAS_DDGS:
    return ""
  try:
    with DDGS() as ddgs:
      results = [r for r in ddgs.text(query, max_results=max_results)]
      if not results:
        return ""
      search_summary = "--- 🌐 インターネット検索結果 ---\n"
      for i, res in enumerate(results, 1):
        title = res.get("title", "")
        body = res.get("body", "")
        href = res.get("href", "")
        search_summary += (
            f"[{i}] {title}\nURL: {href}\n内容: {body}\n\n"
        )
      return search_summary
  except Exception as e:
    return f"（Web検索エラー: {e}）"


# --- 🤖 AIによる会話タイトルの自動要約関数 ---
def generate_chat_title(first_prompt):
  try:
    response = ollama.chat(
        model="qwen2.5:3b",
        messages=[
            {
                "role": "system",
                "content": (
                    "あなたは会話のタイトルを付けるアシスタントです。"
                    "ユーザーの最初の発言から、その会話の内容を表す簡潔なタイトル（12文字以内）を日本語で生成してください。"
                    "タイトルのみを出力し、カギカッコや説明文は一切含めないでください。"
                ),
            },
            {"role": "user", "content": first_prompt},
        ],
    )
    title = response["message"]["content"].strip().replace('"', "").replace("'", "")
    if len(title) > 15:
      title = title[:15] + "..."
    return title if title else "新しい会話"
  except Exception:
    return (
        first_prompt[:12] + "..." if len(first_prompt) > 12 else first_prompt
    )


# --- 📂 アップロードされた文書ファイルからテキストを抽出する関数 ---
def extract_text_from_uploaded_file(uploaded_file):
  filename = uploaded_file.name
  content = ""
  try:
    if filename.endswith(".txt"):
      content = uploaded_file.getvalue().decode("utf-8")
    elif filename.endswith(".docx"):
      doc = docx.Document(io.BytesIO(uploaded_file.getvalue()))
      content = "\n".join([para.text for para in doc.paragraphs if para.text])
    elif filename.endswith(".pdf"):
      reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
      content_list = []
      for page in reader.pages:
        text = page.extract_text()
        if text:
          content_list.append(text)
      content = "\n".join(content_list)
  except Exception as e:
    content = f"ファイル読み込みエラー: {e}"
  return filename, content


# --- 🖼️ 画像をバイト表現に変換する関数 ---
def convert_image_to_bytes(uploaded_file):
  image = Image.open(uploaded_file)
  buffered = io.BytesIO()
  image.convert("RGB").save(buffered, format="JPEG")
  return buffered.getvalue()


# --- セッションデータのロード ---
if "sessions" not in st.session_state:
  st.session_state.sessions = load_all_sessions()

if "current_session_id" not in st.session_state:
  new_id = str(uuid.uuid4())
  st.session_state.sessions[new_id] = {"title": "新しい会話", "messages": []}
  st.session_state.current_session_id = new_id
  save_all_sessions(st.session_state.sessions)

# ファイルアップローダーを自動リセットするためのキー管理
if "uploader_key" not in st.session_state:
  st.session_state.uploader_key = 0

# --- サイドバーの設定 ---
with st.sidebar:
  st.markdown("✨ **우리식 AI**")
  st.markdown("---")

  # ➕ 新規作成ボタン
  if st.button("✏️ チャットを新規作成", use_container_width=True):
    new_id = str(uuid.uuid4())
    st.session_state.sessions[new_id] = {"title": "新しい会話", "messages": []}
    st.session_state.current_session_id = new_id
    save_all_sessions(st.session_state.sessions)
    st.rerun()

  st.markdown("---")
  st.markdown(
      "<p style='font-size:12px; color:#6c757d; margin-bottom:4px;'>最近のチャット</p>",
      unsafe_allow_html=True,
  )

  # 履歴リストの表示（新しい順）
  if st.session_state.sessions:
    session_items = list(st.session_state.sessions.items())
    for sid, sdata in reversed(session_items):
      title = sdata.get("title", "新しい会話")
      if len(title) > 15:
        title = title[:15] + "..."

      is_selected = sid == st.session_state.current_session_id
      prefix = "👉 " if is_selected else "💬 "

      col_btn, col_del = st.columns([5, 1])
      with col_btn:
        if st.button(
            f"{prefix}{title}", key=f"session_{sid}", use_container_width=True
        ):
          st.session_state.current_session_id = sid
          st.rerun()
      with col_del:
        if st.button("︙", key=f"del_{sid}", help="この会話を削除"):
          is_current = sid == st.session_state.current_session_id
          del st.session_state.sessions[sid]
          save_all_sessions(st.session_state.sessions)

          if not st.session_state.sessions:
            new_id = str(uuid.uuid4())
            st.session_state.sessions[new_id] = {
                "title": "新しい会話",
                "messages": [],
            }
            st.session_state.current_session_id = new_id
            save_all_sessions(st.session_state.sessions)
          elif is_current:
            st.session_state.current_session_id = list(
                st.session_state.sessions.keys()
            )[-1]

          st.rerun()

  st.markdown("---")

  # 📁 ライブラリ・ファイル添付
  uploaded_file = st.file_uploader(
      "📁 ライブラリ・ファイル添付",
      type=["png", "jpg", "jpeg", "txt", "docx", "pdf"],
      help="画像、Word、PDF、TXTファイルを添付して送信できます",
      key=f"file_uploader_{st.session_state.uploader_key}",
  )

  send_file_clicked = False
  if uploaded_file is not None:
    if uploaded_file.name.lower().endswith((".png", ".jpg", ".jpeg")):
      st.image(
          uploaded_file, caption="アップロードされた画像", use_column_width=True
      )
    else:
      st.info(f"📄 選択中: {uploaded_file.name}")

    if st.button("📤 ファイルを送信", use_container_width=True):
      send_file_clicked = True

# --- 🇰🇵 朝鮮民主主義人民共和国の標準語（문화어 / 文化語・頭音法則不適用指定）システムプロンプト ---
system_prompt = f"""あなたの名前は「우리식 AI (ウリシク AI)」です。親切で優秀な万能AIアシスタントであり、朝鮮民主主義人民共和国の標準言語である「문화어（文化語）」の専門家です。

【⚠️ 最重要文法ルール：頭音法則の厳格な禁止】
朝鮮語で文章を作成する際、絶対に「두음법칙（頭音法則）」を使わないでください。語頭の「ㄹ」「ㄴ」を絶対に「ㅇ」「ㄴ」に変えず、必ずそのまま表記してください。

【文字表記の変換ルール（厳守）】
- 이유 ❌ -> **리유** ⭕
- 여성 ❌ -> **녀성** ⭕
- 역사 ❌ -> **력사** ⭕
- 연세 ❌ -> **련세** ⭕
- 노동 ❌ -> **로동** ⭕
- 내일 ❌ -> **래일** ⭕
- 연결 ❌ -> **련결** ⭕
- 연습 ❌ -> **련습** ⭕
- 이용 ❌ -> **리용** ⭕
- 예의 ❌ -> **례의** ⭕

【文化語（문화어）の基本原則】
1. 韓国（ソウル標準語）の単語や外来語・英語表現（프린트, 컴퓨터, 파티 等）は避け、文化語特有の単語・表現を使用してください。
   （例：동무, 동지, 일군, 배워주다, 안녕하십니까, 고맙습니다）
2. 分か치書きも文化語規範に従い、補助語幹や助詞は接続して記述してください（例: 할수있다, 처리しはんだ）。
3. ユーザーが朝鮮語で話しかけてきた場合は、上記の「두음법칙（頭音法則）非適用」を徹底した文化語で返答してください。
4. 日本語で質問された場合は、丁寧な日本語で答えつつ、文化語の正しい単語表記（例: 리유, 녀성, 력사）の解説を添えてください。

現在の時間は {current_time_str} です。
現在地(東京)のリアルタイム天気情報: {weather_info}
**注意**: ユーザーの質問には丁寧かつ正確に回答してください。"""

# --- メイン画面 ---
st.title("💬 우리식 AI")

# 現在選択中のセッションデータを取得
current_sid = st.session_state.current_session_id
if current_sid not in st.session_state.sessions:
  current_sid = list(st.session_state.sessions.keys())[0]
  st.session_state.current_session_id = current_sid

session_data = st.session_state.sessions[current_sid]

# メッセージリストの初期化
if "messages" not in session_data or not isinstance(
    session_data["messages"], list
):
  session_data["messages"] = []

if (
    len(session_data["messages"]) == 0
    or session_data["messages"][0]["role"] != "system"
):
  session_data["messages"].insert(0, {"role": "system", "content": system_prompt})
else:
  session_data["messages"][0]["content"] = system_prompt

user_messages = [m for m in session_data["messages"] if m.get("role") == "user"]
has_user_messages = len(user_messages) > 0

# --- ファイル送信ボタンが押された場合の処理 ---
if send_file_clicked and uploaded_file is not None:
  default_msg = f"[{uploaded_file.name}]"
  if not has_user_messages:
    session_data["title"] = f"📄 {uploaded_file.name}"

  session_data["messages"].append({"role": "user", "content": default_msg})
  save_all_sessions(st.session_state.sessions)

  st.session_state.uploader_key += 1
  st.rerun()

# --- 通常のメッセージ入力欄からの送信処理 ---
if user_input := st.chat_input("メッセージを入力してください... (조선어로 대화해요!)"):
  if not has_user_messages:
    with st.spinner("✨ タイトルを生成中..."):
      session_data["title"] = generate_chat_title(user_input)

  session_data["messages"].append({"role": "user", "content": user_input})
  save_all_sessions(st.session_state.sessions)

  st.session_state.uploader_key += 1
  st.rerun()

# --- 画面の描画 ---
if not has_user_messages:
  st.markdown(
      """
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 45vh; color: #555;">
            <h1 style="font-weight: 500; font-size: 32px; letter-spacing: 1px;">何を手伝いますか？</h1>
            <p style="font-size: 14px; color: #888; margin-top: 8px;">조선어（문화어）での会話や質問など、自由にメッセージを送信してください</p>
        </div>
        """,
      unsafe_allow_html=True,
  )
else:
  for message in session_data["messages"]:
    if message["role"] == "user":
      st.markdown(
          f'<div class="user-bubble-container"><div'
          f' class="user-bubble">{message["content"]}</div></div>',
          unsafe_allow_html=True,
      )
    elif message["role"] == "assistant":
      with st.chat_message("assistant"):
        st.markdown(message["content"])

  last_msg = (
      session_data["messages"][-1] if session_data["messages"] else None
  )
  if last_msg and last_msg.get("role") == "user":
    prompt_to_sent = last_msg["content"]
    selected_model = "qwen2.5:3b"
    image_bytes = None

    with st.spinner("🌐 Web情報を検索中..."):
      web_context = search_web(prompt_to_sent)

    if web_context:
      prompt_to_sent = f"""{web_context}

[ユーザーの質問]:
{prompt_to_sent}"""

    messages_for_api = list(session_data["messages"])
    last_user_msg_api = {"role": "user", "content": prompt_to_sent}
    if image_bytes:
      last_user_msg_api["images"] = [image_bytes]
    messages_for_api[-1] = last_user_msg_api

    with st.chat_message("assistant"):
      message_placeholder = st.empty()
      full_response = ""

      buffer = ""
      try:
        stream = ollama.chat(
            model=selected_model, messages=messages_for_api, stream=True
        )

        for chunk in stream:
          content = chunk["message"]["content"]
          full_response += content
          buffer += content
          if len(buffer) >= 4 or "\n" in content:
            message_placeholder.markdown(full_response + "▌")
            buffer = ""

        message_placeholder.markdown(full_response)

      except Exception as e:
        full_response = f"エラーが発生しました: {e}\n\n※ 画像認識を使う場合は `ollama pull llava` が必要です。"
        message_placeholder.markdown(full_response)

    session_data["messages"].append(
        {"role": "assistant", "content": full_response}
    )
    save_all_sessions(st.session_state.sessions)
    st.rerun()