import streamlit as st
import pandas as pd
import numpy as np
import io
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

st.set_page_config(layout="wide", page_title="AJMAN – Compare & Merge")


# ============================================================
# ФУНКЦИЯ ОЧИСТКИ ФАЙЛА
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

    df = df.dropna(how="all")          # удалить пустые строки
    df = df.dropna(axis=1, how="all")  # удалить пустые столбцы
    df = df.reset_index(drop=True)

    return df


# ============================================================
# ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ
# ============================================================
if "log_actions" not in st.session_state:
    st.session_state["log_actions"] = []

if "merged_df" not in st.session_state:
    st.session_state["merged_df"] = None


# ============================================================
# UI: ЗАГРУЗКА ФАЙЛОВ
# ============================================================
st.title("📊 AJMAN — Сравнение, сопоставление и объединение таблиц")

manager_id = st.text_input("Manager ID (для логов)", value="system")

col1, col2 = st.columns(2)
with col1:
    old_file = st.file_uploader("Загрузите старый файл (df_raw_v1)", type=["xlsx"])
with col2:
    new_file = st.file_uploader("Загрузите новый файл (df_raw_v2)", type=["xlsx"])

if not old_file or not new_file:
    st.stop()

provider_name = "ajman"
last_version = old_file.name

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
        key=f"map_{col}",
    )
    mapping[col] = choice if choice != "— Нет соответствия —" else None

st.success("Сопоставление колонок завершено!")


# ============================================================
# LOG_SCHEMA: renamed / added / deleted
# ============================================================
st.header("📘 Логирование изменений столбцов")

log_rows = []
current_date = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
used_new_cols = set()

for old_col, new_col in mapping.items():
    if new_col is None:
        log_rows.append({
            "date": current_date,
            "provider": provider_name,
            "last_version": last_version,
            "event": "deleted",
            "old_column": old_col,
            "new_column": None,
        })
    else:
        used_new_cols.add(new_col)
        if new_col == old_col:
            continue
        log_rows.append({
            "date": current_date,
            "provider": provider_name,
            "last_version": last_version,
            "event": "renamed",
            "old_column": old_col,
            "new_column": new_col,
        })

for col in new_cols:
    if col not in used_new_cols and col not in old_cols:
        log_rows.append({
            "date": current_date,
            "provider": provider_name,
            "last_version": last_version,
            "event": "added",
            "old_column": None,
            "new_column": col,
        })

df_log_columns = pd.DataFrame(log_rows)
st.subheader("📄 Лог изменений столбцов")
st.dataframe(df_log_columns, use_container_width=True)


def download_log(df: pd.DataFrame):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="log_schema")
    buffer.seek(0)
    return buffer


st.download_button(
    label="⬇ Скачать лог изменений столбцов",
    data=download_log(df_log_columns),
    file_name="log_schema.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


# ============================================================
# ПРИМЕНИТЬ ПЕРЕИМЕНОВАНИЕ К СТАРОЙ ТАБЛИЦЕ
# ============================================================
df_old_renamed = df_old.copy()
for old_col, new_col in mapping.items():
    if new_col is not None:
        df_old_renamed.rename(columns={old_col: new_col}, inplace=True)

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
    indicator=True,
)


# ============================================================
# СТАТУС + КОЛОНКА "измененные столбцы"
# ============================================================
def compare_row_changes(row, common_cols):
    """
    Возвращает:
    - статус строки
    - строку 'измененные столбцы' (через запятую) или None
    """
    if row["_merge"] == "left_only":
        return "deleted", None
    if row["_merge"] == "right_only":
        return "new", None

    changed_cols = []
    for col in common_cols:
        old_val = row.get(f"old_{col}", np.nan)
        new_val = row.get(f"new_{col}", np.nan)
        if str(old_val).strip() != str(new_val).strip():
            changed_cols.append(col)

    if changed_cols:
        return "changed", ", ".join(changed_cols)
    return "not_changed", None


common_cols = [
    c.replace("old_", "")
    for c in df_old_pref.columns
    if c.replace("old_", "") in [x.replace("new_", "") for x in df_new_pref.columns]
]

statuses = []
changed_cols_list = []
for _, r in merged_df.iterrows():
    s, cols = compare_row_changes(r, common_cols)
    statuses.append(s)
    changed_cols_list.append(cols)

