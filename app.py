import io
import datetime
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

st.set_page_config(layout="wide", page_title="AJMAN Activity Manager")

# ==============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================

def init_state_from_file(uploaded_file):
    """Инициализируем все датафреймы из Excel только один раз на загрузку файла."""
    xls = pd.ExcelFile(uploaded_file)

    st.session_state.df_compare = pd.read_excel(xls, "df_compare_nosymb")
    st.session_state.df_edit = pd.read_excel(xls, "df_edit_before_db")

    # логи
    st.session_state.log_schema = pd.read_excel(xls, "log_schema")
    st.session_state.log_edit = pd.read_excel(xls, "log_edit")

    # сохраняем имя файла, чтобы при новой загрузке переинициализироваться
    st.session_state.source_filename = uploaded_file.name
    st.session_state.initialized = True


def aggrid_with_selection(df, status_col=None, status_colors=None, key=None):
    """
    Показать редактируемую таблицу с мультивыбором строк.
    status_col — колонка, по которой подсвечиваем цветом строки (например, 'Статус').
    status_colors — словарь {значение: цвет}.
    Возвращает (df_edited, selected_orig_indices).
    """
    # сохраняем оригинальный индекс, чтобы не потерять его после фильтрации
    df_to_show = df.copy()
    df_to_show["_orig_index"] = df_to_show.index

    gb = GridOptionsBuilder.from_dataframe(df_to_show)
    gb.configure_default_column(editable=True, wrapText=True, autoHeight=True)
    gb.configure_selection("multiple", use_checkbox=True)
    gb.configure_side_bar()

    # если нужно — подсветка по статусу
    if status_col and status_col in df_to_show.columns and status_colors:
        js_parts = []
        for val, color in status_colors.items():
            js_parts.append(
                f"if (params.colDef.field == '{status_col}' && params.value == '{val}')"
                f" {{ return {{'backgroundColor': '{color}'}}; }}"
            )
        js_code = "function(params) {" + " else ".join(js_parts) + " else {return {};}}"  # noqa: E501
        status_style = JsCode(js_code)
        gb.configure_column(status_col, cellStyle=status_style)

    grid_options = gb.build()

    grid_response = AgGrid(
        df_to_show,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        key=key,
    )

    df_edited = pd.DataFrame(grid_response["data"]).drop(columns=["_orig_index"])
    # какие строки выбраны
    selected = grid_response["selected_rows"]
    selected_indices = [int(r["_orig_index"]) for r in selected] if selected else []

    return df_edited, selected_indices


def append_schema_log(msg: str):
    st.session_state.log_schema.loc[len(st.session_state.log_schema)] = {
        "timestamp": datetime.datetime.now(),
        "change": msg,
    }


def append_edit_log(msg: str):
    st.session_state.log_edit.loc[len(st.session_state.log_edit)] = {
        "timestamp": datetime.datetime.now(),
        "change": msg,
    }


