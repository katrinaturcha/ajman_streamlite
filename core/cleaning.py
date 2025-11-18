# core/cleaning.py

import pandas as pd
import streamlit as st


def clean_excel_table(uploaded_file):
    """
    Универсальная функция очистки входного Excel-файла.
    Находит строку, содержащую 'Activity Master Number', делает её заголовком,
    удаляет пустые строки и пустые столбцы.

    Работает и для «грязных» файлов, и для нормальных Excel.
    """

    # читаем файл без заголовков
    df_all = pd.read_excel(uploaded_file, header=None, dtype=object)

    # ищем строку, которая содержит название столбца
    header_row_idx = None
    for i, row in df_all.iterrows():
        if row.astype(str).str.contains("Activity Master Number", case=False, na=False).any():
            header_row_idx = i
            break

    if header_row_idx is None:
        st.error("❌ Ошибка: в файле нет строки с заголовком 'Activity Master Number'")
        st.stop()

    # читаем снова, но уже с найденной строкой в качестве заголовка
    if header_row_idx == 0:
        df = pd.read_excel(uploaded_file, dtype=object)
    else:
        df = pd.read_excel(uploaded_file, header=header_row_idx, dtype=object)

    # удаляем полностью пустые строки
    df = df.dropna(how="all")

    # удаляем полностью пустые столбцы
    df = df.dropna(axis=1, how="all")

    # сброс индексов
    df = df.reset_index(drop=True)

    return df
