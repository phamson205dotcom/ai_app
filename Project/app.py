import os
import time
import pandas as pd
import plotly.express as px
import streamlit as st
from audio_recorder_streamlit import audio_recorder
from google import genai

from VoiceService import VoiceService
from PBIPHandler  import PBIPHandler

# -----------------------------------------------------------------------------
# 1. CẤU HÌNH TRANG & SERVICES
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Data Analyst Executive Dashboard",
    layout="wide",
)

GEMINI_API_KEY = "AQ.Ab8RN6IXXveW1kFkg2VhfKmKyRVEMBoJ1yxyl6FKsFD_fvy29w"

@st.cache_resource
def get_gemini_client():
    if GEMINI_API_KEY:
        return genai.Client(api_key=GEMINI_API_KEY)
    return None

@st.cache_resource
def get_voice_service():
    ffmpeg_bin = r"C:\ffmpeg\bin"
    if os.path.exists(ffmpeg_bin) and ffmpeg_bin not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + ffmpeg_bin
    return VoiceService(model_size="medium")

gemini_client = get_gemini_client()
voice_service = get_voice_service()

CANDIDATE_MODELS = [
    "gemini-2.0-flash-lite-001",
    "gemini-3.5-flash",
    "gemini-2.5-pro"
]

# -----------------------------------------------------------------------------
# 2. KHỞI TẠO SESSION STATE
# -----------------------------------------------------------------------------
for key, default in [
    ("chat_history", []),
    ("pending_query", None),
    ("current_audio_path", None),
    ("recorder_key", 0),
    ("chat_session", None),
    ("loaded_file_name", None),
    ("active_model_name", CANDIDATE_MODELS[0]),
    ("df_data", None)
]:
    if key not in st.session_state:
        st.session_state[key] = default

# -----------------------------------------------------------------------------
# 3. HÀM KHỞI TẠO CHAT SESSION
# -----------------------------------------------------------------------------
def build_system_instruction(df: pd.DataFrame = None) -> str:
    data_summary = ""
    if df is not None:
        data_summary = f"""
--- BÁO CÁO DỮ LIỆU ĐẦU VÀO ---
- Tổng số dòng: {len(df)}
- Danh sách các cột: {list(df.columns)}
- Kiểu dữ liệu:\n{df.dtypes.to_string()}
- 5 dòng dữ liệu mẫu đầu tiên:\n{df.head(5).to_string()}
- Thống kê các cột số:\n{df.describe().to_string()}
--------------------------------
"""
    return f"""
Bạn là một Chuyên viên Phân tích Dữ liệu và Trợ lý Lãnh đạo cấp cao.
Nhiệm vụ của bạn là trả lời các câu hỏi dựa trên Báo cáo Dữ liệu.
{data_summary}
YÊU CẦU: Ngắn gọn, chính xác, lịch sự. Tất cả từ tiếng Anh đặt trong dấu *...*.
"""

def init_or_update_chat_session(df: pd.DataFrame = None, target_model: str = None) -> bool:
    if gemini_client is None:
        return False

    system_instruction = build_system_instruction(df)
    models_to_try = [target_model] if target_model else CANDIDATE_MODELS

    history_payload = []
    for item in st.session_state.chat_history:
        role = "user" if item["role"] == "user" else "model"
        history_payload.append({"role": role, "parts": [{"text": item["content"]}]})

    for model_name in models_to_try:
        try:
            st.session_state.chat_session = gemini_client.chats.create(
                model=model_name,
                config={"system_instruction": system_instruction},
                history=history_payload if history_payload else None
            )
            st.session_state.active_model_name = model_name
            return True
        except Exception:
            continue
    return False

def load_data_file(uploaded_file):
    file_name = uploaded_file.name
    if file_name.endswith(('.xlsx', '.xls')):
        return pd.read_excel(uploaded_file)
    elif file_name.endswith('.csv'):
        for encoding in ['utf-8-sig', 'utf-8', 'cp1252', 'latin1', 'utf-16']:
            try:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, encoding=encoding)
            except Exception:
                continue
        raise ValueError("Không thể tự động đọc file CSV này.")
    raise ValueError("Định dạng file không hỗ trợ.")

# -----------------------------------------------------------------------------
# 4. SIDEBAR - TẢI FILE DỮ LIỆU VÀ FILE PBIP (ZIP)
# -----------------------------------------------------------------------------
st.sidebar.title("📁 Quản lý Dữ liệu & PBIP")

# 1. Tải file dữ liệu
uploaded_data = st.sidebar.file_uploader(
    "1. Tải file dữ liệu (.xlsx / .csv)", type=["xlsx", "csv"]
)

