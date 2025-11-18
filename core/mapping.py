import pandas as pd
import streamlit as st

# ===================================================================
# ① ОТРИСОВКА UI для сопоставления колонок
# ===================================================================

def draw_column_mapping_ui(df_old, df_new):
    """
    Показывает пользователю интерфейс сопоставления колонок.
    Возвращает dict: {old_col: new_col or None}
    """

    st.header("🧩 Сопоставление столбцов")

    st.markdown("""
    Настройте соответствие между столбцами **СТАРОГО** и **НОВОГО** файла.

    - Если столбец исчез → выберите «Нет соответствия»
    - Если появился новый столбец → он будет определён автоматически
    """)

    mapping = {}
    old_cols = list(df_old.columns)
    new_cols = list(df_new.columns)

    for col in old_cols:
        choice = st.selectbox(
            f"Старый столбец: **{col}**",
            options=["— Нет соответствия —"] + new_cols,
            key=f"map_{col}"
        )
        mapping[col] = None if choice == "— Нет соответствия —" else choice

    st.success("Сопоставление столбцов завершено!")

    return mapping


# ===================================================================
# ② ЛОГИРОВАНИЕ: added / deleted / renamed
# ===================================================================

def build_column_change_log(mapping, df_old, df_new, provider_name, last_version):
    """
    Принимает:
        mapping: {old_col: new_col or None}
        df_old, df_new: исходные таблицы

    Возвращает:
        df_log_columns — DataFrame с логом изменений столбцов
    """

    current_date = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    log_rows = []
    used_new_cols = set()

    old_cols = list(df_old.columns)
    new_cols = list(df_new.columns)

    # --------------------------
    # renamed + deleted
    # --------------------------
    for old_col, new_col in mapping.items():

        # DELETED
        if new_col is None:
            log_rows.append({
                "date": current_date,
                "provider": provider_name,
                "last_version": last_version,
                "event": "deleted",
                "old_column": old_col,
                "new_column": None
            })

        else:
            used_new_cols.add(new_col)

            # RENAMED
            if new_col != old_col:
                log_rows.append({
                    "date": current_date,
                    "provider": provider_name,
                    "last_version": last_version,
                    "event": "renamed",
                    "old_column": old_col,
                    "new_column": new_col
                })

    # --------------------------
    # ADDED
    # --------------------------
    for col in new_cols:
        if col not in used_new_cols and col not in old_cols:
            log_rows.append({
                "date": current_date,
                "provider": provider_name,
                "last_version": last_version,
                "event": "added",
                "old_column": None,
                "new_column": col
            })

    df_log = pd.DataFrame(log_rows)

    return df_log


# ===================================================================
# ③ ПРИМЕНЕНИЕ ПЕРЕИМЕНОВАНИЯ К СТАРОЙ ТАБЛИЦЕ
# ===================================================================

def apply_column_mapping(df_old, mapping):
    """
    Переименовывает колонки в старой таблице согласно mapping.

    Пример:
      old: 'Activity Name'
      new: 'Oфициальное Наименование'
    """

    df = df_old.copy()

    rename_map = {old: new for old, new in mapping.items() if new is not None}
    df = df.rename(columns=rename_map)

    return df
