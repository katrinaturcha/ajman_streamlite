import streamlit as st
import pandas as pd
import io

st.set_page_config(layout="wide", page_title="Column Mapping Tool")

st.title("📊 Сопоставление столбцов старой и новой таблиц")

# =====================================
# STEP 1 — Загрузка старого и нового файла
# =====================================

col1, col2 = st.columns(2)

with col1:
    old_file = st.file_uploader("Загрузите старый файл (df_raw_v1)", type=["xlsx"])

with col2:
    new_file = st.file_uploader("Загрузите новый файл (df_raw_v2)", type=["xlsx"])

if not old_file or not new_file:
    st.stop()

df_old = pd.read_excel(old_file)
df_new = pd.read_excel(new_file)

old_cols = list(df_old.columns)
new_cols = list(df_new.columns)

st.success("Файлы успешно загружены.")

# =====================================
# STEP 2 — Объединённая таблица (чисто визуально)
# =====================================

st.header("🔎 Объединённая таблица по Activity Master Number")

if "Activity Master Number" in df_old.columns and "Activity Master Number" in df_new.columns:
    merged = df_old.merge(df_new, on="Activity Master Number", how="outer", suffixes=("_old", "_new"))
    st.dataframe(merged, use_container_width=True)
else:
    st.error("Оба файла должны содержать столбец 'Activity Master Number'")
    st.stop()

# =====================================
# STEP 3 — Форма сопоставления столбцов
# =====================================

st.header("🧩 Сопоставление столбцов")

st.markdown("""
Выберите, какой столбец из НОВОГО файла соответствует каждому столбцу из СТАРОГО файла.

- Если не выбирать — столбец считается **удалённым**.
- Если столбец из нового файла никто не выбрал — он считается **добавленным**.
- Если выбрать столбец с таким же названием — **не изменён**.
- Если выбрать другое название — **переименован**.
""")

mapping = {}

for col in old_cols:
    choice = st.selectbox(
        f"Старый столбец: **{col}**",
        options=["— Нет соответствия —"] + new_cols,
        key=f"map_{col}"
    )
    mapping[col] = choice if choice != "— Нет соответствия —" else None

# =====================================
# STEP 4 — Анализ изменений
# =====================================

st.header("📘 Результат сопоставления")

used_new_cols = set([v for v in mapping.values() if v is not None])

rows = []

# Проверяем старые столбцы
for old in old_cols:
    new = mapping[old]
    if new is None:
        status = "deleted"
    elif new == old:
        status = "unchanged"
    else:
        status = "renamed"
    rows.append({"old_column": old, "new_column": new, "status": status})

# Проверяем добавленные новые столбцы
for new in new_cols:
    if new not in used_new_cols and new not in old_cols:
        rows.append({"old_column": None, "new_column": new, "status": "added"})

df_log = pd.DataFrame(rows)

st.dataframe(df_log, use_container_width=True)

# =====================================
# STEP 5 — Скачивание результата
# =====================================

st.header("⬇ Скачать лог изменений")

def create_excel(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="column_mapping", index=False)
    buffer.seek(0)
    return buffer

st.download_button(
    label="Скачать Excel",
    data=create_excel(df_log),
    file_name="column_mapping.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)