if uploaded_data:
    try:
        if st.session_state.loaded_file_name != uploaded_data.name:
            df_loaded = load_data_file(uploaded_data)
            st.session_state.df_data = df_loaded
            st.session_state.loaded_file_name = uploaded_data.name
            init_or_update_chat_session(st.session_state.df_data)
            st.sidebar.info("💡 Đã cập nhật dữ liệu cho AI!")
        st.sidebar.success(f"✅ Đã nạp dữ liệu: {len(st.session_state.df_data):,} dòng")
    except Exception as e:
        st.sidebar.error(f"Lỗi đọc file: {e}")
else:
    if st.session_state.chat_session is None:
        init_or_update_chat_session(None)

st.sidebar.markdown("---")

# 2. Tải file PBIP dưới dạng ZIP
uploaded_pbip_zip = st.sidebar.file_uploader(
    "2. Tải dự án Power BI (.zip)", type=["zip"],
    help="Nén folder dự án .pbip (gồm cả thư mục .Report) thành file .zip và upload vào đây"
)

# Khởi tạo PBIP Handler tùy theo việc người dùng upload ZIP hay dùng mẫu có sẵn
if uploaded_pbip_zip:
    pbip_handler = PBIPHandler(uploaded_zip_file=uploaded_pbip_zip)
    st.sidebar.success("✅ Đã nạp giao diện từ ZIP PBIP!")
else:
    # Sử dụng folder mẫu mặc định nếu chưa upload
    pbip_handler = PBIPHandler(pbip_folder_path="./sale_sample")

st.sidebar.markdown("---")

if st.sidebar.button("🗑️ Xóa lịch sử Chat"):
    st.session_state.chat_history = []
    st.session_state.pending_query = None
    st.session_state.current_audio_path = None
    init_or_update_chat_session(st.session_state.df_data)
    st.rerun()

st.sidebar.caption(f"🤖 Active Model: `{st.session_state.active_model_name}`")

# -----------------------------------------------------------------------------
# 5. GIAO DIỆN CHÍNH
# -----------------------------------------------------------------------------
col_data, col_ai = st.columns([2, 1])

# ===== CỘT 1: DASHBOARD DỰNG TỪ PBIP HANDLER =====
with col_data:
    st.title("📊 Financial Performance Dashboard")
    # Gọi hàm dựng layout từ Class PBIPHandler
    pbip_handler.render_dashboard(st.session_state.df_data)

# ===== CỘT 2: VOICE & CHAT BOT AI =====
with col_ai:
    st.subheader("🎙️ Trợ lý Phân tích AI")

    chat_container = st.container(height=380)
    with chat_container:
        if not st.session_state.chat_history:
            st.caption("Bấm mic hoặc nhập câu hỏi bên dưới!")
        else:
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.write(message["content"])

    if st.session_state.current_audio_path and os.path.exists(st.session_state.current_audio_path):
        st.audio(st.session_state.current_audio_path, format="audio/mp3", autoplay=True)

    st.markdown("---")
    st.write("🗣️ **Hỏi bằng Giọng nói:**")
    
    audio_bytes = audio_recorder(
        text="Bấm để nói",
        recording_color="#e8b62c",
        neutral_color="#6aa36f",
        icon_name="microphone",
        icon_size="1x",
        key=f"audio_recorder_{st.session_state.recorder_key}"
    )

    user_text_input = st.chat_input("Hoặc gõ câu hỏi...")

    if audio_bytes:
        with st.spinner("⚡ Whisper đang nhận diện giọng nói..."):
            recognized_text = voice_service.speech_to_text(audio_bytes, language="vi")
            if recognized_text:
                st.session_state.recorder_key += 1
                st.session_state.pending_query = recognized_text
                st.session_state.chat_history.append({"role": "user", "content": recognized_text})
                st.rerun()

    elif user_text_input:
        st.session_state.pending_query = user_text_input
        st.session_state.chat_history.append({"role": "user", "content": user_text_input})
        st.rerun()

    if st.session_state.pending_query:
        query_to_process = st.session_state.pending_query
        st.session_state.pending_query = None

        with st.spinner("🧠 AI đang xử lý..."):
            response_text = None
            try:
                response = st.session_state.chat_session.send_message(query_to_process)
                response_text = response.text
            except Exception as e:
                if any(code in str(e) for code in ["429", "RESOURCE_EXHAUSTED"]):
                    curr_m = st.session_state.active_model_name
                    rem_models = [m for m in CANDIDATE_MODELS if m != curr_m]
                    for fb_model in rem_models:
                        if init_or_update_chat_session(st.session_state.df_data, target_model=fb_model):
                            try:
                                response = st.session_state.chat_session.send_message(query_to_process)
                                response_text = response.text
                                break
                            except Exception:
                                continue

                if not response_text:
                    response_text = "Thưa Sếp, hệ thống AI tạm thời quá tải, vui lòng thử lại sau."

            audio_path = voice_service.text_to_speech(response_text)
            st.session_state.current_audio_path = audio_path

        st.session_state.chat_history.append({"role": "assistant", "content": response_text})
        st.rerun()