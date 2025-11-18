# core/table_editor.py

# core/editing.py

from typing import List, Dict, Any, Tuple
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode


# ============================================================
#  ВСПОМОГАТЕЛЬНО: извлекает изменения ячеек
# ============================================================
def _detect_cell_changes(before_df: pd.DataFrame, after_df: pd.DataFrame) -> List[Dict[str, Any]]:
    changes = []

    for rid in after_df.index:
        if rid not in before_df.index:
            continue

        for col in after_df.columns:
            if col in ["_orig_index", "_rid"]:
                continue

            old_value = before_df.loc[rid, col]
            new_value = after_df.loc[rid, col]

            if pd.isna(old_value) and pd.isna(new_value):
                continue

            if str(old_value) != str(new_value):
                changes.append({
                    "orig_index": int(rid),
                    "column": col,
                    "old_value": old_value,
                    "new_value": new_value
                })

    return changes


# ============================================================
#  ОСНОВНАЯ ФУНКЦИЯ: RENDER TABLE + COLLECT CHANGES
# ============================================================
def render_editable_table(
    df: pd.DataFrame,
    height: int = 650
) -> Dict[str, Any]:
    """
    Отображает редактируемую таблицу AG-Grid.
    Возвращает словарь:
      {
          "df_after": DataFrame после редактирования,
          "selected_orig_indices": [int, ...],
          "cell_changes": [...],
          "column_events": {...}
      }
    """

    # ---------------------------------------------------------
    # Подготовка данных: создаём _rid идентификатор строки
    # ---------------------------------------------------------
    df = df.copy()
    if "_orig_index" not in df.columns:
        df["_orig_index"] = df.index

    df["_rid"] = df["_orig_index"].astype(str)

    # ---------------------------------------------------------
    # AG-GRID OPTIONS
    # ---------------------------------------------------------
    gb = GridOptionsBuilder.from_dataframe(df)

    gb.configure_default_column(
        editable=True,
        filter=True,
        sortable=True,
        resizable=True,
        wrapText=True,
    )

    gb.configure_selection("multiple", use_checkbox=True)

    gb.configure_grid_options(
        rowSelection="multiple",
        suppressRowClickSelection=True,
        enableRangeSelection=True
    )

    # чекбокс в заголовке таблицы
    first_col = df.columns[0]
    gb.configure_column(
        first_col,
        headerCheckboxSelection=True,
        headerCheckboxSelectionFilteredOnly=True,
        checkboxSelection=True,
    )

    # скрываем служебные
    gb.configure_column("_orig_index", hide=True)
    gb.configure_column("_rid", hide=True)

    # JS — обязателен для корректного получения rowId
    get_row_id_js = JsCode("""
        function(params) {
            return params.data._rid;
        }
    """)

    grid_options = gb.build()
    grid_options["getRowId"] = get_row_id_js

    # ---------------------------------------------------------
    # RENDER GRID
    # ---------------------------------------------------------
    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
        data_return_mode="AS_INPUT",
        allow_unsafe_jscode=True,
        enable_enterprise_modules=True,
        fit_columns_on_grid_load=False,
        height=height,
    )

    df_after = pd.DataFrame(grid_response["data"])
    selected_rows = grid_response["selected_rows"]
    column_state = grid_response.get("column_state")

    # ---------------------------------------------------------
    # Извлечение выделенных строк
    # ---------------------------------------------------------
    selected_orig_indices = []
    for row in selected_rows:
        if "_orig_index" in row:
            try:
                selected_orig_indices.append(int(row["_orig_index"]))
            except:
                pass

    # ---------------------------------------------------------
    # Изменения ячеек (до-после)
    # ---------------------------------------------------------
    df_before = df.copy().set_index("_orig_index")
    df_after_idxed = df_after.copy().set_index("_orig_index")

    cell_changes = _detect_cell_changes(df_before, df_after_idxed)

    # ---------------------------------------------------------
    # События колонок: rename / delete (если пользователь редактировал)
    # ---------------------------------------------------------
    column_events = {}

    if column_state:
        for cs in column_state:
            col_id = cs.get("colId")
            header_name = cs.get("headerName")

            if col_id and header_name and col_id != header_name:
                column_events[col_id] = header_name

    # ---------------------------------------------------------
    # Возвращаем всю собранную информацию
    # ---------------------------------------------------------
    return {
        "df_after": df_after_idxed.reset_index(drop=False),
        "selected_orig_indices": selected_orig_indices,
        "cell_changes": cell_changes,
        "column_events": column_events,
    }
