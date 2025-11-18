from typing import Tuple, List, Dict, Any
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode


def render_editable_table(
    df: pd.DataFrame,
    grid_key: str,
    height: int = 600
) -> Tuple[pd.DataFrame, List[Dict[str, Any]], List[Dict[str, Any]], List[int]]:
    """
    Возвращает:
        df_after            — DataFrame после редактирования
        selected_rows        — список выделенных строк
        cell_changes         — список изменённых ячеек
        indices_to_delete    — индексы, которые запросили удалить
    """

    # ============================
    # 1) Добавляем служебный индекс
    # ============================
    df = df.copy()
    df["_orig_index"] = df.index

    # ============================
    # 2) Настройки AG-Grid
    # ============================
    gb = GridOptionsBuilder.from_dataframe(df)

    gb.configure_default_column(
        editable=True,
        filter=True,
        sortable=True,
        resizable=True,
        wrapText=True,
        autoHeight=True,
    )

    gb.configure_selection("multiple", use_checkbox=True)
    gb.configure_grid_options(
        rowSelection="multiple",
        suppressRowClickSelection=True,
        enableRangeSelection=True,
    )

    # Чекбокс в заголовке – выделить всё
    first_col = df.columns[0]
    gb.configure_column(
        first_col,
        headerCheckboxSelection=True,
        headerCheckboxSelectionFilteredOnly=True,
        checkboxSelection=True,
    )

    # скрываем служебную колонку
    gb.configure_column("_orig_index", hide=True)

    # ============================
    # 3) getRowId — ОБЯЗАТЕЛЬНО
    # ============================
    gb.configure_grid_options(
        getRowId=JsCode("""
            function(params) {
                return params.data._orig_index;
            }
        """)
    )

    grid_options = gb.build()

    # ============================================
    # 4) Рендерим AG-Grid
    # ============================================
    grid = AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
        data_return_mode="AS_INPUT",
        enable_enterprise_modules=True,
        fit_columns_on_grid_load=False,
        height=height,
        key=grid_key,
        allow_unsafe_jscode=True,
    )

    df_after = pd.DataFrame(grid["data"])
    selected_rows = grid.get("selected_rows", [])

    # ============================================
    # 5) Определяем изменения ячеек
    # ============================================
    cell_changes = []

    df_before = df.set_index("_orig_index")
    df_after_i = df_after.set_index("_orig_index")

    for idx in df_after_i.index:
        for col in df_after_i.columns:
            if col == "_orig_index":
                continue
            old_val = df_before.loc[idx, col]
            new_val = df_after_i.loc[idx, col]

            if str(old_val) != str(new_val):
                cell_changes.append({
                    "orig_index": idx,
                    "column": col,
                    "old_value": old_val,
                    "new_value": new_val
                })

    # ============================================
    # 6) Индексы для удаления
    # ============================================
    indices_to_delete = []
    for row in selected_rows:
        if "_orig_index" in row:
            try:
                indices_to_delete.append(int(row["_orig_index"]))
            except:
                pass

    return df_after, selected_rows, cell_changes, indices_to_delete