def make_excel_download(dfs: dict, filename: str):
    """dfs: {'sheet_name': df} → байты Excel."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    buffer.seek(0)
    st.download_button(
        "⬇ Скачать " + filename,
        data=buffer,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ==============================
# UI
# ==============================

st.title("📊 AJMAN — Управление изменениями и переводами")

uploaded = st.file_uploader("Загрузите файл AJM.xlsx", type=["xlsx"])
if not uploaded:
    st.stop()

# инициализация состояния
if (
    "initialized" not in st.session_state
    or not st.session_state.initialized
    or st.session_state.get("source_filename") != uploaded.name
):
    init_state_from_file(uploaded)

df_compare = st.session_state.df_compare
df_edit = st.session_state.df_edit
log_schema = st.session_state.log_schema
log_edit = st.session_state.log_edit

tab1, tab2, tab3 = st.tabs(
    ["1️⃣ Файл провайдера", "2️⃣ Переводы и итог", "3️⃣ Итоговые таблицы"]
)

# ==========================================
# TAB 1 — ФАЙЛ ПРОВАЙДЕРА / df_compare_nosymb
# ==========================================

with tab1:
    st.subheader("Этап 1. Проверка различий (df_compare_nosymb)")

    # колонка со статусом, пытаемся угадать имя
    status_col_candidates = ["Статус", "status", "Status"]
    status_col = next((c for c in status_col_candidates if c in df_compare.columns), None)

    # блок фильтров по статусу
    if status_col:
        statuses = sorted(df_compare[status_col].dropna().unique())
        st.markdown("**Фильтр по статусу файла:**")
        selected_statuses = st.multiselect(
            "Статусы", options=statuses, default=statuses, label_visibility="collapsed"
        )
        df_filtered = df_compare[df_compare[status_col].isin(selected_statuses)]
    else:
        st.info("В таблице не найден столбец 'Статус' — показываю все строки.")
        df_filtered = df_compare

    # подсветка по статусу (на всякий случай — несколько вариантов)
    status_colors = {
        "changed": "#fff3cd",
        "Изменено": "#fff3cd",
        "new": "#d4edda",
        "Новое": "#d4edda",
        "deleted": "#f8d7da",
        "Удалить": "#f8d7da",
    }

    st.markdown("### Таблица изменений (можно редактировать, фильтровать и выбирать строки)")
    df_stage1, selected_indices = aggrid_with_selection(
        df_filtered,
        status_col=status_col,
        status_colors=status_colors,
        key="compare_table",
    )

    # обновляем исходный df_compare (по индексам отфильтрованного df)
    df_compare.loc[df_stage1.index, :] = df_stage1
    st.session_state.df_compare = df_compare

    # правая панель — детальный diff по одной выбранной строке
    st.markdown("---")
    st.markdown("### Детальный просмотр выбранной строки")

    if selected_indices:
        idx = selected_indices[0]
        row = df_compare.loc[idx]

        # пробуем найти колонки с различиями
        diff_cols = [c for c in df_compare.columns if "Различия" in c]
        name_cols = [c for c in df_compare.columns if "Name" in c and "Различия" not in c]
        descr_cols = [
            c
            for c in df_compare.columns
            if ("Description" in c or "опис" in c.lower()) and "Различия" not in c
        ]

        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("**Строка №{} (индекс {})**".format(idx, idx))
            st.write(row.to_frame())

        with col_right:
            st.markdown("**Различия (по данным таблицы):**")
            if diff_cols:
                for c in diff_cols:
                    if pd.notna(row.get(c, None)):
                        st.markdown(f"**{c}:**")
                        st.write(row[c])
            else:
                st.write("Столбцы с различиями не найдены (поиск по 'Различия').")

            st.markdown("---")
            st.markdown("**Имя / Описание (если есть):**")
            if name_cols:
                for c in name_cols:
                    st.markdown(f"**{c}:** {row[c]}")
            if descr_cols:
                for c in descr_cols:
                    st.markdown(f"**{c}:** {row[c]}")

    else:
        st.info("Выделите хотя бы одну строку в таблице слева, чтобы увидеть подробности здесь.")

    st.markdown("---")
    st.markdown("### Массовые действия по выбранным строкам")

    # колонка для решения менеджера
    decision_col = "Статус менеджера"
    if decision_col not in df_compare.columns:
        df_compare[decision_col] = ""
        st.session_state.df_compare = df_compare

    decision = st.selectbox(
        "Какое решение применить к выбранным строкам?",
        ["(не менять)", "Принято", "Отклонено", "Проверить вручную"],
    )

    if st.button("✅ Применить к выбранным строкам"):
        if not selected_indices:
            st.warning("Сначала выберите строки в таблице.")
        else:
            if decision != "(не менять)":
                df_compare.loc[selected_indices, decision_col] = decision
                st.session_state.df_compare = df_compare
                append_schema_log(
                    f"Менеджер установил '{decision}' для {len(selected_indices)} строк df_compare_nosymb"
                )
                st.success("Решение применено.")
            else:
                st.info("Решение '(не менять)' не изменило данные.")

    st.markdown("### Экспорт для переводчика")
    st.write(
        "После проверки изменений можно выгрузить текущую версию df_compare_nosymb и передать её переводчику."
    )

    if st.button("📤 Подготовить Excel для переводчика"):
        append_schema_log("Выгружен Excel для переводчика из df_compare_nosymb")
        make_excel_download(
            {"df_compare_nosymb": st.session_state.df_compare, "log_schema": st.session_state.log_schema},
            filename="AJM_for_translator.xlsx",
        )

# ==========================================
# TAB 2 — ПЕРЕВОДЫ И ИТОГ / df_edit_before_db
# ==========================================

with tab2:
    st.subheader("Этап 2. Переводы и финальная правка (df_edit_before_db)")

    df_edit = st.session_state.df_edit

    # колонка статуса файла и статуса перевода — пытаемся угадать имена
    file_status_candidates = ["Статус файла", "file_status", "File Status"]
    trans_status_candidates = ["Статус перевода", "translation_status", "Translation Status"]

    file_status_col = next((c for c in file_status_candidates if c in df_edit.columns), None)
    trans_status_col = next((c for c in trans_status_candidates if c in df_edit.columns), None)

    col_filters = st.columns(2)

    if file_status_col:
        with col_filters[0]:
            file_statuses = sorted(df_edit[file_status_col].dropna().unique())
            file_status_filter = st.multiselect(
                "Фильтр по статусу файла",
                options=file_statuses,
                default=file_statuses,
            )
    else:
        file_status_filter = None

    if trans_status_col:
        with col_filters[1]:
            trans_statuses = sorted(df_edit[trans_status_col].dropna().unique())
            trans_status_filter = st.multiselect(
                "Фильтр по статусу перевода",
                options=trans_statuses,
                default=trans_statuses,
            )
    else:
        trans_status_filter = None

    df_edit_filtered = df_edit.copy()
    if file_status_filter is not None:
        df_edit_filtered = df_edit_filtered[df_edit_filtered[file_status_col].isin(file_status_filter)]
    if trans_status_filter is not None:
        df_edit_filtered = df_edit_filtered[df_edit_filtered[trans_status_col].isin(trans_status_filter)]

    st.markdown("### Таблица df_edit_before_db (можно редактировать и выбирать строки)")
    df_edit_new, selected_indices_2 = aggrid_with_selection(
        df_edit_filtered,
        key="edit_table",
    )

    # обновляем основной df_edit
    df_edit.loc[df_edit_new.index, :] = df_edit_new
    st.session_state.df_edit = df_edit

    st.markdown("---")
    st.markdown("### Массовые действия по выбранным строкам (этап 2)")

    decision2_col = "Статус менеджера (перевод)"
    if decision2_col not in df_edit.columns:
        df_edit[decision2_col] = ""
        st.session_state.df_edit = df_edit

    decision2 = st.selectbox(
        "Решение по выбранным строкам:",
        ["(не менять)", "Готово к загрузке в БД", "Требует правки перевода", "Исключить"],
    )

    if st.button("✅ Применить решение (этап 2)"):
        if not selected_indices_2:
            st.warning("Сначала выберите строки в таблице df_edit_before_db.")
        else:
            if decision2 != "(не менять)":
                df_edit.loc[selected_indices_2, decision2_col] = decision2
                st.session_state.df_edit = df_edit
                append_edit_log(
                    f"Менеджер установил '{decision2}' для {len(selected_indices_2)} строк df_edit_before_db"
                )
                st.success("Решение применено.")
            else:
                st.info("Решение '(не менять)' не изменило данные.")

    st.markdown("---")
    st.markdown("### Экспорт итогового файла для загрузки в БД")

    st.write("Итоговая таблица для БД — это текущая версия df_edit_before_db.")

    if st.button("📥 Выгрузить итоговый Excel для БД"):
        append_edit_log("Выгружен итоговый Excel для БД (df_edit_before_db)")
        make_excel_download(
            {
                "final_for_db": st.session_state.df_edit,
                "log_schema": st.session_state.log_schema,
                "log_edit": st.session_state.log_edit,
            },
            filename="AJM_final_for_DB.xlsx",
        )

# ==========================================
# TAB 3 — ИТОГОВЫЕ ТАБЛИЦЫ
# ==========================================

with tab3:
    st.subheader("Итоговая таблица для БД")
    st.dataframe(st.session_state.df_edit, use_container_width=True)

    st.subheader("log_schema — история изменений структуры")
    st.dataframe(st.session_state.log_schema, use_container_width=True)

    st.subheader("log_edit — история решений менеджера")
    st.dataframe(st.session_state.log_edit, use_container_width=True)