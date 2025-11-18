# core/aggrid_config.py

from st_aggrid import GridOptionsBuilder
from typing import Iterable
import pandas as pd


def build_grid_options(
    df: pd.DataFrame,
    *,
    checkbox_selection: bool = True,
    enable_sidebar: bool = True,
    hidden_cols: Iterable[str] = ("_orig_index", "_rowid"),
) -> dict:
    """
    Создаёт gridOptions для AgGrid с максимально типичным поведением
    excel / google sheets:

    - редактируемые ячейки
    - сортировка / фильтры / resize
    - мультивыделение строк с чекбоксами
    - master checkbox в заголовке (select all по фильтру)
    - опциональный sidebar для показа/скрытия столбцов.
    """

    if df.empty:
        gb = GridOptionsBuilder.from_dataframe(df)
    else:
        gb = GridOptionsBuilder.from_dataframe(df)

    # базовые настройки столбцов
    gb.configure_default_column(
        editable=True,
        filter=True,
        sortable=True,
        resizable=True,
        wrapText=True,
        autoHeight=True,
    )

    # выбор строк чекбоксами
    if checkbox_selection:
        gb.configure_selection(
            selection_mode="multiple",
            use_checkbox=True,
        )
        gb.configure_grid_options(
            rowSelection="multiple",
            suppressRowClickSelection=True,
            enableRangeSelection=True,
        )

        # первый столбец — с master checkbox
        first_col = df.columns[0] if len(df.columns) else None
        if first_col is not None:
            gb.configure_column(
                first_col,
                headerCheckboxSelection=True,
                headerCheckboxSelectionFilteredOnly=True,
                checkboxSelection=True,
            )

    # скрываем служебные столбцы
    for c in hidden_cols:
        if c in df.columns:
            gb.configure_column(c, hide=True)

    # sidebar (показывать / скрывать колонки)
    if enable_sidebar:
        gb.configure_side_bar()

    grid_options = gb.build()
    return grid_options

