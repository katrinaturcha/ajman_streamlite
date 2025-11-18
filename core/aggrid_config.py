import pandas as pd
from st_aggrid import GridOptionsBuilder
from st_aggrid.shared import JsCode


# ============================================================
# JS-код для контекстного меню столбца (как в Google Sheets)
# ============================================================

COLUMN_MENU_JS = JsCode("""
function getMainMenuItems(params) {
    var defaultMenu = params.defaultItems.slice();

    defaultMenu.push({
        name: 'Rename column',
        action: function() {
            var col = params.column;
            var api = params.api;
            var oldName = col.colDef.headerName || col.colDef.field;

            var newName = window.prompt('Enter new column name:', oldName);
            if (newName && newName !== oldName) {

                // обновляем headerName
                col.colDef.headerName = newName;
                api.refreshHeader();

                // пишем в глобальный window объект (Streamlit считает потом)
                if (!window._renameEvents) { window._renameEvents = [] }
                window._renameEvents.push({
                    oldName: oldName,
                    newName: newName
                });
            }
        }
    });

    defaultMenu.push({
        name: 'Delete column',
        action: function() {
            var field = params.column.colId;
            var api = params.api;

            var newDefs = api.getColumnDefs().filter(c => c.colId !== field);
            api.setColumnDefs(newDefs);

            if (!window._deleteColumnEvents) { window._deleteColumnEvents = [] }
            window._deleteColumnEvents.push({
                column: field
            });
        }
    });

    defaultMenu.push("separator");

    defaultMenu.push("sortAscending");
    defaultMenu.push("sortDescending");
    defaultMenu.push("separator");
    defaultMenu.push("pinSubMenu");
    defaultMenu.push("valueAggSubMenu");

    return defaultMenu;
}
""")


# ============================================================
# JS: назначение уникального ID строки — _rid
# ============================================================

GET_ROW_ID_JS = JsCode("""
function(params) {
    return params.data._rid;
}
""")


# ============================================================
# Конструктор gridOptions (AG-Grid)
# ============================================================

def build_aggrid_options(view_df: pd.DataFrame):
    """
    Создаёт GridOptionsBuilder и формирует корректные gridOptions.
    Возвращает:
        grid_options
    """

    gb = GridOptionsBuilder.from_dataframe(view_df)

    # ---------------------------------------
    # DEFAULT COLUMN BEHAVIOR (как Sheets)
    # ---------------------------------------

    gb.configure_default_column(
        editable=True,
        filter=True,
        sortable=True,
        resizable=True,
        wrapText=True,
        autoHeight=True
    )

    # ---------------------------------------
    # SELECTION MODE: checkbox + select all
    # ---------------------------------------

    gb.configure_selection(
        selection_mode="multiple",
        use_checkbox=True
    )

    # ---------------------------------------
    # GRID OPTIONS
    # ---------------------------------------

    gb.configure_grid_options(
        rowSelection="multiple",
        suppressRowClickSelection=True,
        animateRows=True,
        undoRedoCellEditing=True,     # встроенный локальный undo-redo в ячейках
        undoRedoCellEditingLimit=50,
        getMainMenuItems=COLUMN_MENU_JS,   # кастомное меню
    )

    # скрываем служебные колонки
    if "_rid" in view_df.columns:
        gb.configure_column("_rid", hide=True)
    if "_orig_index" in view_df.columns:
        gb.configure_column("_orig_index", hide=True)

    # ---------------------------------------
    # BUILD OPTIONS
    # ---------------------------------------

    grid_options = gb.build()

    # обязательный getRowId
    grid_options["getRowId"] = GET_ROW_ID_JS

    # включаем боковое меню (columns tab)
    grid_options["sideBar"] = {
        "toolPanels": [
            {
                "id": "columns",
                "labelDefault": "Columns",
                "labelKey": "columns",
                "iconKey": "columns",
                "toolPanel": "agColumnsToolPanel"
            }
        ],
        "defaultToolPanel": "columns"
    }

    return grid_options
