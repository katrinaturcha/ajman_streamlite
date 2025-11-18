import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode

from core.logging import (
    log_edit_cell,
    log_delete_row,
    log_rename_column,
    log_delete_column,
    log_undo
)


# ============================================================
# 🧩 ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ (merged_df, undo, redo)
# ============================================================

def init_table_state(session_state, df):
    """
    Создаёт начальные структуры данных.
    """
    if "merged_df" not in session_state:
        session_state["merged_df"] = df.copy()

    if "undo_stack" not in session_state:
        session_state["undo_stack"] = []

    if "redo_stack" not in session_state:
        session_state["redo_stack"] = []


# ============================================================
# 📌 UNDO
# ============================================================

def undo(session_state, manager_id):
    if not session_state["undo_stack"]:
        return False

    prev_df = session_state["undo_stack"].pop()
    session_state["redo_stack"].append(session_state["merged_df"].copy())
    session_state["merged_df"] = prev_df.copy()

    log_undo(session_state, manager_id)

    return True


# ============================================================
# 📌 СОХРАНЕНИЕ СОСТОЯНИЯ ПЕРЕД ДЕЙСТВИЕМ
# ============================================================

def push_undo_state(session_state):
    session_state["undo_stack"].append(session_state["merged_df"].copy())
    session_state["redo_stack"].clear()


# ============================================================
# 📌 НАСТРОЙКА AG-Grid
# ============================================================

def build_grid(df):
    """
    Полная AG-Grid конфигурация с:
      - чекбоксами
      - getRowId
      - контекстным меню
    """

    df = df.copy()
    df["_rid"] = df.index.astype(str)

    gb = GridOptionsBuilder.from_dataframe(df)

    gb.configure_default_column(
        editable=True,
        filter=True,
        sortable=True,
        resizable=True,
        wrapText=True,
    )

    gb.configure_selection(
        selection_mode="multiple",
        use_checkbox=True
    )

    gb.configure_grid_options(
        rowSelection="multiple",
        suppressRowClickSelection=True,
        enableRangeSelection=True,
    )

    # выделить все строки
    first_col = df.columns[0]
    gb.configure_column(
        first_col,
        headerCheckboxSelection=True,
        headerCheckboxSelectionFilteredOnly=True,
        checkboxSelection=True,
    )

    # скрыть служебный
    gb.configure_column("_rid", hide=True)

    grid_options = gb.build()

    # getRowId — важно
    grid_options["getRowId"] = JsCode("""
        function(params){ return params.data._rid; }
    """)

    # КАСТОМНОЕ МЕНЮ СТОЛБЦОВ
    grid_options["getMainMenuItems"] = JsCode("""
        function(params) {
            var items = params.defaultItems.slice();

            items.push("separator");

            items.push({
                name: "Rename column",
                action: function() {
                    var old = params.column.colId;
                    var New = window.prompt("Новое имя:", old);
                    if (New && New !== old) {
                        params.columnApi.applyColumnState({
                            state: [{ colId: old, hide: false, headerName: New }],
                            applyOrder: true
                        });
                    }
                }
            });

            items.push({
                name: "Delete column",
                action: function() {
                    var col = params.column.colId;
                    params.columnApi.applyColumnState({
                        state: [{ colId: col, hide: true }],
                        applyOrder: true
                    });
                }
            });

            return items;
        }
    """)

    return df, grid_options


# ============================================================
# 📌 ОБРАБОТКА ИЗМЕНЕНИЙ ЯЧЕЕК
# ============================================================

def process_cell_changes(session_state, before_df, after_df, manager_id):
    """
    Сравнивает before/after таблицу и логирует изменения.
    """
    merged_df = session_state["merged_df"]

    before_df = before_df.set_index("_rid")
    after_df = after_df.set_index("_rid")

    for rid in after_df.index:
        if rid not in before_df.index:
            continue

        row_index = int(rid)

        if row_index not in merged_df.index:
            continue

        for col in after_df.columns:
            if col == "_rid":
                continue

            old_val = before_df.loc[rid, col]
            new_val = after_df.loc[rid, col]

            if str(old_val) != str(new_val):
                log_edit_cell(
                    session_state,
                    manager_id,
                    row_id=get_row_id(merged_df, row_index),
                    column_name=col,
                    old_value=old_val,
                    new_value=new_val
                )
                merged_df.at[row_index, col] = new_val


def get_row_id(df, idx):
    return df.loc[idx].get("old_Activity Master Number") or df.loc[idx].get("new_Activity Master Number")


# ============================================================
# 📌 УДАЛЕНИЕ СТРОК
# ============================================================

def delete_selected_rows(session_state, selected_rows, manager_id):
    if not selected_rows:
        return 0

    merged_df = session_state["merged_df"]

    push_undo_state(session_state)

    deleted_count = 0

    for row in selected_rows:
        rid = row["_rid"]
        idx = int(rid)

        if idx not in merged_df.index:
            continue

        row_dict = merged_df.loc[idx].to_dict()

        log_delete_row(
            session_state,
            manager_id,
            row_id=get_row_id(merged_df, idx),
            old_row_dict=row_dict
        )

        merged_df.drop(index=idx, inplace=True)
        deleted_count += 1

    merged_df.reset_index(drop=True, inplace=True)
    session_state["merged_df"] = merged_df

    return deleted_count


# ============================================================
# 📌 ОБРАБОТКА ПЕРЕИМЕНОВАНИЯ И УДАЛЕНИЯ СТОЛБЦОВ
# ============================================================

def process_column_state_changes(session_state, grid_response, manager_id):
    """
    Отслеживает изменения columnState → фиксирует rename/delete в логах.
    """
    merged_df = session_state["merged_df"]

    col_state = (
        grid_response.get("column_state")
        or grid_response.get("grid_state", {}).get("columnState")
    )

    if not col_state:
        return

    rename_map = {}
    delete_cols = []

    for cs in col_state:
        col = cs.get("colId")
        name = cs.get("headerName")
        hidden = cs.get("hide", False)

        if col not in merged_df.columns:
            continue

        if name and name != col:
            rename_map[col] = name

        if hidden:
            delete_cols.append(col)

    if rename_map:
        push_undo_state(session_state)
        for old, new in rename_map.items():
            log_rename_column(session_state, manager_id, old, new)
        merged_df.rename(columns=rename_map, inplace=True)

    if delete_cols:
        push_undo_state(session_state)
        for c in delete_cols:
            log_delete_column(session_state, manager_id, c)
        merged_df.drop(columns=delete_cols, inplace=True)

    session_state["merged_df"] = merged_df


# ============================================================
# 📌 ВЫГРУЗКА ТЕКУЩЕГО DF (для отображения)
# ============================================================

def get_view_df(session_state):
    return session_state["merged_df"].copy()
