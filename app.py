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
# 🧠 ОПРЕДЕЛЕНИЕ СТАТУСА СТРОКИ + СПИСОК ИЗМЕНЁННЫХ КОЛОНОК
# ============================================================

def detect_row_changes(row, common_cols):
    """
    Возвращает:
      status: deleted / new / changed / not_changed
      changed_list: перечисление колонок с изменениями через запятую
    """

    # строки есть только в старой
    if row["_merge"] == "left_only":
        return "deleted", None

    # строки есть только в новой
    if row["_merge"] == "right_only":
        return "new", None

    # если строка есть в обеих таблицах
    changed_cols = []
    for col in common_cols:
        old_val = row.get(f"old_{col}", None)
        new_val = row.get(f"new_{col}", None)

        # сравниваем безопасно
        if (pd.isna(old_val) and pd.isna(new_val)):
            continue

        if str(old_val).strip() != str(new_val).strip():
            changed_cols.append(col)

    if changed_cols:
        return "changed", ", ".join(changed_cols)

    return "not_changed", None


# список общих колонок (уже после переименования)
common_cols = [
    c.replace("old_", "")
    for c in df_old_pref.columns
    if c.replace("old_", "") in [x.replace("new_", "") for x in df_new_pref.columns]
]

statuses = []
changed_colnames = []

for _, row in merged_df.iterrows():
    s, ch = detect_row_changes(row, common_cols)
    statuses.append(s)
    changed_colnames.append(ch)

merged_df["status"] = statuses
merged_df["changed columns"] = changed_colnames

# переносим статус в начало
status_col = merged_df.pop("status")
merge_col = merged_df.pop("_merge")
changed_col = merged_df.pop("changed columns")

merged_df.insert(0, "changed columns", changed_col)
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
        vis = st.checkbox(c, value=True, key=f"vis_{c}")
        if vis:
            visible_cols.append(c)
    if not visible_cols:
        st.warning("Не выбрано ни одного столбца — таблица будет пустой.")

view_df_visible = view_df[visible_cols] if visible_cols else view_df.iloc[:, :0]

# служебный столбец для связи с merged_df
view_df_visible = view_df_visible.copy()
view_df_visible["_orig_index"] = view_df_visible.index


# ============================================================
# ТАБЛИЦА (AGGrid, редактируема)
# ============================================================
st.header("📋 Таблица (редактируемая)")
# добавляем уникальный RowID
view_df_visible = view_df_visible.copy()
view_df_visible["_rid"] = (
    view_df_visible["_orig_index"].astype(str) + "_" +
    view_df_visible.index.astype(str)
)

# Кнопка УДАЛИТЬ ВЫБРАННЫЕ СТРОКИ – визуально над таблицей
delete_rows_clicked = st.button("🗑 Удалить выбранные строки")

gb = GridOptionsBuilder.from_dataframe(view_df_visible)

gb.configure_default_column(
    editable=True,
    filter=True,
    sortable=True,
    resizable=True,
    wrapText=True,
)

gb.configure_selection("multiple", use_checkbox=True)

gb.configure_grid_options(
    enableRangeSelection=True,
    rowSelection="multiple",
    suppressRowClickSelection=True,
)

gb.configure_column("_orig_index", hide=True)
gb.configure_column("_rid", hide=True)

grid_options = gb.build()

# обязательный JS для сохранения идентификаторов строк
grid_options["getRowId"] = JsCode("""
function(params) { 
    return params.data._rid;
}
""")

grid_response = AgGrid(
    view_df_visible,
    gridOptions=grid_options,
    update_mode=(GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED),
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=650,
)

grid_df_after = pd.DataFrame(grid_response["data"])
grid_df_before = view_df_visible.copy()

selected_rows = grid_response["selected_rows"]  # ← тут теперь есть _rid

# ============================================================
# УДАЛЕНИЕ ВЫБРАННЫХ СТРОК (через _selectedRowNodeInfo)
# ============================================================
if delete_rows_clicked:
    merged_df_current = st.session_state["merged_df"].copy()

    selected_rids = {row["_rid"] for row in selected_rows if "_rid" in row}

    if not selected_rids:
        st.warning("Нет выделенных строк для удаления.")
    else:
        orig_ids_to_delete = []

        for rid in selected_rids:
            # rid = "_orig_index + '_' + view_index"
            orig_idx = int(rid.split("_")[0])
            orig_ids_to_delete.append(orig_idx)

        orig_ids_to_delete = sorted(set(orig_ids_to_delete))

        # ЛОГИ + удаление строк
        for idx in orig_ids_to_delete:
            if idx not in merged_df_current.index:
                continue

            row_data = merged_df_current.loc[idx].to_dict()
            row_id_val = row_data.get("old_Activity Master Number") or row_data.get("new_Activity Master Number")

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

            merged_df_current.drop(index=idx, inplace=True)

        merged_df_current.reset_index(drop=True, inplace=True)
        st.session_state["merged_df"] = merged_df_current

        st.success(f"Удалено строк: {len(orig_ids_to_delete)}")


# ============================================================
# 💾 СОХРАНЕНИЕ ИЗМЕНЕНИЙ И ЛОГИРНОВАНИЕ
# ============================================================
st.header("💾 Сохранить изменения и выгрузить Excel")

if st.button("Сохранить изменения"):
    merged_df_current = st.session_state["merged_df"].copy()

    # 1. Собираем таблицу ДО и ПОСЛЕ
    before_df = grid_df_before.copy()
    after_df = grid_df_after.copy()

    # привязываемся только по _rid
    before_df = before_df.set_index("_rid")
    after_df = after_df.set_index("_rid")

    # 2. Логируем изменения ячеек
    for rid in after_df.index:

        if rid not in before_df.index:
            # новая строка (пока не реализуем, но можно добавить)
            continue

        orig_idx = int(rid.split("_")[0])         # ← индекс в merged_df
        if orig_idx not in merged_df_current.index:
            continue

        for col in after_df.columns:
            if col in ["_rid"]:  # служебные
                continue

            old_val = before_df.loc[rid, col]
            new_val = after_df.loc[rid, col]

            # если значение изменилось
            if (pd.isna(old_val) and pd.isna(new_val)):
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

    # =======================================================
    # 3. Логируем переименование столбцов (если было)
    # =======================================================
    col_state = grid_response.get("column_state") or grid_response.get("grid_state", {}).get("columnState")

    if col_state:
        rename_map = {}
        for cs in col_state:
            col_id = cs.get("colId")
            header_name = cs.get("headerName")

            if col_id and header_name and col_id in merged_df_current.columns:
                if header_name != col_id:
                    rename_map[col_id] = header_name

        # фиксируем в логах
        for old_name, new_name in rename_map.items():
            st.session_state["log_actions"].append({
                "date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "provider": provider_name,
                "last_version": last_version,
                "row_id": None,
                "action": "rename_column",
                "column_name": old_name,
                "old_value": old_name,
                "new_value": new_name,
                "manager_id": manager_id,
            })

        merged_df_current.rename(columns=rename_map, inplace=True)

    # =======================================================
    # 4. Обновляем merged_df после всех изменений
    # =======================================================
    merged_df_current.reset_index(drop=True, inplace=True)
    st.session_state["merged_df"] = merged_df_current

    st.success("Все изменения сохранены и учтены в логах.")

# ============================================================
# СКАЧАТЬ ОБЪЕДИНЁННУЮ ТАБЛИЦУ
# ============================================================
def download_excel(df: pd.DataFrame):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="merged")
    buffer.seek(0)
    return buffer

st.download_button(
    label="⬇ Скачать объединённую таблицу",
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