merged_df["status"] = statuses
merged_df["измененные столбцы"] = changed_cols_list

status_col = merged_df.pop("status")
merge_col = merged_df.pop("_merge")
merged_df.insert(0, "status", status_col)
merged_df.insert(1, "_merge", merge_col)

st.success("Анализ изменений выполнен!")

# Сохраняем в состояние (будем дальше редактировать)
st.session_state["merged_df"] = merged_df.copy()


# ============================================================
# ФИЛЬТР ПО СТАТУСУ
# ============================================================
st.header("🔎 Фильтр по статусу")

status_filter = st.selectbox(
    "Выберите статус",
    ["all", "changed", "not_changed", "new", "deleted"],
)

base_df = st.session_state["merged_df"]
if status_filter == "all":
    view_df = base_df.copy()
else:
    view_df = base_df[base_df["status"] == status_filter].copy()


# ============================================================
# РЕДАКТИРУЕМАЯ ТАБЛИЦА (как Google Sheets)
# ============================================================
st.header("📋 Таблица (редактируемая)")

# Добавляем скрытый столбец с оригинальным индексом merged_df,
# чтобы можно было правильно обновить и удалять строки
view_df_for_grid = view_df.copy()
view_df_for_grid["_orig_index"] = view_df_for_grid.index

gb = GridOptionsBuilder.from_dataframe(view_df_for_grid)
gb.configure_default_column(
    editable=True,
    filter="agTextColumnFilter",
    sortable=True,
    resizable=True,
    wrapText=True,
)
gb.configure_selection("multiple", use_checkbox=True)
gb.configure_grid_options(enableRangeSelection=True, rowSelection="multiple")
# Скрыть служебный столбец из UI
gb.configure_column("_orig_index", hide=True)

grid_options = gb.build()

grid_response = AgGrid(
    view_df_for_grid,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=600,
)

grid_df = pd.DataFrame(grid_response["data"])      # текущее состояние таблицы
grid_df_before = view_df_for_grid.copy()           # до изменений
selected_rows = grid_response["selected_rows"]     # список словарей выбранных строк


# ============================================================
# УДАЛЕНИЕ ВЫДЕЛЕННЫХ СТРОК
# ============================================================
st.subheader("🗑 Удаление строк (через выделение в таблице)")

if st.button("Удалить выделенные строки"):
    if not selected_rows:
        st.warning("Выберите строки в таблице (галочками слева).")
    else:
        merged_df_current = st.session_state["merged_df"].copy()
        indices_to_drop = []

        for row in selected_rows:
            orig_idx = row.get("_orig_index")
            if orig_idx is None:
                continue
            if orig_idx in merged_df_current.index:
                row_data = merged_df_current.loc[orig_idx].to_dict()
                row_id_val = (
                    row_data.get("old_Activity Master Number")
                    or row_data.get("new_Activity Master Number")
                )
                st.session_state["log_actions"].append({
                    "date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "provider": provider_name,
                    "last_version": last_version,
                    "row_id": row_id_val,
                    "action": "delete_row",
                    "column_name": None,
                    "old_value": row_data,
                    "new_value": None,
                    "manager_id": manager_id,
                })
                indices_to_drop.append(orig_idx)

        merged_df_current.drop(index=indices_to_drop, inplace=True)
        merged_df_current.reset_index(drop=True, inplace=True)
        st.session_state["merged_df"] = merged_df_current

        st.success(f"Удалено строк: {len(indices_to_drop)}")


# ============================================================
# ПЕРЕИМЕНОВАНИЕ И УДАЛЕНИЕ СТОЛБЦОВ
# ============================================================
st.header("✏ Редактирование структуры (столбцы)")

full_df = st.session_state["merged_df"]

# --- Переименование столбца ---
st.subheader("Переименовать столбец")

col_to_rename = st.selectbox("Столбец для переименования", full_df.columns.tolist())
new_col_name = st.text_input("Новое имя столбца", key="rename_col_input")

