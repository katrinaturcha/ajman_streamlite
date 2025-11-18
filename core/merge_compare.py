import pandas as pd
import numpy as np


# ===================================================================
# ① Определение статуса строки + список изменённых колонок
# ===================================================================

def detect_row_changes(row, common_cols):
    """
    Возвращает tuple:
        (status, changed_columns_string or None)

    Возможные статусы:
        - deleted
        - new
        - changed
        - not_changed
    """

    # строка только в старой таблице
    if row["_merge"] == "left_only":
        return "deleted", None

    # строка только в новой таблице
    if row["_merge"] == "right_only":
        return "new", None

    # строка существует в обеих таблицах
    changed_cols = []

    for col in common_cols:
        old_val = row.get(f"old_{col}", None)
        new_val = row.get(f"new_{col}", None)

        # оба значения пустые → не считать изменением
        if pd.isna(old_val) and pd.isna(new_val):
            continue

        # сравнение по строковому представлению
        if str(old_val).strip() != str(new_val).strip():
            changed_cols.append(col)

    if changed_cols:
        return "changed", ", ".join(changed_cols)

    return "not_changed", None



# ===================================================================
# ② Основная функция: объединение + сравнение
# ===================================================================

def merge_and_compare(df_old, df_new):
    """
    Принимает:
        df_old — таблица со старым именованием столбцов (уже переименованная)
        df_new — таблица с новыми данными

    Оба датафрейма должны быть подготовлены:
        df_old = df_old_renamed.add_prefix("old_")
        df_new = df_new.add_prefix("new_")

    Возвращает:
        merged_df — таблица с колонками:
            status
            changed columns
            _merge
            old_*
            new_*
    """

    # ---------------------------------------------------
    # Объединение по Activity Master Number
    # ---------------------------------------------------

    merged = df_old.merge(
        df_new,
        left_on="old_Activity Master Number",
        right_on="new_Activity Master Number",
        how="outer",
        indicator=True
    )

    # ---------------------------------------------------
    # Список реально общих колонок (по смыслу)
    # ---------------------------------------------------

    common_cols = [
        c.replace("old_", "")
        for c in df_old.columns
        if c.replace("old_", "") in [
            col.replace("new_", "") for col in df_new.columns
        ]
    ]

    # ---------------------------------------------------
    # Определяем статус строки + изменённые колонки
    # ---------------------------------------------------

    statuses = []
    changed_list = []

    for _, row in merged.iterrows():
        s, ch = detect_row_changes(row, common_cols)
        statuses.append(s)
        changed_list.append(ch)

    merged["status"] = statuses
    merged["changed columns"] = changed_list

    # ---------------------------------------------------
    # Перемещаем служебные столбцы в начало
    # ---------------------------------------------------

    status_col = merged.pop("status")
    merge_col = merged.pop("_merge")
    changed_col = merged.pop("changed columns")

    merged.insert(0, "changed columns", changed_col)
    merged.insert(0, "status", status_col)
    merged.insert(1, "_merge", merge_col)

    return merged
