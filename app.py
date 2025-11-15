import streamlit as st
import pandas as pd
import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

st.set_page_config(layout="wide", page_title="AJMAN Workflow")

# ===============================
# Вспомогательные функции
# ===============================

def editable_table(df):
    """Отображает df в интерактивном AGGrid и возвращает изменённый df."""
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(editable=True, wrapText=True, autoHeight=True)
    gb.configure_side_bar()
    gb.configure_grid_options(enableRangeSelection=True)
    gb.configure_selection("multiple")
    grid_options = gb.build()

    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        fit_columns_on_grid_load=True,
        enable_enterprise_modules=True
    )

    return pd.DataFrame(grid_response["data"])


def log_change(log_df, description):
    log_df.loc[len(log_df)] = {
        "timestamp": datetime.datetime.now(),
        "change": description
    }


# ===============================
# Загрузка файла
# ===============================

uploaded = st.file_uploader("Загрузите AJM.xlsx", type=["xlsx"])
if not uploaded:
    st.stop()

xls = pd.ExcelFile(uploaded)

# Главные таблицы
df_compare_nosymb = pd.read_excel(xls, "df_compare_nosymb")
df_edit_before_db = pd.read_excel(xls, "df_edit_before_db")

# Логи
log_schema = pd.read_excel(xls, "log_schema")
log_edit = pd.read_excel(xls, "log_edit")

# ============================================
# ЭТАП 1 — Проверка различий df_compare_nosymb
# ============================================

st.header("ЭТАП 1 — Проверка различий (df_compare_nosymb)")

# Фильтр по статусу
status_filter = st.multiselect(
    "Фильтр по статусу",
    df_compare_nosymb["Статус"].dropna().unique(),
)

if status_filter:
    df_filtered = df_compare_nosymb[df_compare_nosymb["Статус"].isin(status_filter)]
else:
    df_filtered = df_compare_nosymb

st.subheader("Редактируемая таблица")
df_stage1 = editable_table(df_filtered)

if st.button("💾 Сохранить изменения (Этап 1)"):
    df_compare_nosymb.update(df_stage1)
    log_change(log_schema, "Изменения сохранены в df_compare_nosymb")
    st.success("Изменения сохранены!")

if st.button("⬇ Скачать Excel для переводчика"):
    out = pd.ExcelWriter("AJM_for_translator.xlsx", engine="openpyxl")
    df_compare_nosymb.to_excel(out, "df_compare_nosymb", index=False)
    log_schema.to_excel(out, "log_schema", index=False)
    out.close()
    st.download_button("Скачать файл", open("AJM_for_translator.xlsx", "rb"), "AJM_for_translator.xlsx")


# ============================================
# ЭТАП 2 — Работа с переводами
# ============================================

st.header("ЭТАП 2 — Проверка переводов")

st.write("Пока используем df_trans_v1, df_trans_v2 → df_compare_trans")

df_trans_v1 = pd.read_excel(xls, "df_trans_v1")
df_trans_v2 = pd.read_excel(xls, "df_trans_v2")
df_compare_trans = pd.read_excel(xls, "df_compare_trans")

status_filter2 = st.multiselect(
    "Фильтр по статусу перевода",
    df_compare_trans["Статус"].dropna().unique(),
)

if status_filter2:
    df_trans_filtered = df_compare_trans[df_compare_trans["Статус"].isin(status_filter2)]
else:
    df_trans_filtered = df_compare_trans

st.subheader("Редактируемая таблица переводов")
df_stage2 = editable_table(df_trans_filtered)

if st.button("💾 Сохранить изменения (Этап 2)"):
    df_compare_trans.update(df_stage2)
    log_change(log_edit, "Изменения переводов сохранены")
    st.success("Изменения сохранены!")


# ============================================
# ЭТАП 3 — Итоговая таблица для загрузки в БД
# ============================================

st.header("ЭТАП 3 — Итоговые данные для БД")

final_df = df_edit_before_db.copy()

st.subheader("Итоговая таблица")
st.dataframe(final_df, use_container_width=True)

st.subheader("📘 История изменений структуры (log_schema)")
st.dataframe(log_schema, use_container_width=True)

st.subheader("📙 История правок менеджеров (log_edit)")
st.dataframe(log_edit, use_container_width=True)

if st.button("⬇ Скачать итоговый файл для БД"):
    out = pd.ExcelWriter("AJM_final.xlsx", engine="openpyxl")
    final_df.to_excel(out, "final_for_db", index=False)
    log_schema.to_excel(out, "log_schema", index=False)
    log_edit.to_excel(out, "log_edit", index=False)
    out.close()
    st.download_button("Скачать AJM_final.xlsx", open("AJM_final.xlsx", "rb"), "AJM_final.xlsx")