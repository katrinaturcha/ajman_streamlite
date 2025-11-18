from typing import Dict, Any, List
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode


def render_editable_table(
    df: pd.DataFrame,
    grid_key: str = "main_grid",
    height: int = 650,
) -> Dict[str, Any]:
    """
    Рендерит редактируемую таблицу AG-Grid и возвращает:
      {
        "df_after": DataFrame после редактирования (с _orig_index),
        "selected_orig_indices": [список индексов исходной merged_df],
        "cell_changes": [
            {
              "orig_index": int,
              "column": str,
              "old_value": Any,
              "new_value": Any,
            },
            ...
        ]
      }
    """

    # ---------------------------------------------------------
    # 1. Подготовка данных: добавляем служебный индекс
    # ---------------------------------------------------------
    df_view = df.copy()

    # _orig_index должен связывать строки view_df с merged_df
    if "_orig_index" not in df_view.columns:
        df_view["_orig_index"] = df_view.index

    # Дополнительный ID строки для AG Grid (строковый)
    df_view["_rid"] = df_view["_orig_index"].astype(str)

    # ---------------------------------------------------------
    # 2. Настройка GridOptions
    # ---------------------------------------------------------
    gb = GridOptionsBuilder.from_dataframe(df_view)

    gb.configure_default_column(
        editable=True,
        filter=True,
        sortable=True,
        resizable=True,
        wrapText=True,
        autoHeight=True,
    )

    # выбор строк как в Google Sheets — чекбоксы
    gb.configure_selection("multiple", use_checkbox=True)

    gb.configure_grid_options(
        rowSelection="multiple",
        suppressRowClickSelection=True,
        enableRangeSelection=True,
    )

    # чекбокс в заголовке (select all по текущему фильтру)
    first_col = df_view.columns[0]
    gb.configure_column(
        first_col,
        headerCheckboxSelection=True,
        headerCheckboxSelectionFilteredOnly=True,
        checkboxSelection=True,
    )

    # служебные колонки скрываем, но они остаются в data
    gb.configure_column("_orig_index", hide=True)
    gb.configure_column("_rid", hide=True)

    # getRowId — обязательный JS, чтобы AG Grid знал стабильный ID строки
    get_row_id = JsCode(
        """
        function(params) {
            return params.data._rid;
        }
        """
    )

    grid_options = gb.build()
    grid_options["getRowId"] = get_row_id

    # ---------------------------------------------------------
    # 3. Рендер AG-Grid
    # ---------------------------------------------------------
    grid_response = AgGrid(
        df_view,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
        data_return_mode="AS_INPUT",
        allow_unsafe_jscode=True,
        enable_enterprise_modules=True,
        fit_columns_on_grid_load=False,
        height=height,
        key=grid_key,
    )

    df_after = pd.DataFrame(grid_response["data"])

    # selected_rows может отсутствовать → берём безопасно
    selected_rows = grid_response.get("selected_rows") or []

    # ---------------------------------------------------------
    # 4. Вычисляем изменённые ячейки (до/после)
    # ---------------------------------------------------------
    # индексация по _orig_index, чтобы привязать к merged_df
    before_df = df_view.set_index("_orig_index")
    after_df = df_after.set_index("_orig_index")

    cell_changes: List[Dict[str, Any]] = []

    # проходим по всем строкам и колонкам (кроме служебных)
    for orig_idx in after_df.index:
        if orig_idx not in before_df.index:
            continue

        for col in after_df.columns:
            if col in ["_orig_index", "_rid"]:
                continue

            old_val = before_df.loc[orig_idx, col]
            new_val = after_df.loc[orig_idx, col]

            # одинаковые пропускаем
            if (pd.isna(old_val) and pd.isna(new_val)) or str(old_val) == str(new_val):
                continue

            cell_changes.append(
                {
                    "orig_index": int(orig_idx),
                    "column": col,
                    "old_value": old_val,
                    "new_value": new_val,
                }
            )

    # ---------------------------------------------------------
    # 5. Индексы выделенных строк (по _orig_index)
    # ---------------------------------------------------------
    selected_orig_indices: List[int] = []
    for row in selected_rows:
        if "_orig_index" in row:
            try:
                selected_orig_indices.append(int(row["_orig_index"]))
            except Exception:
                continue

    selected_orig_indices = sorted(set(selected_orig_indices))

    # ---------------------------------------------------------
    # 6. Возвращаем результат в формате, который ждёт app.py
    # ---------------------------------------------------------
    return {
        "df_after": df_after,
        "selected_orig_indices": selected_orig_indices,
        "cell_changes": cell_changes,
    }
