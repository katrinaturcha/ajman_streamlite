import streamlit as st
import pandas as pd
import numpy as np
import io
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

st.set_page_config(layout="wide", page_title="AJMAN – Compare & Merge")


# ============================================================
# ФУНКЦИЯ ОЧИСТКИ ФАЙЛА (оставляем строго твою логику)
# ============================================================
def clean_excel_table(uploaded_file):
    """
    Читает Excel-файл, ищет строку с 'Activity Master Number' и
    возвращает очищенный DataFrame.
    Работает и для грязных файлов, и для стандартных.
    """
    df_all = pd.read_excel(uploaded_file, header=None, dtype=object)

    header_row_idx = None
    for i, row in df_all.iterrows():
        if row.astype(str).str.contains("Activity Master Number", case=False, na=False).any():
            header_row_idx = i
            break

    if header_row_idx is None:
        st.error("❌ Не найдена строка с заголовком 'Activity Master Number'")
        st.stop()

    if header_row_idx == 0:
        df = pd.read_excel(uploaded_file, dtype=object)
    else:
        df = pd.read_excel(uploaded_file, header=header_row_idx, dtype=object)

    df = df.dropna(how="all")            # удалить пустые строки
    df = df.dropna(axis=1, how="all")    # удалить пустые столбцы
    df = df.reset_index(drop=True)

    return df


# ============================================================
# UI: ЗАГРУЗКА ФАЙЛОВ
# ============================================================

st.title("📊 AJMAN — Сравнение, сопоставление и объединение таблиц")

col1, col2 = st.columns(2)

with col1:
    old_file = st.file_uploader("Загрузите старый файл (df_raw_v1)", type=["xlsx"])

with col2:
    new_file = st.file_uploader("Загрузите новый файл (df_raw_v2)", type=["xlsx"])

if not old_file or not new_file:
    st.stop()

st.success("Файлы загружены! Идёт обработка...")


# ============================================================
# ЧИСТИМ ОБА ФАЙЛА
# ============================================================

df_old = clean_excel_table(old_file)
df_new = clean_excel_table(new_file)

old_cols = list(df_old.columns)
new_cols = list(df_new.columns)

st.write("### 🧼 Очищенные таблицы загружены:")
st.write(f"Старая таблица: {df_old.shape[0]} строк, {df_old.shape[1]} колонок")
st.write(f"Новая таблица: {df_new.shape[0]} строк, {df_new.shape[1]} колонок")


# ============================================================
# СОПОСТАВЛЕНИЕ КОЛОНОК
# ============================================================

st.header("🧩 Сопоставление столбцов")

st.markdown("Выберите, каким столбцам из НОВОГО файла соответствуют столбцы из СТАРОГО файла.")

mapping = {}

for col in old_cols:
    choice = st.selectbox(
        f"Старый столбец: **{col}**",
        options=["— Нет соответствия —"] + new_cols,
        key=f"map_{col}"
    )
    mapping[col] = choice if choice != "— Нет соответствия —" else None

st.success("Сопоставление колонок завершено!")

# ============================================================
# LOGGING COLUMN CHANGES (renamed / added / deleted)
# ============================================================

st.header("📘 Логирование изменений столбцов")

log_rows = []
current_date = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
provider_name = "ajman"            # можно подставить переменную
last_version = old_file.name        # или любую версию, которую хочешь логировать

# 1. renamed + deleted (разбираем старые)
used_new_cols = set()

for old_col, new_col in mapping.items():
    if new_col is None:
        # deleted
        log_rows.append({
            "date": current_date,
            "provider": provider_name,
            "last_version": last_version,
            "event": "deleted",
            "old_column": old_col,
            "new_column": None
        })
    else:
        used_new_cols.add(new_col)

        if new_col == old_col:
            # unchanged — обычно не логируем
            continue
        else:
            # renamed
            log_rows.append({
                "date": current_date,
                "provider": provider_name,
                "last_version": last_version,
                "event": "renamed",
                "old_column": old_col,
                "new_column": new_col
            })

