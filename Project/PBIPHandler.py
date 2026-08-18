import os
import json
import tempfile
import zipfile
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

class PBIPHandler:
    """
    Class xử lý PBIP tổng quát 100%:
    - Đọc vị trí (x, y, width, height) và loại visual của MỌI file .pbip
    - Tự động nhận diện cột dữ liệu thực tế từ DataFrame mà KHÔNG hardcode tên cột
    - Ánh xạ đúng tỉ lệ Grid và biểu đồ cho bất kỳ loại báo cáo nào (Bán hàng, Nhân sự, Tài chính...)
    """
    def __init__(self, pbip_folder_path: str = None, uploaded_zip_file=None):
        self.pbip_folder_path = pbip_folder_path
        self.pages = []
        self.temp_dir = None

        if uploaded_zip_file is not None:
            self.extract_and_parse_zip(uploaded_zip_file)
        elif pbip_folder_path and os.path.exists(pbip_folder_path):
            self.parse_pbip_structure(pbip_folder_path)

    def extract_and_parse_zip(self, uploaded_zip_file):
        try:
            self.temp_dir = tempfile.TemporaryDirectory()
            zip_path = os.path.join(self.temp_dir.name, "uploaded_pbip.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_zip_file.getbuffer())
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir.name)
            self.parse_pbip_structure(self.temp_dir.name)
        except Exception as e:
            st.error(f"Lỗi giải nén ZIP PBIP: {e}")

    def extract_visual_metadata(self, vis_data: dict) -> dict:
        """
        Trích xuất Tiêu đề (Title) và các Cột Dữ liệu (Data Fields) thực tế từ PBIP JSON
        """
        visual_obj = vis_data.get("visual", vis_data)
        
        title = None
        data_fields = []

        # 1. Trích xuất Custom Title (Nếu người dùng đặt lại tiêu đề trên Power BI)
        try:
            objects = visual_obj.get("objects", {})
            title_obj = objects.get("title", [])
            if title_obj and isinstance(title_obj, list):
                props = title_obj[0].get("properties", {})
                text_expr = props.get("text", {}).get("expr", {})
                if "Literal" in text_expr:
                    title = text_expr["Literal"].get("Value", "").strip("'\"")
        except Exception:
            pass

        # 2. Trích xuất tên các cột dữ liệu được kéo vào visual (Projections/Select)
        try:
            query = visual_obj.get("query", {})
            select_list = query.get("select", [])
            for item in select_list:
                if "Property" in item:
                    data_fields.append(item["Property"])
                elif "Name" in item:
                    field_name = item["Name"].split(".")[-1]
                    data_fields.append(field_name)
        except Exception:
            pass

        # Fallback: Trích xuất từ visualData (PBIP phiên bản khác)
        if not data_fields:
            try:
                query_state = visual_obj.get("queryData", {}).get("queryState", {})
                for role, data in query_state.items():
                    projections = data.get("projections", [])
                    for proj in projections:
                        if "field" in proj:
                            prop = proj["field"].get("Column", {}).get("Property")
                            if prop:
                                data_fields.append(prop)
            except Exception:
                pass

        return {
            "title": title,
            "fields": data_fields
        }

    def parse_pbip_structure(self, root_dir: str):
        try:
            report_folder = None
            for root, dirs, _ in os.walk(root_dir):
                for d in dirs:
                    if d.endswith('.Report'):
                        report_folder = os.path.join(root, d)
                        break
                if report_folder:
                    break

            if not report_folder:
                return

            pages_folder = os.path.join(report_folder, "definition", "pages")
            if not os.path.exists(pages_folder):
                return

            self.pages = []

            for page_folder in sorted(os.listdir(pages_folder)):
                page_path = os.path.join(pages_folder, page_folder)
                page_json_path = os.path.join(page_path, "page.json")
                if not os.path.exists(page_json_path):
                    continue

                with open(page_json_path, 'r', encoding='utf-8') as f:
                    page_data = json.load(f)

                page_name = page_data.get("displayName", page_folder)
                visuals_list = []

                visuals_dir = os.path.join(page_path, "visuals")
                if os.path.exists(visuals_dir):
                    for vis_folder in os.listdir(visuals_dir):
                        vis_json_path = os.path.join(visuals_dir, vis_folder, "visual.json")
                        if os.path.exists(vis_json_path):
                            with open(vis_json_path, 'r', encoding='utf-8') as vf:
                                vis_data = json.load(vf)
                                vis_type = vis_data.get("visual", {}).get("visualType", "unknown") if "visual" in vis_data else vis_data.get("visualType", "unknown")
                                pos = vis_data.get("position", {"x": 0, "y": 0, "width": 100, "height": 100})
                                
                                # Trích xuất Title và Fields chuẩn từ JSON
                                meta = self.extract_visual_metadata(vis_data)

                                if vis_type.lower() not in ["image", "shape", "textbox", "slicer"]:
                                    visuals_list.append({
                                        "id": vis_folder,
                                        "type": vis_type,
                                        "position": pos,
                                        "title": meta["title"],      # Title đọc từ PBIP
                                        "fields": meta["fields"],    # Cột đọc từ PBIP
                                        "raw_data": vis_data
                                    })

                visuals_list.sort(key=lambda v: (v["position"]["y"], v["position"]["x"]))

                self.pages.append({
                    "name": page_name,
                    "visuals": visuals_list
                })

        except Exception as e:
            st.error(f"Lỗi đọc PBIP: {e}")

    def render_single_visual(self, vis_info: dict, df: pd.DataFrame, vis_index: int = 0):
        vis_type = vis_info["type"].lower()
        num_cols, cat_cols, date_cols = self._detect_column_types(df)

        # Đội ưu tiên: Dùng cột được khai báo trong PBIP trước, nếu không có mới tự suy luận
        pbip_fields = vis_info.get("fields", [])
        matched_num_cols = [f for f in pbip_fields if f in num_cols]
        matched_cat_cols = [f for f in pbip_fields if f in cat_cols or f in date_cols]

        # Xác định Cột Số chính và Cột Phân loại chính
        val_col = matched_num_cols[0] if matched_num_cols else (num_cols[vis_index % len(num_cols)] if num_cols else df.columns[0])
        group_col = matched_cat_cols[0] if matched_cat_cols else (date_cols[0] if date_cols else (cat_cols[0] if cat_cols else df.columns[0]))

        # Xác định Title hiển thị
        display_title = vis_info.get("title")
        if not display_title:
            display_title = f"{val_col} theo {group_col}" if vis_type not in ["card", "gauge"] else f"{val_col}"

        # 1. Thẻ KPI (Card)
        if "card" in vis_type:
            val = df[val_col].sum() if val_col in df.columns else len(df)
            formatted_val = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}"
            lbl = vis_info.get("title") or f"Tổng {val_col}"

            st.markdown(f"""
                <div style="background-color: #EBF3E8; border-radius: 10px; padding: 12px; text-align: center; border: 1px solid #D1E2C4;">
                    <div style="font-size: 22px; font-weight: bold; color: #1E1E1E;">{formatted_val}</div>
                    <div style="font-size: 12px; color: #555555; margin-top: 4px;">{lbl}</div>
                </div>
            """, unsafe_allow_html=True)

        # 2. Đồng hồ (Gauge)
        elif "gauge" in vis_type:
            val = df[val_col].sum() if val_col in df.columns else len(df)
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=val,
                title={'text': display_title, 'font': {'size': 13}}
            ))
            fig.update_layout(height=220, margin=dict(l=15, r=15, t=30, b=15))
            st.plotly_chart(fig, use_container_width=True)

        # 3. Biểu đồ Đường (Line Chart)
        elif any(k in vis_type for k in ["line", "area"]):
            grouped_df = df.groupby(group_col)[val_col].sum().reset_index()
            fig = px.line(grouped_df, x=group_col, y=val_col, title=display_title)
            fig.update_layout(height=240, margin=dict(l=10, r=10, t=35, b=10))
            st.plotly_chart(fig, use_container_width=True)

        # 4. Biểu đồ Cột (Bar / Column)
        elif any(k in vis_type for k in ["bar", "column"]):
            grouped_df = df.groupby(group_col)[val_col].sum().reset_index().head(10)
            fig = px.bar(grouped_df, x=group_col, y=val_col, title=display_title)
            fig.update_layout(height=240, margin=dict(l=10, r=10, t=35, b=10))
            st.plotly_chart(fig, use_container_width=True)

        # 5. Mặc định
        else:
            fig = px.bar(df.head(10), x=group_col, y=val_col, title=display_title)
            fig.update_layout(height=240, margin=dict(l=10, r=10, t=35, b=10))
            st.plotly_chart(fig, use_container_width=True)

    # --- TỰ ĐỘNG PHÂN LOẠI CỘT TỔNG QUÁT THEO KIỂU DỮ LIỆU ---
    def _detect_column_types(self, df: pd.DataFrame):
        num_cols = df.select_dtypes(include=['number']).columns.tolist()
        cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        
        # Tự động tìm cột thời gian bất kỳ
        date_cols = []
        for c in df.columns:
            if df[c].dtype == 'datetime64[ns]' or any(k in str(c).lower() for k in ['date', 'time', 'year', 'month', 'day', 'ngay', 'thang', 'nam']):
                date_cols.append(c)

        return num_cols, cat_cols, date_cols

    # --- TỰ ĐỘNG DỰNG BỐ CỤC THEO ĐÚNG TỶ LỆ CỦA TỪNG BÁO CÁO ---
    def render_dashboard(self, df: pd.DataFrame):
        if df is None or df.empty:
            st.info("💡 Chưa có dữ liệu. Vui lòng tải file Excel/CSV ở thanh bên!")
            return

        if "selected_page" not in st.session_state:
            st.session_state.selected_page = self.pages[0]["name"] if self.pages else "Overview"

        current_page = next((p for p in self.pages if p["name"] == st.session_state.selected_page), None)

        st.caption(f"📌 Đang xem trang: **{st.session_state.selected_page}**")
        st.write("")

        if current_page and current_page["visuals"]:
            visuals = current_page["visuals"]
            
            # Nhóm các visual theo Hàng ngang dựa trên tọa độ Y
            rows = []
            curr_row = []
            last_y = None

            for v in visuals:
                y = v["position"]["y"]
                if last_y is None or abs(y - last_y) < 80:
                    curr_row.append(v)
                else:
                    rows.append(curr_row)
                    curr_row = [v]
                last_y = y
            if curr_row:
                rows.append(curr_row)

            card_idx = 0
            for row in rows:
                # Sử dụng trực tiếp tỉ lệ chiều rộng (Width) từ file PBIP gốc
                widths = [max(v["position"]["width"], 10) for v in row]
                cols = st.columns(widths)
                
                for idx, vis_info in enumerate(row):
                    with cols[idx]:
                        if "card" in vis_info["type"].lower():
                            self.render_single_visual(vis_info, df, vis_index=card_idx)
                            card_idx += 1
                        else:
                            self.render_single_visual(vis_info, df, vis_index=idx)
        else:
            st.warning("Không tìm thấy cấu trúc visual thích hợp trong PBIP.")

        # Page Navigator linh hoạt
        st.markdown("---")
        page_names = [p["name"] for p in self.pages] if self.pages else ["Overview"]
        nav_cols = st.columns(max(len(page_names), 1))
        for idx, p_name in enumerate(page_names):
            with nav_cols[idx]:
                is_active = (st.session_state.selected_page == p_name)
                btn_type = "primary" if is_active else "secondary"
                if st.button(p_name, key=f"nav_btn_{idx}", type=btn_type, use_container_width=True):
                    st.session_state.selected_page = p_name
                    st.rerun()