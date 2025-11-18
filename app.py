import io
import numpy as np
import pandas as pd
import streamlit as st

# ag-grid внутри table_editor/aggrid_config
from core.cleaning import clean_excel_table
from core.utils import safe_equals
from core.undo_redo import (
    init_undo_redo,
    push_undo_state,
    undo as undo_state,
    redo as redo_state,
)
from core.logging import (
    init_logs,
    log_edit_cell,
    log_delete_row,
    get_logs_df,
)
from core.table_editor import render_editable_table
from core.editing import apply_row_deletions, apply_cell_edits


# ------------------------------------------------------------
# НАСТРОЙКА СТРАНИЦЫ
# ------------------------------------------------------------
st.set_page_config(layout="wide", page_title="AJMAN – Compare & Merge")

st.title("AJMAN — Сравнение, сопоставление и редактирование таблиц")


# ------------------------------------------------------------
# ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ
# ------------------------------------------------------------
if "merged_df" not in st.session_state:
    st.session_state["merged_df"] = None

init_logs(st.session_state)
init_undo_redo(st.session_state)


# ------------------------------------------------------------
# ВВОД ДАННЫХ МЕНЕДЖЕРА
# ------------------------------------------------------------
manager_id = st.text_input("Manager ID (для логов)", value="system")
provider_name = "ajman"


# ------------------------------------------------------------
# ЗАГРУЗКА ФАЙЛОВ
# ------------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    old_file = st.file_uploader("Загрузите старый файл (df_raw_v1)", type=["xlsx"])
with col2:
    new_file = st.file_uploader("Загрузите новый файл (df_raw_v2)", type=["xlsx"])

if not old_file or not new_file:
    st.info("Загрузите оба файла, чтобы продолжить.")
    st.stop()

last_version = old_file.name
st.success("Файлы загружены! Идёт обработка...")


# ------------------------------------------------------------
# ОЧИСТКА ФАЙЛОВ
# ------------------------------------------------------------
df_old = clean_excel_table(old_file)
df_new = clean_excel_table(new_file)

old_cols = list(df_old.columns)
new_cols = list(df_new.columns)

st.write("### Очищенные таблицы загружены:")
st.write(f"Старая таблица: {df_old.shape[0]} строк, {df_old.shape[1]} колонок")
st.write(f"Новая таблица: {df_new.shape[0]} строк, {df_new.shape[1]} колонок")


# ------------------------------------------------------------
# СОПОСТАВЛЕНИЕ СТОЛБЦОВ (UI)
# ------------------------------------------------------------
st.header("Сопоставление столбцов")

st.markdown(
    "Для каждого **старого** столбца выберите соответствующий столбец "
    "из **новой** таблицы. Если соответствия нет — оставьте «Нет соответствия»."
)

mapping = {}
for col in old_cols:
    choice = st.selectbox(
        f"Старый столбец: **{col}**",
        options=["— Нет соответствия —"] + new_cols,
        key=f"map_{col}",
    )
    mapping[col] = choice if choice != "— Нет соответствия —" else None

st.success("Сопоставление столбцов завершено.")


# ------------------------------------------------------------
# LOG_SCHEMA: renamed / added / deleted
# ------------------------------------------------------------
st.header("Логирование изменений столбцов (log_schema)")

log_rows = []
current_date = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
used_new_cols = set()

# 1) renamed / deleted
for old_col, new_col in mapping.items():
    if new_col is None:
        log_rows.append(
            {
                "date": current_date,
                "provider": provider_name,
                "last_version": last_version,
                "event": "deleted",
                "old_column": old_col,
                "new_column": None,
            }
        )
    else:
        used_new_cols.add(new_col)
        if new_col == old_col:
            # не логируем "без изменений"
            continue
        log_rows.append(
            {
                "date": current_date,
                "provider": provider_name,
                "last_version": last_version,
                "event": "renamed",
                "old_column": old_col,
                "new_column": new_col,
            }
        )

# 2) added
for col in new_cols:
    if col not in used_new_cols and col not in old_cols:
        log_rows.append(
            {
                "date": current_date,
                "provider": provider_name,
                "last_version": last_version,
                "event": "added",
                "old_column": None,
                "new_column": col,
            }
        )

