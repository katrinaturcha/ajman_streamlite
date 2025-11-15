import streamlit as st
import pandas as pd
import datetime

st.set_page_config(page_title="AJMAN Activity Comparator", layout="wide")

# ---- Настройки ----
STATUS_LIST = ["Было", "Новое", "Удалить", "Изменено", "Проверить вручную"]


# ============================================================
# 1. ЗАГРУЗКА ФАЙЛА
# ============================================================

st.title("📊 AJMAN — Интерактивное сравнение и подготовка данных для БД")

uploaded = st.file_uploader("Загрузите файл AJM.xlsx", type=["xlsx"])

if not uploaded:
    st.stop()

# Читаем все листы
xls = pd.ExcelFile(uploaded)

df_raw_v1 = pd.read_excel(xls, "df_raw_v1")
df_raw_v2 = pd.read_excel(xls, "df_raw_v2")

df_compare_raw = pd.read_excel(xls, "df_compare_raw")
df_compare_nosymb = pd.read_excel(xls, "df_compare_nosymb")

df_trans_v1 = pd.read_excel(xls, "df_trans_v1")
df_trans_v2 = pd.read_excel(xls, "df_trans_v2")
df_compare_trans = pd.read_excel(xls, "df_compare_trans")

df_edit_before_db = pd.read_excel(xls, "df_edit_before_db")
df_for_database = pd.read_excel(xls, "df_for_database")

log_schema = pd.read_excel(xls, "log_schema")
log_edit = pd.read_excel(xls, "log_edit")


# ============================================================
# 2. ИНТЕРАКТИВНЫЙ ИНТЕРФЕЙС ДЛЯ СРАВНЕНИЯ РЯДОВ
# ============================================================

st.header("🔍 Интерактивная проверка различий")

row_id = st.number_input(
    "Выберите номер строки",
    min_value=0,
    max_value=len(df_compare_raw)-1,
    step=1
)

row = df_compare_raw.loc[row_id]

st.subheader("Исходные данные")
st.dataframe(row.to_frame().rename(columns={row_id: "Value"}))

# ---- виджеты статуса ----
status = st.selectbox(
    "Статус строки",
    STATUS_LIST,
    index=STATUS_LIST.index(row.get("Статус", "Проверить вручную"))
)

comment = st.text_area(
    "Комментарий менеджера:",
    value=row.get("Комментарий", ""),
    height=100
)

save_button = st.button("💾 Сохранить изменения")


# ============================================================
# 3. СОХРАНЕНИЕ РЕШЕНИЯ МЕНЕДЖЕРА
# ============================================================

if save_button:
    df_edit_before_db.loc[row_id, "Статус"] = status
    df_edit_before_db.loc[row_id, "Комментарий"] = comment

    log_edit.loc[len(log_edit)] = {
        "timestamp": datetime.datetime.now(),
        "row_id": row_id,
        "old_row": str(dict(row)),
        "new_status": status,
        "new_comment": comment
    }

    st.success("✔ Изменения сохранены!")


# ============================================================
# 4. ФОРМИРОВАНИЕ ИТОГОВОЙ df_for_database
# ============================================================

st.header("📦 Формирование итоговой таблицы для БД")

if st.button("Сформировать df_for_database"):
    result = df_edit_before_db.copy()
    result = result[result["Статус"] != "Удалить"]
    result = result.drop(columns=["Статус", "Различия", "Комментарий"], errors="ignore")

    df_for_database = result.copy()

    # логируем изменения структуры
    log_schema.loc[len(log_schema)] = {
        "timestamp": datetime.datetime.now(),
        "columns": ", ".join(df_for_database.columns)
    }

    st.success("✔ Итоговая таблица df_for_database сформирована!")


# ============================================================
# 5. ПОКАЗАТЬ ГОТОВЫЕ ТАБЛИЦЫ
# ============================================================

st.header("📄 Просмотр таблиц")

selected_table = st.selectbox(
    "Выберите таблицу для просмотра",
    [
        "df_edit_before_db",
        "df_for_database",
        "log_edit",
        "log_schema",
        "df_compare_raw",
        "df_compare_nosymb",
        "df_raw_v1",
        "df_raw_v2",
        "df_trans_v1",
        "df_trans_v2",
        "df_compare_trans"
    ]
)

st.dataframe(eval(selected_table))


# ============================================================
# 6. ВЫГРУЗКА ФАЙЛА ОБРАТНО (Excel)
# ============================================================

st.header("⬇ Скачать обновлённый Excel-файл")

if st.button("Скачать AJM_updated.xlsx"):
    output = pd.ExcelWriter("AJM_updated.xlsx", engine="openpyxl")

    df_raw_v1.to_excel(output, "df_raw_v1", index=False)
    df_raw_v2.to_excel(output, "df_raw_v2", index=False)

    df_compare_raw.to_excel(output, "df_compare_raw", index=False)
    df_compare_nosymb.to_excel(output, "df_compare_nosymb", index=False)

    df_trans_v1.to_excel(output, "df_trans_v1", index=False)
    df_trans_v2.to_excel(output, "df_trans_v2", index=False)
    df_compare_trans.to_excel(output, "df_compare_trans", index=False)

    df_edit_before_db.to_excel(output, "df_edit_before_db", index=False)
    df_for_database.to_excel(output, "df_for_database", index=False)

    log_schema.to_excel(output, "log_schema", index=False)
    log_edit.to_excel(output, "log_edit", index=False)

    output.close()

    st.success("✔ Готово! Файл сохранён как AJM_updated.xlsx")
    with open("AJM_updated.xlsx", "rb") as f:
        st.download_button("⬇ Скачать файл", f, file_name="AJM_updated.xlsx")