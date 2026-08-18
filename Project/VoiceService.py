import asyncio
import io
import os
import re
import tempfile
import edge_tts
from pydub import AudioSegment

# 1. Chuyển vị trí lưu Cache Model từ ổ C sang ổ D
os.environ["HF_HOME"] = r"D:\whisper_cache"

# 2. Tắt cảnh báo Symlink trên Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from faster_whisper import WhisperModel


class VoiceService:

    def __init__(self, model_size: str = "base"):
        """Khởi tạo Faster-Whisper và các cấu hình giọng đọc TTS."""
        self.whisper_model = WhisperModel(
            model_size, device="cpu", compute_type="int8"
        )
        
        # Cấu hình giọng đọc đa ngôn ngữ cho Edge-TTS
        self.voice_vi = "vi-VN-HoaiMyNeural"
        self.voice_en = "en-US-SteffanNeural"

    def speech_to_text(self, audio_bytes: bytes, language: str = "vi") -> str:
        """Chuyển giọng nói tiếng Việt thành văn bản (Tối ưu cho tốc độ nói nhanh)."""
        if not audio_bytes:
            return ""

        audio_stream = io.BytesIO(audio_bytes)

        # Gợi ý ngữ cảnh quen thuộc
        initial_prompt = (
            "Báo cáo, doanh thu, lợi nhuận, chi phí, số liệu, sản phẩm, "
            "khách hàng, biểu đồ, dữ liệu, phân tích, tổng số dòng, tăng trưởng."
        )

        try:
            segments, _ = self.whisper_model.transcribe(
                audio_stream,
                language=language,
                initial_prompt=initial_prompt,
                
                # --- CÁC THÔNG SỐ ĐƯỢC TỐI ƯU CHO NÓI NHANH ---
                temperature=0.2,            # Tăng nhẹ độ linh hoạt để bắt kịp các từ nối/nói lướt
                beam_size=5,                # Tìm kiếm đa hướng để không bỏ sót từ
                vad_filter=True,            # Bật lọc tạp âm
                vad_parameters=dict(
                    threshold=0.3,          # Hạ ngưỡng phát hiện giọng nói
                    min_silence_duration_ms=200, # Không bị cắt xén khi ngắt nghỉ ngắn
                    speech_pad_ms=300       # Giữ lại dải âm thanh đầu/cuối
                ),
            )

            user_text = "".join([segment.text for segment in segments]).strip()
            return user_text

        except Exception as e:
            print(f"Lỗi STT (Faster-Whisper): {e}")
            return ""

    def parse_tagged_text(self, text: str):
        """
        Tách văn bản dựa trên ký hiệu * do Gemini đánh dấu.
        """
        parts = re.split(r'\*(.*?)\*', text)
        chunks = []

        for idx, part in enumerate(parts):
            clean_part = part.strip()
            if not clean_part:
                continue
            lang = "en" if idx % 2 == 1 else "vi"
            chunks.append((clean_part, lang))

        return chunks

    @staticmethod
    async def _async_generate_tts(
        text: str,
        output_path: str,
        voice: str = "vi-VN-HoaiMyNeural",
        rate: str = "+30%",
    ):
        """Hàm bất đồng bộ gọi edge-tts để ghi file âm thanh."""
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(output_path)

    def text_to_speech(
        self,
        text: str,
        rate: str = "+30%",
    ) -> str:
        """
        Chuyển văn bản đa ngôn ngữ thành file MP3 tạm thời bằng cách ghép các segment audio.
        """
        chunks = self.parse_tagged_text(text)
        if not chunks:
            return ""

        temp_files = []
        combined_audio = AudioSegment.empty()

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            for idx, (chunk_text, lang) in enumerate(chunks):
                selected_voice = self.voice_en if lang == "en" else self.voice_vi
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_chunk:
                    chunk_audio_path = tmp_chunk.name
                    temp_files.append(chunk_audio_path)

                loop.run_until_complete(
                    self._async_generate_tts(
                        chunk_text, chunk_audio_path, voice=selected_voice, rate=rate
                    )
                )

                if os.path.exists(chunk_audio_path) and os.path.getsize(chunk_audio_path) > 0:
                    segment = AudioSegment.from_file(chunk_audio_path)
                    combined_audio += segment

            loop.close()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_out:
                output_audio_path = tmp_out.name

            combined_audio.export(output_audio_path, format="mp3")

        except Exception as e:
            print(f"Lỗi TTS (Edge-TTS Multilingual): {e}")
            output_audio_path = ""

        finally:
            for f in temp_files:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

        return output_audio_path
