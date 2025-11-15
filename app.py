import streamlit as st
import pandas as pd
import datetime

st.set_page_config(page_title="AJMAN Comparator", layout="wide")

uploaded = st.file_uploader("Загрузите AJM.xlsx", type=["xlsx"])

if not uploaded:
    st.stop()

xls = pd.ExcelFile(uploaded)

# === ТАБЛИЦЫ ===
df_raw_v1 = pd.read_excel(xls, "df_raw_v1")
df_raw_v2 = pd.read_excel(xls, "df_raw_v2")

# Главная таблица сравнений
df_compare = pd.read_excel(xls, "df_compare_nosymb")

# Таблица, куда менеджер пишет решения
df_edit_before_db = pd.read_excel(xls, "df_edit_before_db")

# Логи
log_schema = pd.read_excel(xls, "log_schema")
log_edit = pd.read_excel(xls, "log_edit")


STATUS_LIST = ["Было", "Новое", "Удалить", "Изменено", "Проверить вручную"]


# ======================================================
# ИНТЕРАКТИВНАЯ ОБРАБОТКА СТРОК
# ======================================================

st.header("🔍 Проверка изменений")

row_id = st.number_input(
    "Строка в таблице сравнения",
    min_value=0,
    max_value=len(df_compare) - 1,
    step=1
)

row = df_compare.loc[row_id]
st.subheader("Данные строки")
st.dataframe(row.to_frame(), use_container_width=True)

# Текущие значения
current_status = df_edit_before_db.loc[row_id, "Статус"] if "Статус" in df_edit_before_db.columns else "Проверить вручную"
current_comment = df_edit_before_db.loc[row_id, "Комментарий"] if "Комментарий" in df_edit_before_db.columns else ""

status = st.selectbox("Статус", STATUS_LIST, index=STATUS_LIST.index(current_status))
comment = st.text_area("Комментарий", value=current_comment, height=100)

if st.button("💾 Сохранить решение"):
    df_edit_before_db.loc[row_id, "Статус"] = status
    df_edit_before_db.loc[row_id, "Комментарий"] = comment

    log_edit.loc[len(log_edit)] = {
        "timestamp": datetime.datetime.now(),
        "row_id": row_id,
        "new_status": status,
        "new_comment": comment
    }

    st.success("Сохранено!")


# ======================================================
# ПОКАЗ ЛЮБЫХ ТАБЛИЦ
# ======================================================

st.header("📄 Просмотр таблиц")

tables = {
    "df_compare_nosymb": df_compare,
    "df_edit_before_db": df_edit_before_db,
    "log_edit": log_edit,
    "log_schema": log_schema,
    "df_raw_v1": df_raw_v1,
    "df_raw_v2": df_raw_v2
}

selected = st.selectbox("Выберите таблицу", list(tables.keys()))

st.dataframe(tables[selected], use_container_width=True)


# ======================================================
# СКАЧИВАНИЕ ОБНОВЛЕННОГО ФАЙЛА
# ======================================================

st.header("⬇ Скачать обновлённый файл")

if st.button("Собрать Excel"):
    out_path = "AJM_updated.xlsx"
    writer = pd.ExcelWriter(out_path, engine="openpyxl")

    df_raw_v1.to_excel(writer, "df_raw_v1", index=False)
    df_raw_v2.to_excel(writer, "df_raw_v2", index=False)
    df_compare.to_excel(writer, "df_compare_nosymb", index=False)
    df_edit_before_db.to_excel(writer, "df_edit_before_db", index=False)
    log_edit.to_excel(writer, "log_edit", index=False)
    log_schema.to_excel(writer, "log_schema", index=False)

    writer.close()

    with open(out_path, "rb") as f:
        st.download_button("⬇ Скачать AJM_updated.xlsx", f, file_name="AJM_updated.xlsx")