df_log_schema = pd.DataFrame(log_rows)
st.subheader("log_schema")
st.dataframe(df_log_schema, use_container_width=True)


def download_log_schema(df: pd.DataFrame):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="log_schema")
    buffer.seek(0)
    return buffer


st.download_button(
    "⬇ Скачать log_schema.xlsx",
    data=download_log_schema(df_log_schema),
    file_name="log_schema.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


# ------------------------------------------------------------
# ПРИМЕНЯЕМ ПЕРЕИМЕНОВАНИЕ К СТАРОЙ ТАБЛИЦЕ
# ------------------------------------------------------------
df_old_renamed = df_old.copy()
for old_col, new_col in mapping.items():
    if new_col is not None:
        df_old_renamed.rename(columns={old_col: new_col}, inplace=True)

df_old_pref = df_old_renamed.add_prefix("old_")
df_new_pref = df_new.add_prefix("new_")


# ------------------------------------------------------------
# MERGE + СТАТУСЫ + ИЗМЕНЁННЫЕ СТОЛБЦЫ
# ------------------------------------------------------------
st.header("Объединение строк по Activity Master Number")

merged_df = df_old_pref.merge(
    df_new_pref,
    left_on="old_Activity Master Number",
    right_on="new_Activity Master Number",
    how="outer",
    indicator=True,
)


def detect_row_changes(row, common_columns):
    """возвращает (status, changed_columns_str)"""
    if row["_merge"] == "left_only":
        return "deleted", None
    if row["_merge"] == "right_only":
        return "new", None

    changed_cols = []
    for col in common_columns:
        old_val = row.get(f"old_{col}", np.nan)
        new_val = row.get(f"new_{col}", np.nan)
        if not safe_equals(old_val, new_val):
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
    s, ch = detect_row_changes(r, common_cols)
    statuses.append(s)
    changed_cols_list.append(ch)

merged_df["status"] = statuses
merged_df["changed columns"] = changed_cols_list

# переносим служебные колонки в начало
status_col = merged_df.pop("status")
changed_col = merged_df.pop("changed columns")
merge_col = merged_df.pop("_merge")

merged_df.insert(0, "changed columns", changed_col)
merged_df.insert(0, "status", status_col)
merged_df.insert(1, "_merge", merge_col)

# сохраняем в session_state как "текущая версия"
st.session_state["merged_df"] = merged_df.copy()


# ------------------------------------------------------------
# ФИЛЬТР ПО СТАТУСУ
# ------------------------------------------------------------
st.header("Фильтр по статусу")

status_filter = st.selectbox(
    "Выберите статус",
    ["all", "changed", "not_changed", "new", "deleted"],
)

base_df = st.session_state["merged_df"]

if status_filter == "all":
    filtered_df = base_df.copy()
else:
    filtered_df = base_df[base_df["status"] == status_filter].copy()


# ------------------------------------------------------------
# ВИДИМОСТЬ СТОЛБЦОВ (Sidebar)
# ------------------------------------------------------------
with st.sidebar:
    st.subheader("Видимость столбцов")
    visible_cols = []
    for c in filtered_df.columns:
        vis = st.checkbox(c, value=True, key=f"vis_{c}")
        if vis:
            visible_cols.append(c)
    if not visible_cols:
        st.warning("Не выбрано ни одного столбца — таблица будет пустой.")

if visible_cols:
    view_df = filtered_df[visible_cols]
else:
    view_df = filtered_df.iloc[:, :0]


# ------------------------------------------------------------
# UNDO / REDO КНОПКИ
# ------------------------------------------------------------
st.header("Таблица (редактируемая)")

col_undo, col_redo = st.columns(2)
if col_undo.button("↩ Отменить последнее действие"):
    res = undo_state(st.session_state)
    if res is None:
        st.warning("Нет действий для отмены.")
    else:
        st.success("Последнее действие отменено.")

if col_redo.button("↪ Повторить (redo)"):
    res = redo_state(st.session_state)
    if res is None:
        st.warning("Нет действий для повтора.")
    else:
        st.success("Действие повторено.")


# ------------------------------------------------------------
# РЕНДЕР РЕДАКТИРУЕМОЙ ТАБЛИЦЫ (AG-GRID)
# ------------------------------------------------------------
# здесь всё управление гридом вынесено в core.table_editor
result = render_editable_table(view_df, grid_key="main_grid", height=650)

df_after_grid = result["df_after"]
selected_orig_indices = result["selected_orig_indices"]
cell_changes = result["cell_changes"]

# ------------------------------------------------------------
# КНОПКА УДАЛЕНИЯ ВЫБРАННЫХ СТРОК
# ------------------------------------------------------------
st.markdown("### Удаление строк")

if st.button("Удалить выбранные строки"):
    if not selected_orig_indices:
        st.warning("Нет выделенных строк для удаления.")
    else:
        merged_df_current = st.session_state["merged_df"].copy()

        # сохраняем состояние для undo
        push_undo_state(
            st.session_state,
            merged_df_current,
            st.session_state["log_actions"],
        )

        # применяем удаление
        new_df, row_events = apply_row_deletions(
            merged_df_current,
            indices_to_drop=selected_orig_indices,
        )

        # логируем каждую удалённую строку
        for ev in row_events:
            row_dict = ev["row_data"]
            row_id_val = (
                row_dict.get("old_Activity Master Number")
                or row_dict.get("new_Activity Master Number")
            )
            log_delete_row(
                st.session_state,
                manager_id=manager_id,
                row_id=row_id_val,
                old_row_dict=row_dict,
            )

        st.session_state["merged_df"] = new_df
        st.success(f"Удалено строк: {len(row_events)}")


# ------------------------------------------------------------
# СОХРАНЕНИЕ ИЗМЕНЕНИЙ (ЯЧЕЙКИ)
# ------------------------------------------------------------
st.header("Сохранить изменения и выгрузить Excel")

if st.button("Сохранить изменения"):
    if not cell_changes:
        st.info("Нет изменений ячеек для сохранения.")
    else:
        merged_df_before = st.session_state["merged_df"].copy()

        # сохраняем состояние для undo
        push_undo_state(
            st.session_state,
            merged_df_before,
            st.session_state["log_actions"],
        )

        # применяем изменения ячеек
        new_df, cell_events = apply_cell_edits(
            merged_df_before,
            cell_changes=cell_changes,
        )

        # логируем
        for ch in cell_events:
            idx = ch["orig_index"]
            col = ch["column"]
            old_val = ch["old_value"]
            new_val = ch["new_value"]

            # row_id берём по старому df (индекс ещё есть)
            if idx in merged_df_before.index:
                row_data_before = merged_df_before.loc[idx]
                row_id_val = (
                    row_data_before.get("old_Activity Master Number")
                    or row_data_before.get("new_Activity Master Number")
                )
            else:
                row_id_val = None

            log_edit_cell(
                st.session_state,
                manager_id=manager_id,
                row_id=row_id_val,
                column_name=col,
                old_value=old_val,
                new_value=new_val,
            )

        st.session_state["merged_df"] = new_df
        st.success("Все изменения сохранены и зафиксированы в логах.")


# ------------------------------------------------------------
# ВЫГРУЗКА ОБЪЕДИНЁННОЙ ТАБЛИЦЫ
# ------------------------------------------------------------
def download_merged(df: pd.DataFrame):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="merged")
    buffer.seek(0)
    return buffer


st.download_button(
    "Скачать объединённую таблицу (merged_status.xlsx)",
    data=download_merged(st.session_state["merged_df"]),
    file_name="merged_status.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


# ------------------------------------------------------------
# ЛОГ ДЕЙСТВИЙ МЕНЕДЖЕРА
# ------------------------------------------------------------
st.header("Лог действий менеджера (log_edit)")

df_log_actions = get_logs_df(st.session_state)
if df_log_actions.empty:
    st.info("Пока нет зафиксированных действий менеджера.")
else:
    st.dataframe(df_log_actions, use_container_width=True)


def download_log_actions(df: pd.DataFrame):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="log_edit")
    buffer.seek(0)
    return buffer


st.download_button(
    "Скачать log_edit.xlsx",
    data=download_log_actions(df_log_actions),
    file_name="log_edit.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
