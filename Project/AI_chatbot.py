import os
from google import genai
from google.genai import types

# ---------------------------------------------------------
# 1. Điền API Key của bạn tại đây
# ---------------------------------------------------------

# ---------------------------------------------------------
# 2. Định nghĩa các hàm API thực tế (Mock API)
# ---------------------------------------------------------
def get_order_status(order_id: str) -> dict:
    """Lấy thông tin trạng thái của một đơn hàng dựa vào mã đơn hàng (order_id)."""
    mock_orders = {
        "DH123": {"status": "Đang giao hàng", "carrier": "Giao Hàng Nhanh", "estimated_delivery": "Hôm nay"},
        "DH456": {"status": "Đã hủy", "reason": "Người dùng yêu cầu hủy"},
        "DH789": {"status": "Giao thành công", "date": "01/08/2026"}
    }
    
    if order_id in mock_orders:
        return {"success": True, "data": mock_orders[order_id]}
    return {"success": False, "message": f"Không tìm thấy đơn hàng {order_id}"}

def get_gold_price(type: str = "SJC") -> dict:
    """Lấy giá vàng hôm nay theo loại vàng."""
    return {
        "type": type,
        "buy_price": "88,000,000 VND/lượng",
        "sell_price": "90,000,000 VND/lượng",
        "updated_at": "Hôm nay"
    }

# Map tên hàm với function thực tế trong Python
tools_map = {
    "get_order_status": get_order_status,
    "get_gold_price": get_gold_price
}

# ---------------------------------------------------------
# 3. Khởi tạo Client & Chatbot
# ---------------------------------------------------------
client = genai.Client(api_key="AQ.Ab8RN6LDJidy7tfwl5wiX8Zdvgdgh0uINloLsYo8tz5sKczh3g")

# Sử dụng gemini-2.5-flash (Model có sẵn trong danh sách của bạn)
chat = client.chats.create(
    model="gemini-3.5-flash",
    config=types.GenerateContentConfig(
        system_instruction="Bạn là chuyên gia phan tich dữ liệu và API. Hãy trả lời ngắn gọn, súc tích, và nếu cần, hãy gọi các hàm API đã được định nghĩa sẵn.",
        tools=[get_order_status, get_gold_price]
    )
)
# ---------------------------------------------------------
# 4. Vòng lặp Chatbot xử lý Function Calling
# ---------------------------------------------------------
print("=== DEMO CHATBOT TÍCH HỢP API (Nhập 'exit' để thoát) ===")

while True:
    user_input = input("\nBạn: ")
    if user_input.lower() in ["exit", "quit"]:
        break

    # Gửi tin nhắn đến Gemini
    response = chat.send_message(user_input)

    # Kiểm tra xem Gemini có yêu cầu gọi API/Hàm không
    if response.function_calls:
        for call in response.function_calls:
            function_name = call.name
            function_args = call.args
            
            print(f"🤖 [System] Gemini đang gọi API: {function_name} với tham số {function_args}")
            
            # Thực thi hàm tương ứng trong Python
            if function_name in tools_map:
                api_result = tools_map[function_name](**function_args)
                
                # Trả kết quả API ngược lại cho Gemini để nó tổng hợp câu trả lời
                response = chat.send_message(
                    types.Part.from_function_response(
                        name=function_name,
                        response={"result": api_result}
                    )
                )

    # In ra câu trả lời cuối cùng cho người dùng
    print(f"Bot: {response.text}")