# core/utils.py
import pandas as pd
import numpy as np
from copy import deepcopy
from datetime import datetime


# ============================================================
# 🌟 TIMESTAMP
# ============================================================
def now_ts():
    """Возвращает timestamp в удобном формате."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# 🌟 БЕЗОПАСНОЕ СРАВНЕНИЕ ЯЧЕЕК
# ============================================================
def safe_equals(a, b):
    """Корректное сравнение значений с учётом NaN, типов и лишних пробелов."""
    if pd.isna(a) and pd.isna(b):
        return True
    return str(a).strip() == str(b).strip()


def safe_not_equals(a, b):
    return not safe_equals(a, b)


# ============================================================
# 🌟 НОРМАЛИЗАЦИЯ ТЕКСТА
# ============================================================
def normalize_text(val):
    """Превращает любые значения в аккуратный текст."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(val).strip().replace("\n", " ").replace("\r", "")


# ============================================================
# 🌟 ГЛУБОКОЕ КЛОНИРОВАНИЕ DF
# ============================================================
def clone_df(df: pd.DataFrame) -> pd.DataFrame:
    """Делает глубокую копию DataFrame (для undo/redo)."""
    return deepcopy(df)


# ============================================================
# 🌟 UNDO / REDO СТЕКИ
# ============================================================
def push_undo(df, session_state):
    """Добавляет копию df в undo стек и очищает redo."""
    session_state["undo_stack"].append(clone_df(df))
    session_state["redo_stack"].clear()


def undo(session_state):
    """
    Делает шаг назад.
    Перекладывает текущий df → redo, достаёт последний undo → current.
    """
    if not session_state["undo_stack"]:
        return None, False

    prev_df = session_state["undo_stack"].pop()
    session_state["redo_stack"].append(clone_df(session_state["merged_df"]))

    return prev_df, True


def redo(session_state):
    """Делает шаг вперёд."""
    if not session_state["redo_stack"]:
        return None, False

    next_df = session_state["redo_stack"].pop()
    session_state["undo_stack"].append(clone_df(session_state["merged_df"]))

    return next_df, True


# ============================================================
# 🌟 ОБРАБОТКА ID-СТОЛБЦОВ (Для AG-Grid)
# ============================================================
def build_row_id(orig_index: int, view_index: int) -> str:
    """Создаёт уникальный row_id для AG-Grid."""
    return f"{orig_index}_{view_index}"


def parse_row_id(rid: str) -> int:
    """Возвращает orig_index из row_id."""
    try:
        return int(rid.split("_")[0])
    except Exception:
        return None


# ============================================================
# 🌟 ПРОВЕРКА СТОЛБЦОВ
# ============================================================
def ensure_column(df: pd.DataFrame, col: str):
    """Создаёт столбец, если его нет."""
    if col not in df.columns:
        df[col] = None


def drop_columns_safe(df: pd.DataFrame, cols: list):
    """Безопасное удаление столбцов."""
    for c in cols:
        if c in df.columns:
            df.drop(columns=[c], inplace=True)


# ============================================================
# 🌟 ЛОГИРОВАНИЕ (универсальный helper)
# ============================================================
def log_action(session_state, action, manager_id, *,
               row_id=None, column_name=None,
               old_value=None, new_value=None,
               provider=None, version=None):

    session_state["log_actions"].append({
        "date": now_ts(),
        "provider": provider,
        "last_version": version,
        "row_id": row_id,
        "action": action,
        "column_name": column_name,
        "old_value": old_value,
        "new_value": new_value,
        "manager_id": manager_id,
    })