if st.button("Переименовать столбец"):
    if new_col_name and new_col_name not in full_df.columns:
        old_name = col_to_rename
        st.session_state["merged_df"].rename(columns={old_name: new_col_name}, inplace=True)

        st.session_state["log_actions"].append({
            "date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "provider": provider_name,
            "last_version": last_version,
            "row_id": None,
            "action": "rename_column",
            "column_name": old_name,
            "old_value": old_name,
            "new_value": new_col_name,
            "manager_id": manager_id,
        })

        st.success(f"Столбец '{old_name}' переименован в '{new_col_name}'")
    else:
        st.warning("Укажите уникальное новое имя столбца.")

full_df = st.session_state["merged_df"]

# --- Удаление столбцов ---
st.subheader("Удалить столбцы")

select_all_cols = st.checkbox("Выделить все столбцы для удаления")
if select_all_cols:
    cols_to_delete = full_df.columns.tolist()
else:
    cols_to_delete = st.multiselect("Выберите столбцы для удаления", full_df.columns.tolist())

if st.button("Удалить столбцы"):
    merged_df_current = st.session_state["merged_df"].copy()
    deleted_count = 0
    for c in cols_to_delete:
        if c in merged_df_current.columns:
            merged_df_current.drop(columns=[c], inplace=True)
            deleted_count += 1

            st.session_state["log_actions"].append({
                "date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "provider": provider_name,
                "last_version": last_version,
                "row_id": None,
                "action": "delete_column",
                "column_name": c,
                "old_value": "COLUMN",
                "new_value": None,
                "manager_id": manager_id,
            })

    st.session_state["merged_df"] = merged_df_current
    st.success(f"Удалено столбцов: {deleted_count}")


# ============================================================
# КНОПКА "СОХРАНИТЬ ИЗМЕНЕНИЯ" — ЛОГИРУЕМ ИЗМЕНЕНИЯ ЯЧЕЕК
# ============================================================
st.subheader("💾 Сохранить изменения в ячейках")

if st.button("Сохранить изменения в таблице"):
    merged_df_current = st.session_state["merged_df"].copy()

    # сравниваем состояние до/после внутри текущего фильтра
    for i in grid_df.index:
        orig_idx = grid_df.loc[i, "_orig_index"]
        if orig_idx not in merged_df_current.index:
            continue

        for col in grid_df.columns:
            if col == "_orig_index":
                continue

            old_val = grid_df_before.loc[i, col]
            new_val = grid_df.loc[i, col]

            # оба NaN — пропускаем
            if pd.isna(old_val) and pd.isna(new_val):
                continue
            if str(old_val) != str(new_val):
                # обновляем основную таблицу
                merged_df_current.loc[orig_idx, col] = new_val

                row_data = merged_df_current.loc[orig_idx]
                row_id_val = (
                    row_data.get("old_Activity Master Number")
                    or row_data.get("new_Activity Master Number")
                )

                st.session_state["log_actions"].append({
                    "date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "provider": provider_name,
                    "last_version": last_version,
                    "row_id": row_id_val,
                    "action": "edit_cell",
                    "column_name": col,
                    "old_value": old_val,
                    "new_value": new_val,
                    "manager_id": manager_id,
                })

    st.session_state["merged_df"] = merged_df_current
    st.success("Изменения в ячейках сохранены и залогированы.")


# ============================================================
# СКАЧАТЬ ОБЪЕДИНЁННУЮ ТАБЛИЦУ
# ============================================================
st.header("⬇ Выгрузка объединённой таблицы")

def download_excel(df: pd.DataFrame):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="merged")
    buffer.seek(0)
    return buffer

st.download_button(
    label="Скачать объединённую таблицу",
    data=download_excel(st.session_state["merged_df"]),
    file_name="merged_status.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


# ============================================================
# ЛОГ ДЕЙСТВИЙ МЕНЕДЖЕРА
# ============================================================
st.header("📘 Лог действий менеджера (log_edit)")

df_log_actions = pd.DataFrame(st.session_state["log_actions"])
if not df_log_actions.empty:
    st.dataframe(df_log_actions, use_container_width=True)
else:
    st.info("Пока нет зафиксированных действий менеджера.")

def download_log_actions(df: pd.DataFrame):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="log_edit")
    buffer.seek(0)
    return buffer

st.download_button(
    label="⬇ Скачать лог действий менеджера",
    data=download_log_actions(df_log_actions),
    file_name="log_edit.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
