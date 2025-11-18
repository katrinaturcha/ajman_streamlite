# core/table_editor.py

# core/editing.py

from typing import List, Dict, Any, Tuple
import pandas as pd


# ============================================================
# УДАЛЕНИЕ СТРОК
# ============================================================
def apply_row_deletions(
    merged_df: pd.DataFrame,
    indices_to_drop: List[int],
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Удаляет строки из merged_df по индексам.
    Возвращает:
      - новый DataFrame
      - список событий для логов:
        [
          {
            "row_index": int,
            "row_data": dict,
          },
          ...
        ]
    """

    if not indices_to_drop:
        return merged_df, []

    df_before = merged_df.copy()
    events: List[Dict[str, Any]] = []

    for idx in sorted(set(indices_to_drop)):
        if idx not in df_before.index:
            continue

        row_data = df_before.loc[idx].to_dict()
        events.append(
            {
                "row_index": idx,
                "row_data": row_data,
            }
        )

    df_after = df_before.drop(index=sorted(set(indices_to_drop)), errors="ignore")
    df_after = df_after.reset_index(drop=True)

    return df_after, events


# ============================================================
# ПРИМЕНЕНИЕ ИЗМЕНЕНИЙ ЯЧЕЕК
# ============================================================
def apply_cell_edits(
    merged_df: pd.DataFrame,
    cell_changes: List[Dict[str, Any]],
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Применяет изменения отдельных ячеек к merged_df.

    cell_changes — список словарей вида:
      {
        "orig_index": int,
        "column": "col_name",
        "old_value": ...,
        "new_value": ...
      }

    Возвращает:
      - новый DataFrame
      - список событий для логов (тот же формат, только без фильтрации)
    """

    if not cell_changes:
        return merged_df, []

    df_after = merged_df.copy()

    for change in cell_changes:
        idx = change["orig_index"]
        col = change["column"]
        new_val = change["new_value"]

        if (idx in df_after.index) and (col in df_after.columns):
            df_after.at[idx, col] = new_val

    # пересчёт индексов (по желанию, но обычно удобнее)
    df_after = df_after.reset_index(drop=True)

    return df_after, cell_changes