# 2. added (новые колонки, которые никто не сопоставил)
for col in new_cols:
    if col not in used_new_cols and col not in old_cols:
        log_rows.append({
            "date": current_date,
            "provider": provider_name,
            "last_version": last_version,
            "event": "added",
            "old_column": None,
            "new_column": col
        })

# преобразуем в таблицу
df_log_columns = pd.DataFrame(log_rows)

st.subheader("📄 Лог изменений столбцов")
st.dataframe(df_log_columns, use_container_width=True)


# ===== Кнопка СКАЧАТЬ ЛОГ =====

def download_log(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="log_schema")
    buffer.seek(0)
    return buffer

st.download_button(
    label="⬇ Скачать лог изменений столбцов",
    data=download_log(df_log_columns),
    file_name="log_schema.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# ============================================================
# ПРИМЕНИТЬ ПЕРЕИМЕНОВАНИЕ К СТАРОЙ ТАБЛИЦЕ
# ============================================================

df_old_renamed = df_old.copy()

for old_col, new_col in mapping.items():
    if new_col is not None:
        df_old_renamed.rename(columns={old_col: new_col}, inplace=True)


# Добавить префиксы для наглядности
df_old_pref = df_old_renamed.add_prefix("old_")
df_new_pref = df_new.add_prefix("new_")


# ============================================================
# ОБЪЕДИНЕНИЕ ОБЕИХ ТАБЛИЦ
# ============================================================

st.header("🔗 Объединение строк по Activity Master Number")

merged_df = df_old_pref.merge(
    df_new_pref,
    left_on="old_Activity Master Number",
    right_on="new_Activity Master Number",
    how="outer",
    indicator=True
)


# ============================================================
# ЛОГИКА ОПРЕДЕЛЕНИЯ СТАТУСА СТРОКИ
# ============================================================

def row_status(row):
    if row["_merge"] == "left_only":
        return "deleted"
    if row["_merge"] == "right_only":
        return "new"

    # общие колонки
    common_cols = [
        c.replace("old_", "")
        for c in df_old_pref.columns
        if c.replace("old_", "") in [x.replace("new_", "") for x in df_new_pref.columns]
    ]

    for col in common_cols:
        old_val = row.get(f"old_{col}", np.nan)
        new_val = row.get(f"new_{col}", np.nan)
        if str(old_val).strip() != str(new_val).strip():
            return "changed"

    return "not_changed"


merged_df["status"] = merged_df.apply(row_status, axis=1)

status_col = merged_df.pop("status")
merge_col = merged_df.pop("_merge")
merged_df.insert(0, "status", status_col)
merged_df.insert(1, "_merge", merge_col)

st.success("Анализ изменений выполнен!")


# ============================================================
# ФИЛЬТР ПО СТАТУСУ
# ============================================================

st.header("🔎 Фильтр по статусу")

status_filter = st.selectbox(
    "Выберите статус",
    ["all", "changed", "not_changed", "new", "deleted"]
)

if status_filter == "all":
    filtered_df = merged_df
else:
    filtered_df = merged_df[merged_df["status"] == status_filter]


# ============================================================
# РЕДАКТИРУЕМАЯ ТАБЛИЦА
# ============================================================

st.header("📋 Таблица изменений (редактируемая)")

gb = GridOptionsBuilder.from_dataframe(filtered_df)
gb.configure_default_column(editable=True, wrapText=True, width=180)
gb.configure_side_bar()
grid_options = gb.build()

grid_response = AgGrid(
    filtered_df,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.VALUE_CHANGED,
    fit_columns_on_grid_load=False,
    height=600
)

edited_df = pd.DataFrame(grid_response["data"])


# ============================================================
# СКАЧАТЬ В EXCEL
# ============================================================

st.header("⬇ Выгрузка результата")

def download_excel(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="merged")
    buffer.seek(0)
    return buffer

st.download_button(
    label="Скачать объединённую таблицу",
    data=download_excel(edited_df),
    file_name="merged_status.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)