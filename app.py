import streamlit as st
import pandas as pd
from streamlit_sortables import sort_items
import io

st.set_page_config(layout="wide", page_title="Column Mapping Tool")


# =========================
# STEP 1 — FILE UPLOAD
# =========================

st.title("📊 Сопоставление столбцов старой и новой таблиц")

col1, col2 = st.columns(2)

with col1:
    old_file = st.file_uploader("Загрузите старый файл (df_raw_v1)", type=["xlsx"])

with col2:
    new_file = st.file_uploader("Загрузите новый файл (df_raw_v2)", type=["xlsx"])

if not old_file or not new_file:
    st.stop()


# =========================
# STEP 2 — LOAD DATA
# =========================

df_old = pd.read_excel(old_file)
df_new = pd.read_excel(new_file)

old_cols = list(df_old.columns)
new_cols = list(df_new.columns)

st.success("Файлы успешно загружены.")

# ====================================================
# STEP 3 — MERGE TABLES (для визуального сравнения)
# ====================================================

st.header("🔎 Объединённая таблица (по Activity Master Number)")

if "Activity Master Number" in df_old.columns and "Activity Master Number" in df_new.columns:
    merged = df_old.merge(df_new, on="Activity Master Number", how="outer", suffixes=("_old", "_new"))
    st.dataframe(merged, use_container_width=True)
else:
    st.error("В обоих файлах должен быть столбец 'Activity Master Number'")
    st.stop()


# ==========================================
# STEP 4 — COLUMN MAPPING (DRAG-AND-DROP)
# ==========================================

st.header("🧩 Сопоставление столбцов")

st.markdown("""
Перетягивайте элементы, чтобы сопоставить столбцы старой и новой таблиц.
- Если столбцы совпадают → это *unchanged*
- Если столбец старый не сопоставлен → *deleted*
- Если столбец новый не сопоставлен → *added*
- Если сопоставили разные имена → *renamed*
""")

col3, col4 = st.columns(2)

with col3:
    st.subheader("Старые столбцы (old)")
    old_sorted = sort_items(old_cols, key="old_cols")

with col4:
    st.subheader("Новые столбцы (new)")
    new_sorted = sort_items(new_cols, key="new_cols")

# результат сопоставления: позиции в списках
mapping = list(zip(old_sorted, new_sorted))


# =======================================
# STEP 5 — DETECT COLUMN CHANGES
# =======================================

result = []

max_len = max(len(old_sorted), len(new_sorted))

for i in range(max_len):
    old_name = old_sorted[i] if i < len(old_sorted) else None
    new_name = new_sorted[i] if i < len(new_sorted) else None

    if old_name == new_name:
        status = "unchanged"
    elif old_name and not new_name:
        status = "deleted"
    elif new_name and not old_name:
        status = "added"
    else:
        status = "renamed"

    result.append({
        "old_column": old_name,
        "new_column": new_name,
        "status": status
    })

df_log = pd.DataFrame(result)


st.subheader("📘 Результат сопоставления")
st.dataframe(df_log, use_container_width=True)



# =======================================
# STEP 6 — DOWNLOAD LOG AS EXCEL
# =======================================

st.header("⬇ Выгрузка результата")

def excel_download(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="column_mapping", index=False)
    buffer.seek(0)
    return buffer

st.download_button(
    "Скачать Excel",
    data=excel_download(df_log),
    file_name="column_mapping.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)