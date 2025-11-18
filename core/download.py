import pandas as pd
import streamlit as st


def clean_excel_table(uploaded_file):
    """
    Универсальная чистка Excel-файла:
    - ищет строку с 'Activity Master Number'
    - корректно загружает таблицу
    - удаляет пустые строки и столбцы
    - возвращает чистый DataFrame
    """

    # Загружаем сырой Excel без заголовков
    df_all = pd.read_excel(uploaded_file, header=None, dtype=object)

    # Находим строку-заголовок
    header_row_idx = None
    for i, row in df_all.iterrows():
        if row.astype(str).str.contains(
            "Activity Master Number", case=False, na=False
        ).any():
            header_row_idx = i
            break

    if header_row_idx is None:
        st.error("❌ Не найдена строка с заголовком 'Activity Master Number'")
        st.stop()

    # Загружаем таблицу уже с правильно найденным header
    if header_row_idx == 0:
        df = pd.read_excel(uploaded_file, dtype=object)
    else:
        df = pd.read_excel(uploaded_file, header=header_row_idx, dtype=object)

    # Удалить полностью пустые строки
    df = df.dropna(how="all")

    # Удалить полностью пустые колонки
    df = df.dropna(axis=1, how="all")

    # Очистить лишние пробелы и привести колонки в нормальный вид
    df.columns = [str(c).strip() for c in df.columns]

    # Финальное приведение
    df = df.reset_index(drop=True)

    return df
