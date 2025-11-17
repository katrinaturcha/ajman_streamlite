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
        if row.astype(str).str.contains(
            "Activity Master Number", case=False, na=False
        ).any():
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

if "selected_rows_filtered" not in st.session_state:
    st.session_state["selected_rows_filtered"] = []

if "cols_selected" not in st.session_state:
    st.session_state["cols_selected"] = {}


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
# САЙДБАР: ВИДИМОСТЬ СТОЛБЦОВ ("CHOOSE COLUMNS")
# ============================================================
with st.sidebar:
    st.subheader("👁 Видимость столбцов")
    visible_cols = []
    for c in view_df.columns:
        default_vis = True
        vis = st.checkbox(c, value=default_vis, key=f"vis_{c}")
        if vis:
            visible_cols.append(c)

    if not visible_cols:
        st.warning("Не выбрано ни одного столбца — таблица будет пустой.")

view_df_visible = view_df[visible_cols] if visible_cols else view_df.iloc[:, :0]

# служебный столбец для связи с merged_df
view_df_visible = view_df_visible.copy()
view_df_visible["_orig_index"] = view_df_visible.index

# ============================================================
# БЫСТРОЕ ВЫДЕЛЕНИЕ СТРОК ПО ФИЛЬТРУ
# ============================================================
st.subheader("✨ Быстрое выделение строк")

select_all_rows_flag = st.checkbox(
    "Выделить все строки по текущему фильтру",
    key="select_all_rows",
)

if select_all_rows_flag:
    st.session_state["selected_rows_filtered"] = view_df.index.tolist()
else:
    st.session_state["selected_rows_filtered"] = []


# ============================================================
# ТАБЛИЦА (AGGrid, редактируема)
# ============================================================
st.header("📋 Таблица (редактируемая)")

gb = GridOptionsBuilder.from_dataframe(view_df_visible)
gb.configure_default_column(
    editable=True,
    filter="agTextColumnFilter",
    sortable=True,
    resizable=True,
    wrapText=True,
)
gb.configure_selection("multiple", use_checkbox=True)
gb.configure_grid_options(enableRangeSelection=True, rowSelection="multiple")
gb.configure_column("_orig_index", hide=True)

grid_options = gb.build()

grid_response = AgGrid(
    view_df_visible,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=650,
)

grid_df_after = pd.DataFrame(grid_response["data"])
grid_df_before = view_df_visible.copy()
selected_rows = grid_response["selected_rows"]


# ============================================================
# ВЫБОР СТОЛБЦОВ ДЛЯ УДАЛЕНИЯ (СНИЗУ ТАБЛИЦЫ)
# ============================================================
st.subheader("🧱 Выбор столбцов для удаления")

full_df = st.session_state["merged_df"]

# инициализация структуры выбранных столбцов
for col in full_df.columns:
    if col not in st.session_state["cols_selected"]:
        st.session_state["cols_selected"][col] = False

cols_for_delete = []

cols_row = st.columns(3)
with cols_row[0]:
    if st.button("Выделить все столбцы"):
        for col in full_df.columns:
            st.session_state["cols_selected"][col] = True

with cols_row[1]:
    if st.button("Снять выделение столбцов"):
        for col in full_df.columns:
            st.session_state["cols_selected"][col] = False

st.markdown("Выберите столбцы (галочками), которые хотите удалить:")

for col in full_df.columns:
    # не даём случайно удалить служебный столбец индекса, которого нет
    checked = st.checkbox(
        col,
        value=st.session_state["cols_selected"][col],
        key=f"delcol_{col}",
    )
    st.session_state["cols_selected"][col] = checked
    if checked:
        cols_for_delete.append(col)


# ============================================================
# УНИВЕРСАЛЬНАЯ КНОПКА "УДАЛИТЬ ВЫДЕЛЕННОЕ"
# ============================================================
st.subheader("🗑 Удалить выделенное")

if st.button("Удалить выделенное"):
    merged_df_current = st.session_state["merged_df"].copy()

    # --- 1. Определяем выбранные строки ---
    indices_to_drop_rows = []

    if st.session_state["selected_rows_filtered"]:
        indices_to_drop_rows = st.session_state["selected_rows_filtered"]
    else:
        for row in selected_rows:
            orig_idx = row.get("_orig_index")
            if orig_idx is not None and orig_idx in merged_df_current.index:
                indices_to_drop_rows.append(orig_idx)

    indices_to_drop_rows = sorted(set(indices_to_drop_rows))

    # --- 2. Определяем выбранные столбцы ---
    cols_to_drop = [c for c in full_df.columns if st.session_state["cols_selected"].get(c)]

    # --- 3. Логика: что именно удаляем ---
    if indices_to_drop_rows and cols_to_drop:
        st.warning("Нельзя одновременно удалять и строки, и столбцы. Снимите одну из групп выделений.")
    elif not indices_to_drop_rows and not cols_to_drop:
        st.warning("Ничего не выбрано для удаления.")
    else:
        # Удаление строк
        if indices_to_drop_rows:
            df_before = merged_df_current.copy()
            for idx in indices_to_drop_rows:
                if idx not in df_before.index:
                    continue
                row_data = df_before.loc[idx].to_dict()
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

            merged_df_current.drop(index=indices_to_drop_rows, inplace=True)
            merged_df_current.reset_index(drop=True, inplace=True)
            st.success(f"Удалено строк: {len(indices_to_drop_rows)}")

        # Удаление столбцов
        if cols_to_drop:
            deleted_count = 0
            for c in cols_to_drop:
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

            st.success(f"Удалено столбцов: {deleted_count}")

        # обновляем merged_df
        st.session_state["merged_df"] = merged_df_current

        # сбрасываем выбор столбцов
        for c in st.session_state["cols_selected"]:
            st.session_state["cols_selected"][c] = False

        # сбрасываем выбор строк
        st.session_state["selected_rows_filtered"] = []


# ============================================================
# СОХРАНЕНИЕ ИЗМЕНЕНИЙ ЯЧЕЕК
# ============================================================
st.subheader("💾 Сохранить изменения в ячейках")

if st.button("Сохранить изменения в таблице"):
    merged_df_current = st.session_state["merged_df"].copy()

    for i in grid_df_after.index:
        orig_idx = grid_df_after.loc[i, "_orig_index"]
        if orig_idx not in merged_df_current.index:
            continue

        for col in grid_df_after.columns:
            if col == "_orig_index":
                continue

            old_val = grid_df_before.loc[i, col]
            new_val = grid_df_after.loc[i, col]

            if pd.isna(old_val) and pd.isna(new_val):
                continue
            if str(old_val) != str(new_val):
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
