import streamlit as st
import pandas as pd
import io

def clean_excel_table(uploaded_file):
    """Читает Excel-файл, находит строку с заголовками и возвращает очищенный DataFrame."""
    # Читаем полностью без заголовков
    df_all = pd.read_excel(uploaded_file, header=None)

    # Ищем строку, где встречается "Activity Master Number"
    header_row_idx = None
    for i, row in df_all.iterrows():
        if row.astype(str).str.contains("Activity Master Number", case=False, na=False).any():
            header_row_idx = i
            break

    if header_row_idx is None:
        st.error("❌ Не найдена строка с заголовком 'Activity Master Number'")
        st.stop()

    # Загружаем таблицу с правильного заголовка
    df = pd.read_excel(uploaded_file, header=header_row_idx)

    # Удаляем полностью пустые строки
    df = df.dropna(how="all").reset_index(drop=True)

    return df


st.set_page_config(layout="wide", page_title="Column Mapping Tool")

st.title("📊 Сопоставление столбцов старой и новой таблиц")

# =========================
# STEP 1 — FILE UPLOAD
# =========================

col1, col2 = st.columns(2)

with col1:
    old_file = st.file_uploader("Загрузите старый файл (df_raw_v1)", type=["xlsx"])

with col2:
    new_file = st.file_uploader("Загрузите новый файл (df_raw_v2)", type=["xlsx"])

if not old_file or not new_file:
    st.stop()

# =========================
# CLEAN BOTH EXCEL FILES
# =========================

def clean_excel_table(uploaded_file):
    """
    Читает Excel-файл, ищет строку с 'Activity Master Number' и
    возвращает очищенный DataFrame.
    Работает корректно для файлов с мусорными строками сверху
    и для стандартных файлов, где заголовок на первой строке.
    Удаляет полностью пустые строки и столбцы.
    """
    # Читаем без заголовков целиком
    df_all = pd.read_excel(uploaded_file, header=None, dtype=object)

    # === 1. Поиск строки заголовков ===
    header_row_idx = None
    for i, row in df_all.iterrows():
        if row.astype(str).str.contains("Activity Master Number", case=False, na=False).any():
            header_row_idx = i
            break

    # === 2. Если заголовок не найден, останавливаем работу ===
    if header_row_idx is None:
        st.error("❌ Не найдена строка с заголовком 'Activity Master Number'")
        st.stop()

    # === 3. Если заголовок на первой строке — читаем стандартно ===
    if header_row_idx == 0:
        df = pd.read_excel(uploaded_file, dtype=object)
    else:
        # Иначе читаем с найденной строки
        df = pd.read_excel(uploaded_file, header=header_row_idx, dtype=object)

    # === 4. Удаляем полностью пустые строки ===
    df = df.dropna(how="all")

    # === 5. Удаляем полностью пустые столбцы ===
    df = df.dropna(axis=1, how="all")

    # === 6. Сброс индекса ===
    df = df.reset_index(drop=True)

    return df

# Применяем очистку
df_old = clean_excel_table(old_file)
df_new = clean_excel_table(new_file)

old_cols = list(df_old.columns)
new_cols = list(df_new.columns)

st.success("Файлы успешно загружены и автоматически очищены.")

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