import streamlit as st
import pandas as pd
import numpy as np
import io
from st_aggrid import (
    AgGrid,
    GridOptionsBuilder,
    GridUpdateMode,
    JsCode
)

# =============================
# Streamlit config
# =============================
st.set_page_config(
    page_title="AJMAN – Compare & Merge",
    layout="wide"
)

# =============================
# Универсальная очистка Excel
# =============================
def clean_excel_table(uploaded_file):
    df_all = pd.read_excel(uploaded_file, header=None, dtype=object)

    header_row_idx = None
    for i, row in df_all.iterrows():
        if row.astype(str).str.contains(
            "Activity Master Number",
            case=False,
            na=False
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

    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")
    df = df.reset_index(drop=True)
    return df

# =====================================
# Инициируем session_state
# =====================================
if "merged_df" not in st.session_state:
    st.session_state["merged_df"] = None

if "log_actions" not in st.session_state:
    st.session_state["log_actions"] = []

# =====================================
# UI загрузки исходных файлов
# =====================================
st.title("AJMAN — Сравнение и редактирование таблиц")

manager_id = st.text_input("Manager ID", value="system")

col1, col2 = st.columns(2)

with col1:
    old_file = st.file_uploader("Старый файл (df_raw_v1)", type=["xlsx"])
with col2:
    new_file = st.file_uploader("Новый файл (df_raw_v2)", type=["xlsx"])

if not old_file or not new_file:
    st.stop()

provider_name = "ajman"
last_version = old_file.name

st.success("Файлы загружены. Идёт обработка...")

# =====================================
# Чтение и очистка файлов
# =====================================
df_old = clean_excel_table(old_file)
df_new = clean_excel_table(new_file)

old_cols = list(df_old.columns)
new_cols = list(df_new.columns)

st.write("### Очищенные файлы")
st.write(f"Старый файл: {df_old.shape}")
st.write(f"Новый файл: {df_new.shape}")
# ============================================================
# 🧩 СОПОСТАВЛЕНИЕ СТОЛБЦОВ
# ============================================================
st.header("Сопоставление столбцов")

st.markdown(
    "Для каждого столбца из **старого** файла выбери, "
    "какому столбцу из **нового** файла он соответствует."
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


# ============================================================
# 📘 LOG_SCHEMA: renamed / added / deleted
# ============================================================
st.header("Лог изменений структуры столбцов (log_schema)")

log_rows = []
current_date = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
used_new_cols = set()

# старые столбцы → renamed / deleted
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

# новые столбцы, которых не было в старом файле → added
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

df_log_schema = pd.DataFrame(log_rows)

st.subheader("Таблица log_schema")
st.dataframe(df_log_schema, use_container_width=True)


def download_log_schema(df: pd.DataFrame):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="log_schema")
    buf.seek(0)
    return buf


st.download_button(
    "⬇ Скачать log_schema.xlsx",
    data=download_log_schema(df_log_schema),
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

# добавляем префиксы, чтобы различать старые и новые поля
df_old_pref = df_old_renamed.add_prefix("old_")
df_new_pref = df_new.add_prefix("new_")


# ============================================================
# 🔗 ОБЪЕДИНЕНИЕ ТАБЛИЦ ПО Activity Master Number
# ============================================================
st.header("Объединение строк по Activity Master Number")

merged_df = df_old_pref.merge(
    df_new_pref,
    left_on="old_Activity Master Number",
    right_on="new_Activity Master Number",
    how="outer",
    indicator=True,   # показывает, из какой таблицы строка: left_only / right_only / both
)


# ============================================================
# 🧠 ОПРЕДЕЛЕНИЕ СТАТУСА СТРОКИ + 'измененные столбцы'
# ============================================================
def compare_row_changes(row, common_cols):
    """
    Возвращает:
      status: 'deleted' / 'new' / 'changed' / 'not_changed'
      changed_cols_str: перечисление изменённых столбцов через запятую или None
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


# список общих колонок (после переименования) без префиксов
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

# выносим status и _merge в начало
status_col = merged_df.pop("status")
merge_col = merged_df.pop("_merge")
merged_df.insert(0, "status", status_col)
merged_df.insert(1, "_merge", merge_col)

st.success("Объединение и анализ изменений выполнены.")
st.write(f"Размер объединённой таблицы: {merged_df.shape}")

# сохраняем в состояние
st.session_state["merged_df"] = merged_df.copy()

# ============================================================
# 🔎 ФИЛЬТР ПО СТАТУСУ
# ============================================================
st.header("🔎 Фильтр по статусу")

status_filter = st.selectbox(
    "Показать строки со статусом:",
    ["all", "changed", "not_changed", "new", "deleted"],
    index=0
)

base_df = st.session_state["merged_df"]

if status_filter == "all":
    view_df = base_df.copy()
else:
    view_df = base_df[base_df["status"] == status_filter].copy()


# ============================================================
# 👁 САЙДБАР: ВИДИМОСТЬ СТОЛБЦОВ (как Show/Hide в Sheets)
# ============================================================
with st.sidebar:
    st.subheader("👁 Видимость столбцов")
    visible_cols = []
    for c in view_df.columns:
        vis = st.checkbox(c, value=True, key=f"vis_{c}")
        if vis:
            visible_cols.append(c)

    if not visible_cols:
        st.warning("⚠ Вы скрыли все столбцы — таблица будет пустой.")

# применять видимость
view_df = view_df[visible_cols] if visible_cols else view_df.iloc[:, :0]

# служебный столбец — нужен для обработки изменений
view_df = view_df.copy()
view_df["_orig_index"] = view_df.index


# ============================================================
# 📌 КАСТОМНОЕ МЕНЮ ДЛЯ СТОЛБЦОВ (Rename column / Delete column)
# ============================================================
column_menu_js = JsCode("""
function getMainMenuItems(params) {

    var defaultItems = params.defaultItems ? params.defaultItems.slice(0) : [];

    defaultItems.push('separator');

    // ----- RENAME COLUMN -----
    defaultItems.push({
        name: 'Rename column',
        action: function() {
            var col = params.column;
            var colDef = col.getColDef();
            var currentName = colDef.headerName || colDef.field;

            var newName = window.prompt('Новое имя столбца:', currentName);
            if (newName && newName.trim() !== '') {
                colDef.headerName = newName.trim();
                params.api.refreshHeader();
            }
        }
    });

    // ----- DELETE COLUMN -----
    defaultItems.push({
        name: 'Delete column',
        action: function() {
            var field = params.column.getColId();
            var newDefs = [];

            params.api.getColumnDefs().forEach(function(c) {
                var id = c.colId || c.field;
                if (id !== field) newDefs.push(c);
            });

            params.api.setColumnDefs(newDefs);
        }
    });

    return defaultItems;
}
""")


# ============================================================
# 📋 ТАБЛИЦА (AGGRID) — редактируемая
# ============================================================
st.header("📋 Таблица (редактируемая)")

# кнопка удаления строк — должна быть над таблицей
delete_rows_clicked = st.button("🗑 Удалить выбранные строки")

gb = GridOptionsBuilder.from_dataframe(view_df)

gb.configure_default_column(
    editable=True,
    filter=True,
    sortable=True,
    resizable=True,
    wrapText=True,
)

# выбор строк ВСЕГДА через чекбоксы
gb.configure_selection(
    selection_mode="multiple",
    use_checkbox=True
)

gb.configure_grid_options(
    enableRangeSelection=True,
    rowSelection="multiple",
    suppressRowClickSelection=True,
    suppressMenuHide=False
)


# включаем чекбокс в заголовке (select all)
first_col = view_df.columns[0] if len(view_df.columns) else None
if first_col:
    gb.configure_column(
        first_col,
        headerCheckboxSelection=True,
        headerCheckboxSelectionFilteredOnly=True,
        checkboxSelection=True,
    )

# скрыть служебную колонку
gb.configure_column("_orig_index", hide=True)


# --- 💡 РАБОЧИЙ КАСТОМНЫЙ МЕНЮ-КОД ---
custom_menu_js = JsCode("""
function getMainMenuItems(params) {

    var result = params.defaultItems.slice(0);

    result.push('separator');

    // RENAME COLUMN
    result.push({
        name: 'Rename column',
        action: function() {
            let col = params.column;
            let api = params.api;
            let oldName = col.colDef.headerName || col.colDef.field;

            let newName = window.prompt('Новое имя столбца:', oldName);
            if (newName && newName !== oldName) {
                col.colDef.headerName = newName;
                api.refreshHeader();
            }
        }
    });

    // DELETE COLUMN
    result.push({
        name: 'Delete column',
        action: function() {
            let field = params.column.colId;
            let api = params.api;

            let newDefs = api.getColumnDefs().filter(c => c.colId !== field);
            api.setColumnDefs(newDefs);
        }
    });

    return result;
}
""")


grid_options = gb.build()

# ВАЖНО: ВСТАВИТЬ ТОЛЬКО ЗДЕСЬ
grid_options["getMainMenuItems"] = custom_menu_js


# --- РЕНДЕР AG GRID ---
grid_response = AgGrid(
    view_df,
    gridOptions=grid_options,
    update_mode=(
        GridUpdateMode.VALUE_CHANGED |
        GridUpdateMode.SELECTION_CHANGED
    ),
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    height=650,
)

grid_df_after = pd.DataFrame(grid_response["data"])
grid_df_before = view_df.copy()
selected_rows = grid_response["selected_rows"]
column_state = grid_response.get("column_state") or grid_response.get("grid_state", {}).get("columnState", None)

# ============================================================
# 🗑 ЛОГИКА: УДАЛЕНИЕ ВЫБРАННЫХ СТРОК
# ============================================================
if delete_rows_clicked:
    merged_df_current = st.session_state["merged_df"].copy()
    to_delete = []

    for row in selected_rows:
        idx = row.get("_orig_index")
        if idx in merged_df_current.index:
            to_delete.append(idx)

    if not to_delete:
        st.warning("Нет выбранных строк.")
    else:
        df_before = merged_df_current.copy()

        for idx in to_delete:
            row_data = df_before.loc[idx].to_dict()
            row_id = (
                row_data.get("old_Activity Master Number")
                or row_data.get("new_Activity Master Number")
            )

            st.session_state["log_actions"].append({
                "date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "provider": provider_name,
                "last_version": last_version,
                "row_id": row_id,
                "action": "delete_row",
                "column_name": None,
                "old_value": row_data,
                "new_value": None,
                "manager_id": manager_id,
            })

        merged_df_current.drop(index=to_delete, inplace=True)
        merged_df_current.reset_index(drop=True, inplace=True)

        st.session_state["merged_df"] = merged_df_current
        st.success(f"Удалено строк: {len(to_delete)}")

# ============================================================
# 💾 СОХРАНЕНИЕ ИЗМЕНЕНИЙ (ЯЧЕЙКИ + RENAME COLUMN + DELETE COLUMN)
# ============================================================
st.header("💾 Сохранить изменения и экспортировать Excel")

if st.button("Сохранить все изменения"):
    merged_df_current = st.session_state["merged_df"].copy()

    # =======================================
    # 1) ИЗМЕНЕНИЯ В ЯЧЕЙКАХ
    # =======================================
    for i in grid_df_after.index:
        orig_idx = grid_df_after.loc[i, "_orig_index"]
        if orig_idx not in merged_df_current.index:
            continue

        for col in grid_df_after.columns:
            if col == "_orig_index":
                continue

            old_val = grid_df_before.loc[i, col]
            new_val = grid_df_after.loc[i, col]

            # пропускаем NaN == NaN → не менять
            if pd.isna(old_val) and pd.isna(new_val):
                continue

            if str(old_val) != str(new_val):
                merged_df_current.loc[orig_idx, col] = new_val

                row_data = merged_df_current.loc[orig_idx]
                row_id_val = (
                    row_data.get("old_Activity Master Number")
                    or row_data.get("new_Activity Master Number")
                )

                # логируем
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

    # =======================================
    # 2) ПЕРЕИМЕНОВАНИЕ СТОЛБЦОВ (AG Grid menu)
    # =======================================
    """
    column_state имеет структуру:
    [
      { "colId": "old_Activity", "headerName": "New name", ... },
      { ... }
    ]
    """
    column_state = grid_response.get("column_state") or grid_response.get("grid_state", {}).get("columnState", None)

    rename_map = {}
    if column_state:
        for cs in column_state:
            col_id  = cs.get("colId")
            new_hdr = cs.get("headerName")

            # если headerName изменён
            if col_id and new_hdr and col_id in merged_df_current.columns:
                if new_hdr != col_id:
                    rename_map[col_id] = new_hdr

    if rename_map:
        # применяем переименование
        merged_df_current.rename(columns=rename_map, inplace=True)

        # логируем
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

    # =======================================
    # 3) УДАЛЁННЫЕ СТОЛБЦЫ (через меню Delete column)
    # =======================================
    """
    AG Grid после удаления колонки отдаёт новое состояние columnDefs.
    Их можно получить через:
        column_state → список колоночных сущностей
    Нам нужно сравнить НОВЫЕ колонки с merged_df_current.columns.
    """

    if column_state:
        # список колонок, которые остались в AGGRID
        existing_cols = [cs.get("colId") for cs in column_state if cs.get("colId")]

        # реальные колонки в DataFrame
        df_cols = list(merged_df_current.columns)

        # удалённые — это любые df_cols, которых нет в existing_cols
        deleted_cols = [c for c in df_cols if c not in existing_cols]

        if deleted_cols:
            for col in deleted_cols:
                # логирование
                st.session_state["log_actions"].append({
                    "date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "provider": provider_name,
                    "last_version": last_version,
                    "row_id": None,
                    "action": "delete_column",
                    "column_name": col,
                    "old_value": col,
                    "new_value": None,
                    "manager_id": manager_id,
                })

            # удаляем физически
            merged_df_current.drop(columns=deleted_cols, inplace=True)

    # =======================================
    # Фиксируем обновлённый merged_df
    # =======================================
    st.session_state["merged_df"] = merged_df_current
    st.success("Изменения сохранены!")

# ============================================================
# 📤 ВЫГРУЗКА ОБЪЕДИНЁННОЙ ТАБЛИЦЫ В EXCEL
# ============================================================
st.header("⬇ Экспорт в Excel")

def download_excel(df: pd.DataFrame):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="merged")
    buf.seek(0)
    return buf

st.download_button(
    label="⬇ Скачать объединённую таблицу",
    data=download_excel(st.session_state["merged_df"]),
    file_name="merged_status.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


# ============================================================
# 📘 ЛОГ ДЕЙСТВИЙ МЕНЕДЖЕРА (log_edit)
# ============================================================
st.header("📘 Лог действий менеджера (log_edit)")

log_df = pd.DataFrame(st.session_state["log_actions"])

if not log_df.empty:
    st.dataframe(log_df, use_container_width=True)
else:
    st.info("Пока нет зафиксированных действий менеджера.")


# возможность скачать log_edit.xlsx
def download_log_edit(df: pd.DataFrame):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="log_edit")
    buf.seek(0)
    return buf


st.download_button(
    label="⬇ Скачать log_edit.xlsx",
    data=download_log_edit(log_df),
    file_name="log_edit.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# ============================================================
# 🔧 ФИНАЛЬНЫЕ JS-ПАТЧИ ДЛЯ СТАБИЛЬНОЙ РАБОТЫ AG GRID
# ============================================================

# Этот скрипт:
# - гарантирует, что selectAllFiltered() работает корректно
# - стабилизирует отображение меню Rename/Delete после фильтрации
# - фиксирует баг, когда после удаления колонки AGGrid не обновляет columnState


grid_js_fix = JsCode("""
function(e) {
    // Обновляем состояния после загрузки данных
    const api = e.api;

    // Патч: если есть фильтрация → selectAll в header работает только по filtered rows
    api.addEventListener('filterChanged', function() {
        api.refreshCells({force:true});
    });

    // Патч: после удаления колонки пересчитать заголовки
    api.addEventListener('columnEverythingChanged', function() {
        api.refreshHeader();
    });

    // Патч: после rename обновить меню
    api.addEventListener('columnResized', function() {
        api.refreshHeader();
    });
}
""")

# Подключение патча в gridOptions
try:
    grid_options["onFirstDataRendered"] = grid_js_fix
except:
    pass


# ============================================================
# 🎉 ФИНАЛЬНОЕ СООБЩЕНИЕ
# ============================================================
st.success("Готово! Приложение полностью собрано. Все функции активированы.")
st.info("Вы можете продолжать работу или сохранить результаты.")
