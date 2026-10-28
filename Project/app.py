import os
import streamlit as st
from audio_recorder_streamlit import audio_recorder
from VoiceService import VoiceService
from google import genai

# -----------------------------------------------------------------------------
# 1. CẤU HÌNH TRANG & SERVICES
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Voice Chatbot",
    layout="centered",
)

# Khởi tạo dịch vụ thoại & Gemini AI
voice_service = VoiceService()
# Thay YOUR_GEMINI_API_KEY bằng API key thực tế của bạn
client = genai.Client(api_key="AQ.Ab8RN6LbuWqUDOjG2fO30e6RCByfQlF00jpSJe3Rq3ckdTjd8Q")
# Khởi tạo lịch sử trò chuyện trong Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

# -----------------------------------------------------------------------------
# 2. GIAO DIỆN CHATBOT (HEADER & CONTROL)
# -----------------------------------------------------------------------------
st.title("🤖 AI Voice Chatbot")

# Nút xóa lịch sử trò chuyện
if st.button("🗑️ Xóa lịch sử Chat"):
    st.session_state.messages = []
    st.rerun()

# -----------------------------------------------------------------------------
# 3. HIỂN THỊ LỊCH SỬ TIN NHẮN & PHÁT ÂM THANH (TTS)
# -----------------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        # Nếu có file âm thanh TTS kèm theo thì hiển thị trình phát
        if "audio" in msg and msg["audio"]:
            st.audio(msg["audio"], format="audio/mp3")

# -----------------------------------------------------------------------------
# 4. CÔNG CỤ NHẬP LIỆU: VOICETOTEXT (STT) & CHAT INPUT
# -----------------------------------------------------------------------------
st.write("---")
st.subheader("🎙️ Trợ lý Phân tích AI")

# --- STT: Thu âm bằng giọng nói ---
audio_bytes = audio_recorder(text="Bấm mic để nói", icon_name="microphone", icon_size="2x")

user_prompt = None

if audio_bytes:
    with st.spinner("Đang chuyển giọng nói thành văn bản..."):
        user_prompt = voice_service.stt(audio_bytes)
        if user_prompt:
            st.info(f"🗣️ Bạn vừa nói: {user_prompt}")

# --- Nhập văn bản trực tiếp (nếu không dùng giọng nói) ---
text_input = st.chat_input("Hoặc gõ câu hỏi...")
if text_input:
    user_prompt = text_input

# -----------------------------------------------------------------------------
# 5. XỬ LÝ PHẢN HỒI AI & TẠO ÂM THANH (TTS)
# -----------------------------------------------------------------------------
if user_prompt:
    # 1. Ghi nhận tin nhắn người dùng
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.write(user_prompt)

    # 2. Gửi cho Gemini AI xử lý
    with st.chat_message("assistant"):
        with st.spinner("AI đang suy nghĩ..."):
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite-001",
                contents=user_prompt
            )
            ai_reply = response.text
            st.write(ai_reply)

            # 3. TTS: Chuyển câu trả lời của AI thành giọng nói
            audio_path = voice_service.tts(ai_reply)
            
            # Lưu tin nhắn AI và file âm thanh vào lịch sử
            st.session_state.messages.append({
                "role": "assistant", 
                "content": ai_reply, 
                "audio": audio_path
            })
            
            # Phát âm thanh phản hồi lập tức
            if audio_path:
                st.audio(audio_path, format="audio/mp3")
